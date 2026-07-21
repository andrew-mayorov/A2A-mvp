from __future__ import annotations

import asyncio
import builtins
import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sber_a2a.domain.models import (
    ApprovalRequest,
    ApprovalResult,
    ApprovalSnapshot,
    Comparison,
    CreateDealRequest,
    DealEvent,
    DealRecord,
    DealStatus,
    DocumentRef,
    FulfillmentUpdate,
    HumanDecisionKind,
    HumanDecisionRecord,
    OrderState,
    OrderStatus,
    OutboxMessage,
    PaymentDraftStatus,
    PaymentSignatureRequest,
    PaymentSignatureResult,
    Quote,
    utc_now,
)
from sber_a2a.integrations.contracts import DocumentGateway, FulfillmentGateway
from sber_a2a.services.store import DealNotFoundError, DealStore
from sber_a2a.trust_infrastructure.service import (
    TrustControlError,
    TrustedInfrastructureService,
)


class DealConflictError(RuntimeError):
    pass


class DealService:
    def __init__(
        self,
        graph,
        store: DealStore,
        trust: TrustedInfrastructureService,
        fulfillment_gateway: FulfillmentGateway,
        document_gateway: DocumentGateway,
    ) -> None:
        self._graph = graph
        self._store = store
        self._trust = trust
        self._fulfillment_gateway = fulfillment_gateway
        self._document_gateway = document_gateway
        self._approval_lock = asyncio.Lock()
        self._background_tasks: set[asyncio.Task] = set()

    async def create(self, request: CreateDealRequest) -> DealRecord:
        deal = await self._create_draft(request)
        return await self._process(deal.deal_id)

    async def submit(self, request: CreateDealRequest) -> DealRecord:
        deal = await self._create_draft(request)
        self._schedule(deal.deal_id)
        return deal

    async def _create_draft(self, request: CreateDealRequest) -> DealRecord:
        deal_id = uuid4()
        deal = DealRecord(
            deal_id=deal_id,
            status=DealStatus.DRAFT,
            intent=request.intent,
            mandate=request.mandate,
            events=[
                DealEvent(
                    event_type="deal_created",
                    actor=f"A1:{request.mandate.agent_id}",
                    details={
                        "target": "trusted-infrastructure:mandate-service",
                        "message_type": "a2a.procurement.need.v1",
                        "deal_id": str(deal_id),
                        "payload_summary": {
                            "customer_id": request.intent.customer_id,
                            "sku": request.intent.product.sku,
                            "quantity": request.intent.product.quantity,
                            "delivery_city": request.intent.delivery_city,
                            "delivery_by": str(request.intent.delivery_by),
                            "max_total": str(request.intent.max_total),
                        },
                    },
                )
            ],
        )
        await self._store.put(deal)
        return deal

    async def _process(self, deal_id: UUID) -> DealRecord:
        draft = await self._store.get(deal_id)
        initial_state = {
            "deal_id": str(deal_id),
            "intent": draft.intent.model_dump(mode="json"),
            "mandate": draft.mandate.model_dump(mode="json"),
            "supplier_ids": draft.supplier_ids,
            "quotes": [quote.model_dump(mode="json") for quote in draft.quotes],
            "comparison": (draft.comparison.model_dump(mode="json") if draft.comparison else None),
            "status": draft.status.value,
            "errors": draft.errors,
            "events": [event.model_dump(mode="json") for event in draft.events],
        }
        try:
            result = initial_state
            async for snapshot in self._graph.astream(
                initial_state,
                {"configurable": {"thread_id": str(deal_id)}},
                stream_mode="values",
            ):
                result = snapshot
                deal = self._record_from_state(draft, result)
                await self._store.put(deal)
            deal = self._record_from_state(draft, result)
        except Exception as exc:
            deal = draft.model_copy(
                update={
                    "status": DealStatus.FAILED,
                    "errors": [*draft.errors, f"{type(exc).__name__}: {exc}"],
                    "events": [
                        *draft.events,
                        DealEvent(
                            event_type="workflow_failed",
                            actor=f"A1:{draft.mandate.agent_id}",
                            details={"error_type": type(exc).__name__},
                        ),
                    ],
                    "updated_at": utc_now(),
                }
            )
        await self._store.put(deal)
        return deal

    def _record_from_state(self, draft: DealRecord, state: dict) -> DealRecord:
        comparison = Comparison.model_validate(state["comparison"]) if state["comparison"] else None
        preview_snapshot = draft.approval_snapshot
        if (
            preview_snapshot is None
            and comparison is not None
            and comparison.recommended_quote_id is not None
        ):
            evaluated = next(
                (
                    item
                    for item in comparison.evaluated_quotes
                    if item.quote.quote_id == comparison.recommended_quote_id
                ),
                None,
            )
            if evaluated is not None and evaluated.eligible:
                preview_deal = draft.model_copy(update={"comparison": comparison})
                preview_snapshot = self._build_approval_snapshot(
                    preview_deal,
                    evaluated,
                )
        return DealRecord(
            deal_id=draft.deal_id,
            status=DealStatus(state["status"]),
            intent=draft.intent,
            mandate=draft.mandate,
            supplier_ids=state["supplier_ids"],
            quotes=[Quote.model_validate(item) for item in state["quotes"]],
            comparison=comparison,
            approval_snapshot=preview_snapshot,
            errors=state["errors"],
            events=[DealEvent.model_validate(item) for item in state["events"]],
            created_at=draft.created_at,
            updated_at=utc_now(),
        )

    def _schedule(self, deal_id: UUID) -> None:
        task = asyncio.create_task(self._process(deal_id))
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    async def resume_incomplete(self) -> None:
        for deal in await self._store.list(limit=200, status=DealStatus.DRAFT.value):
            self._schedule(deal.deal_id)

    async def get(self, deal_id: UUID) -> DealRecord:
        return await self._store.get(deal_id)

    async def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        status: str | None = None,
    ) -> list[DealRecord]:
        return await self._store.list(limit=limit, offset=offset, status=status)

    async def approve(
        self,
        deal_id: UUID,
        approval: ApprovalRequest,
    ) -> ApprovalResult:
        async with self._approval_lock:
            deal = await self._store.get(deal_id)
            if deal.status in {
                DealStatus.PAYMENT_SIGNATURE_REQUIRED,
                DealStatus.ORDER_CREATED,
                DealStatus.COMPLETED,
            }:
                if (
                    deal.selected_quote_id == approval.quote_id
                    and deal.order_id is not None
                    and deal.payment_draft_id is not None
                ):
                    return ApprovalResult(
                        deal_id=deal_id,
                        status=deal.status,
                        selected_quote_id=approval.quote_id,
                        order_id=deal.order_id,
                        payment_draft_id=deal.payment_draft_id,
                        approval_snapshot_hash=(
                            deal.approval_snapshot.snapshot_hash if deal.approval_snapshot else ""
                        ),
                    )
                raise DealConflictError("Deal already has a different order")
            if deal.status is not DealStatus.AWAITING_APPROVAL:
                raise DealConflictError(f"Deal cannot be approved from status {deal.status.value}")
            if approval.decision is not HumanDecisionKind.APPROVE:
                raise DealConflictError("Use the decision endpoint to reject or request changes")
            if approval.approved_by != deal.mandate.authorized_by:
                raise DealConflictError("Approver is not authorized by the mandate")
            if not deal.mandate.permits("final_offer_acceptance"):
                raise DealConflictError("Mandate does not permit final offer acceptance")
            expires_at = deal.mandate.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            if expires_at <= datetime.now(UTC):
                raise DealConflictError("Mandate has expired")
            if deal.comparison is None:
                raise DealConflictError("Deal has no comparison")

            evaluated = next(
                (
                    item
                    for item in deal.comparison.evaluated_quotes
                    if item.quote.quote_id == approval.quote_id
                ),
                None,
            )
            if evaluated is None or not evaluated.eligible:
                raise DealConflictError("Selected quote is missing or ineligible")
            if evaluated.quote.valid_until <= datetime.now(UTC):
                raise DealConflictError("Selected quote has expired")
            snapshot = self._build_approval_snapshot(deal, evaluated)
            if approval.approval_snapshot_hash != snapshot.snapshot_hash:
                raise DealConflictError("Approval snapshot hash does not match")

            human_decision = HumanDecisionRecord(
                decision=HumanDecisionKind.APPROVE,
                approver_subject=approval.approved_by,
                organization_id=deal.mandate.organization_id,
                role=next(iter(deal.mandate.required_approvals)),
                snapshot_hash=snapshot.snapshot_hash,
                authentication_context={"method": "oidc-or-demo-header"},
                reason=approval.reason,
            )
            try:
                artifacts = await self._trust.process_approved_purchase(
                    deal,
                    evaluated.quote,
                    snapshot,
                    human_decision,
                    idempotency_key=f"deal:{deal_id}:payment-draft",
                )
            except TrustControlError as exc:
                raise DealConflictError(str(exc)) from exc
            payment_draft = artifacts.payment_draft
            order_id = payment_draft.order_id
            payment_draft_id = payment_draft.payment_draft_id
            now = utc_now()
            selected_supplier = evaluated.quote.supplier_id
            order = OrderState(
                order_id=order_id,
                supplier_id=selected_supplier,
                quote_id=approval.quote_id,
                status=OrderStatus.CONFIRMED_BY_SUPPLIER,
                confirmed_at=now,
            )
            lifecycle_events = self._build_approval_events(
                approval,
                snapshot,
                artifacts.anchor.current_hash,
                artifacts.oracle.verification_id,
                payment_draft_id,
                selected_supplier,
            )
            updated = deal.model_copy(
                update={
                    "status": DealStatus.PAYMENT_SIGNATURE_REQUIRED,
                    "selected_quote_id": approval.quote_id,
                    "order_id": order_id,
                    "payment_draft_id": payment_draft_id,
                    "approval_snapshot": snapshot,
                    "order": order,
                    "payment_draft": payment_draft,
                    "human_decision": human_decision,
                    "purchase_intent": artifacts.purchase_intent,
                    "ledger_anchor": artifacts.anchor,
                    "oracle_verification": artifacts.oracle,
                    "policy_decisions": [
                        *deal.policy_decisions,
                        artifacts.policy_decision,
                    ],
                    "fraud_decisions": [
                        *deal.fraud_decisions,
                        artifacts.fraud_decision,
                    ],
                    "updated_at": utc_now(),
                    "events": [*deal.events, *lifecycle_events],
                }
            )
            await self._store.put(updated)
            return ApprovalResult(
                deal_id=deal_id,
                status=updated.status,
                selected_quote_id=approval.quote_id,
                order_id=order_id,
                payment_draft_id=payment_draft_id,
                approval_snapshot_hash=snapshot.snapshot_hash,
            )

    async def decide(
        self,
        deal_id: UUID,
        approval: ApprovalRequest,
    ) -> DealRecord:
        if approval.decision is HumanDecisionKind.APPROVE:
            await self.approve(deal_id, approval)
            return await self.get(deal_id)
        async with self._approval_lock:
            deal = await self._store.get(deal_id)
            if deal.status is not DealStatus.AWAITING_APPROVAL:
                raise DealConflictError("Deal is not awaiting a human decision")
            if approval.approved_by != deal.mandate.authorized_by:
                raise DealConflictError("Approver is not authorized by the mandate")
            if deal.approval_snapshot is None:
                raise DealConflictError("Approval snapshot is missing")
            if approval.approval_snapshot_hash != deal.approval_snapshot.snapshot_hash:
                raise DealConflictError("Approval snapshot hash does not match")
            decision = HumanDecisionRecord(
                decision=approval.decision,
                approver_subject=approval.approved_by,
                organization_id=deal.mandate.organization_id,
                role=next(iter(deal.mandate.required_approvals)),
                snapshot_hash=approval.approval_snapshot_hash,
                authentication_context={"method": "oidc-or-demo-header"},
                reason=approval.reason,
            )
            status = (
                DealStatus.REJECTED
                if approval.decision is HumanDecisionKind.REJECT
                else DealStatus.CHANGES_REQUESTED
            )
            updated = deal.model_copy(
                update={
                    "status": status,
                    "human_decision": decision,
                    "updated_at": utc_now(),
                    "events": [
                        *deal.events,
                        DealEvent(
                            event_type=f"human_{approval.decision.value}",
                            actor=f"human:{approval.approved_by}",
                            details={
                                "target": f"A1:{deal.mandate.agent_id}",
                                "snapshot_hash": approval.approval_snapshot_hash,
                                "reason": approval.reason,
                            },
                        ),
                    ],
                }
            )
            await self._store.put(updated)
            return updated

    async def sign_payment(
        self,
        deal_id: UUID,
        request: PaymentSignatureRequest,
    ) -> PaymentSignatureResult:
        async with self._approval_lock:
            deal = await self._store.get(deal_id)
            if deal.status is DealStatus.COMPLETED and deal.payment_draft is not None:
                return PaymentSignatureResult(
                    deal_id=deal_id,
                    payment_draft_id=deal.payment_draft.payment_draft_id,
                    status=deal.status,
                    payment_status=deal.payment_draft.status,
                )
            if deal.status is not DealStatus.PAYMENT_SIGNATURE_REQUIRED:
                raise DealConflictError("Payment draft is not awaiting signature")
            if not deal.mandate.permits("edo_action"):
                raise DealConflictError("Mandate does not permit fulfillment/EDO action")
            if not request.confirmation:
                raise DealConflictError("Explicit payment confirmation is required")
            if request.signed_by != deal.mandate.authorized_by:
                raise DealConflictError("Payment signer is not authorized by the mandate")
            if deal.payment_draft is None or request.payment_draft_id != deal.payment_draft_id:
                raise DealConflictError("Payment draft ID does not match")
            quote = next(
                (item for item in deal.quotes if item.quote_id == deal.selected_quote_id),
                None,
            )
            if quote is None or deal.order_id is None or deal.approval_snapshot is None:
                raise DealConflictError("Approved purchase state is incomplete")
            fulfillment = await self._fulfillment_gateway.create_demo_timeline(
                supplier_id=quote.supplier_id,
            )
            documents = await self._document_gateway.create_demo_documents(
                deal=deal,
                quote=quote,
                order_id=deal.order_id,
            )
            payment_draft = deal.payment_draft.model_copy(
                update={"status": PaymentDraftStatus.SIGNED}
            )
            events = self._build_lifecycle_events(
                deal,
                ApprovalRequest(
                    quote_id=quote.quote_id,
                    approved_by=request.signed_by,
                    approval_snapshot_hash=deal.approval_snapshot.snapshot_hash,
                ),
                deal.approval_snapshot,
                deal.order_id,
                deal.payment_draft_id,
                quote.supplier_id,
                fulfillment,
                documents,
            )
            updated = deal.model_copy(
                update={
                    "status": DealStatus.COMPLETED,
                    "payment_draft": payment_draft,
                    "fulfillment": fulfillment,
                    "documents": documents,
                    "updated_at": utc_now(),
                    "events": [
                        *deal.events,
                        DealEvent(
                            event_type="payment_draft_signed",
                            actor=f"human:{request.signed_by}",
                            details={
                                "payment_draft_id": str(request.payment_draft_id),
                                "mock_execution": True,
                            },
                        ),
                        *events,
                    ],
                }
            )
            await self._store.put(updated)
            await self._append_and_publish_outbox(
                updated,
                quote,
                deal.approval_snapshot,
                rejected_suppliers=[
                    supplier_id
                    for supplier_id in deal.supplier_ids
                    if supplier_id != quote.supplier_id
                ],
            )
            return PaymentSignatureResult(
                deal_id=deal_id,
                payment_draft_id=request.payment_draft_id,
                status=updated.status,
                payment_status=payment_draft.status,
            )

    def _build_approval_snapshot(self, deal: DealRecord, evaluated) -> ApprovalSnapshot:
        quote = evaluated.quote
        payload = {
            "deal_id": str(deal.deal_id),
            "quote_id": str(quote.quote_id),
            "supplier_id": quote.supplier_id,
            "sku": quote.sku,
            "quantity": quote.quantity,
            "total_cost": str(quote.total_cost),
            "currency": quote.currency,
            "delivery_days": quote.delivery_days,
            "warranty_months": quote.warranty_months,
            "payment_delay_days": quote.payment_delay_days,
            "document_hashes": [],
            "bank_requisites_hash": self._trust.recipient_binding_hash(quote.supplier_id),
            "risk_summary": f"trusted-risk:{quote.supplier_risk}",
            "policy_version": deal.mandate.version,
            "ranking_version": deal.comparison.ranking_version if deal.comparison else "",
            "total_score": str(evaluated.total_score) if evaluated.total_score else None,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return ApprovalSnapshot(
            quote_id=quote.quote_id,
            supplier_id=quote.supplier_id,
            supplier_name=quote.supplier_name,
            sku=quote.sku,
            product_name=quote.product_name,
            quantity=quote.quantity,
            total_cost=quote.total_cost,
            currency=quote.currency,
            delivery_days=quote.delivery_days,
            warranty_months=quote.warranty_months,
            payment_delay_days=quote.payment_delay_days,
            document_hashes=[],
            bank_requisites_hash=self._trust.recipient_binding_hash(quote.supplier_id),
            risk_summary=f"trusted-risk:{quote.supplier_risk}",
            policy_version=deal.mandate.version,
            ranking_version=payload["ranking_version"],
            total_score=evaluated.total_score,
            snapshot_hash=hashlib.sha256(encoded).hexdigest(),
        )

    @staticmethod
    def _build_approval_events(
        approval: ApprovalRequest,
        snapshot: ApprovalSnapshot,
        anchor_hash: str,
        oracle_verification_id: UUID,
        payment_draft_id: UUID,
        selected_supplier: str,
    ) -> builtins.list[DealEvent]:
        return [
            DealEvent(
                event_type="quote_approved",
                actor=f"human:{approval.approved_by}",
                details={
                    "target": "trusted-infrastructure:approval-service",
                    "snapshot_hash": snapshot.snapshot_hash,
                },
            ),
            DealEvent(
                event_type="purchase_intent_anchored",
                actor="trusted-infrastructure:deal-ledger",
                details={"anchor_hash": anchor_hash},
            ),
            DealEvent(
                event_type="oracle_verified",
                actor="trusted-infrastructure:oracle-gateway",
                details={"verification_id": str(oracle_verification_id)},
            ),
            DealEvent(
                event_type="payment_draft_created",
                actor="trusted-infrastructure:payment-gatekeeper",
                details={
                    "target": f"human:{approval.approved_by}",
                    "payment_draft_id": str(payment_draft_id),
                    "status": PaymentDraftStatus.AWAITING_CUSTOMER_SIGNATURE.value,
                    "supplier_id": selected_supplier,
                },
            ),
        ]

    @staticmethod
    def _build_lifecycle_events(
        deal: DealRecord,
        approval: ApprovalRequest,
        snapshot: ApprovalSnapshot,
        order_id: UUID,
        payment_draft_id: UUID,
        selected_supplier: str,
        fulfillment: builtins.list[FulfillmentUpdate],
        documents: builtins.list[DocumentRef],
    ) -> builtins.list[DealEvent]:
        rejected_suppliers = [
            supplier_id for supplier_id in deal.supplier_ids if supplier_id != selected_supplier
        ]
        events = [
            DealEvent(
                event_type="approval_snapshot_created",
                actor=f"A1:{deal.mandate.agent_id}",
                details={
                    "target": f"human:{approval.approved_by}",
                    "message_type": "sber.procurement.approval_snapshot.v1",
                    "snapshot_id": str(snapshot.snapshot_id),
                    "snapshot_hash": snapshot.snapshot_hash,
                },
            ),
            DealEvent(
                event_type="quote_approved",
                actor=f"human:{approval.approved_by}",
                details={
                    "target": f"A1:{deal.mandate.agent_id}",
                    "message_type": "sber.procurement.approval.v1",
                    "quote_id": str(approval.quote_id),
                    "snapshot_hash": snapshot.snapshot_hash,
                },
            ),
            DealEvent(
                event_type="award_sent",
                actor=f"A1:{deal.mandate.agent_id}",
                details={
                    "target": f"A2:{selected_supplier}",
                    "message_type": "sber.procurement.award.v1",
                    "supplier_id": selected_supplier,
                    "quote_id": str(approval.quote_id),
                },
            ),
            *[
                DealEvent(
                    event_type="supplier_rejected",
                    actor=f"A1:{deal.mandate.agent_id}",
                    details={
                        "target": f"A2:{supplier_id}",
                        "message_type": "sber.procurement.rejection.v1",
                        "supplier_id": supplier_id,
                    },
                )
                for supplier_id in rejected_suppliers
            ],
            DealEvent(
                event_type="order_confirmed",
                actor=f"A2:{selected_supplier}",
                details={
                    "target": f"A1:{deal.mandate.agent_id}",
                    "message_type": "sber.procurement.order_confirmation.v1",
                    "order_id": str(order_id),
                },
            ),
            DealEvent(
                event_type="payment_draft_created",
                actor="trusted-infrastructure:payment-gatekeeper",
                details={
                    "target": "payment-adapter",
                    "message_type": "sber.procurement.payment_draft.v1",
                    "payment_draft_id": str(payment_draft_id),
                    "status": PaymentDraftStatus.AWAITING_CUSTOMER_SIGNATURE.value,
                },
            ),
        ]
        events.extend(
            DealEvent(
                event_type="fulfillment_updated",
                actor=update.actor,
                details={
                    "target": f"A1:{deal.mandate.agent_id}",
                    "message_type": "sber.procurement.fulfillment.v1",
                    "status": update.status.value,
                    **update.details,
                },
            )
            for update in fulfillment
        )
        events.extend(
            DealEvent(
                event_type="document_registered",
                actor="mock-edo",
                details={
                    "target": f"A1:{deal.mandate.agent_id}",
                    "message_type": "sber.procurement.document_ref.v1",
                    "document_id": str(document.document_id),
                    "document_type": document.document_type,
                    "sha256": document.sha256,
                },
            )
            for document in documents
        )
        events.append(
            DealEvent(
                event_type="deal_completed",
                actor=f"A1:{deal.mandate.agent_id}",
                details={
                    "target": f"A1:{deal.mandate.agent_id}",
                    "message_type": "sber.procurement.deal_summary.v1",
                    "order_id": str(order_id),
                },
            )
        )
        return events

    async def _append_and_publish_outbox(
        self,
        deal: DealRecord,
        quote: Quote,
        snapshot: ApprovalSnapshot,
        *,
        rejected_suppliers: builtins.list[str],
    ) -> None:
        if deal.order_id is None or deal.payment_draft_id is None:
            return
        correlation_id = deal.events[-1].correlation_id if deal.events else uuid4()
        messages = [
            OutboxMessage(
                aggregate_id=deal.deal_id,
                recipient_agent_id=quote.supplier_id,
                message_type="sber.procurement.award.v1",
                idempotency_key=f"deal:{deal.deal_id}:award:{quote.supplier_id}",
                correlation_id=correlation_id,
                payload={
                    "deal_id": str(deal.deal_id),
                    "order_id": str(deal.order_id),
                    "quote_id": str(quote.quote_id),
                    "snapshot_hash": snapshot.snapshot_hash,
                },
            ),
            *[
                OutboxMessage(
                    aggregate_id=deal.deal_id,
                    recipient_agent_id=supplier_id,
                    message_type="sber.procurement.rejection.v1",
                    idempotency_key=(f"deal:{deal.deal_id}:rejection:{supplier_id}"),
                    correlation_id=correlation_id,
                    payload={
                        "deal_id": str(deal.deal_id),
                        "selected_supplier_id": quote.supplier_id,
                    },
                )
                for supplier_id in rejected_suppliers
            ],
            OutboxMessage(
                aggregate_id=deal.deal_id,
                recipient_agent_id="payment-adapter",
                message_type="sber.procurement.payment_draft.v1",
                idempotency_key=f"deal:{deal.deal_id}:payment-draft",
                correlation_id=correlation_id,
                payload={
                    "deal_id": str(deal.deal_id),
                    "payment_draft_id": str(deal.payment_draft_id),
                    "amount": str(quote.total_cost),
                    "currency": quote.currency,
                },
            ),
            *[
                OutboxMessage(
                    aggregate_id=deal.deal_id,
                    recipient_agent_id=document.source,
                    message_type="sber.procurement.document_ref.v1",
                    idempotency_key=(f"deal:{deal.deal_id}:document:{document.document_id}"),
                    correlation_id=correlation_id,
                    payload=document.model_dump(mode="json"),
                )
                for document in deal.documents
            ],
        ]
        append_outbox = getattr(self._store, "append_outbox", None)
        mark_published = getattr(self._store, "mark_outbox_published", None)
        if append_outbox is not None:
            await append_outbox(messages)
        if mark_published is not None:
            await mark_published(deal.deal_id)


__all__ = [
    "DealConflictError",
    "DealNotFoundError",
    "DealService",
]
