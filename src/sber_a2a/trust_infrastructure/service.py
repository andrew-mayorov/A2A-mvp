from __future__ import annotations

import asyncio
from dataclasses import dataclass
from uuid import UUID, uuid4

from sber_a2a.config import RuntimeConfig
from sber_a2a.domain.models import (
    ApprovalSnapshot,
    ControlDecisionRecord,
    DealRecord,
    HumanDecisionRecord,
    LedgerAnchorRecord,
    OracleVerificationRecord,
    PaymentDraft,
    PaymentDraftStatus,
    PurchaseIntentRecord,
    Quote,
)
from sber_a2a.shared.security.signatures import payload_hash
from sber_a2a.trust_infrastructure.ledger import DatabaseHashChainAnchor


class TrustControlError(RuntimeError):
    pass


@dataclass(frozen=True)
class ApprovedPurchaseArtifacts:
    purchase_intent: PurchaseIntentRecord
    anchor: LedgerAnchorRecord
    oracle: OracleVerificationRecord
    payment_draft: PaymentDraft
    policy_decision: ControlDecisionRecord
    fraud_decision: ControlDecisionRecord


class TrustedInfrastructureService:
    """Deterministic controls only; it never discovers, negotiates or ranks quotes."""

    def __init__(
        self,
        runtime: RuntimeConfig,
        anchor: DatabaseHashChainAnchor,
    ) -> None:
        self._runtime = runtime
        self._anchor = anchor
        self._payment_results: dict[str, PaymentDraft] = {}
        self._purchase_results: dict[str, ApprovedPurchaseArtifacts] = {}
        self._payment_lock = asyncio.Lock()

    def _supplier(self, agent_id: str):
        supplier = next(
            (item for item in self._runtime.suppliers if item.agent_id == agent_id),
            None,
        )
        if supplier is None:
            raise TrustControlError("Supplier is absent from Agent Registry")
        if supplier.status != "active":
            raise TrustControlError("Supplier is not active")
        return supplier

    def recipient_binding_hash(self, agent_id: str) -> str:
        return self._supplier(agent_id).bank_binding_hash

    def check_mandate(self, deal: DealRecord, operation: str) -> ControlDecisionRecord:
        reasons: list[str] = []
        if not deal.mandate.permits(operation):
            reasons.append("Mandate does not permit the operation")
        if deal.intent.currency != deal.mandate.currency:
            reasons.append("Mandate currency does not match the need")
        if deal.intent.product.category not in deal.mandate.allowed_categories:
            reasons.append("Category is outside the mandate")
        decision = "DENY" if reasons else "ALLOW"
        return ControlDecisionRecord(
            decision=decision,
            policy_version=deal.mandate.version,
            operation=operation,
            rule_ids=["mandate.active", "mandate.scope", "mandate.currency"],
            reasons=reasons,
        )

    async def process_approved_purchase(
        self,
        deal: DealRecord,
        quote: Quote,
        snapshot: ApprovalSnapshot,
        human_decision: HumanDecisionRecord,
        *,
        idempotency_key: str,
    ) -> ApprovedPurchaseArtifacts:
        async with self._payment_lock:
            cached = self._purchase_results.get(idempotency_key)
            if cached is not None:
                return cached
        policies = [
            self.check_mandate(deal, operation)
            for operation in (
                "create_purchase_intent",
                "anchor_intent",
                "oracle_process",
                "create_payment_draft",
            )
        ]
        policy = policies[0]
        if any(item.decision != "ALLOW" for item in policies):
            raise TrustControlError("Approved purchase denied by mandate policy")
        if human_decision.snapshot_hash != snapshot.snapshot_hash:
            raise TrustControlError("Approval hash mismatch")
        supplier = self._supplier(quote.supplier_id)
        recipient_binding_hash = supplier.bank_binding_hash
        purchase_intent = PurchaseIntentRecord(
            deal_id=deal.deal_id,
            approved_snapshot_hash=snapshot.snapshot_hash,
            buyer_agent_id=deal.mandate.agent_id,
            supplier_agent_id=quote.supplier_id,
            amount=quote.total_cost,
            currency=quote.currency,
            recipient_binding_hash=recipient_binding_hash,
        )
        anchor = await self._anchor.append(
            deal.deal_id,
            purchase_intent.model_dump(mode="json"),
        )
        checks = {
            "anchor_integrity": await self._anchor.verify(deal.deal_id),
            "intent_hash": anchor.payload_hash == payload_hash(purchase_intent),
            "approval_hash": purchase_intent.approved_snapshot_hash == snapshot.snapshot_hash,
            "buyer_active": True,
            "supplier_active": supplier.status == "active",
            "mandate": all(item.decision == "ALLOW" for item in policies),
            "recipient_binding": purchase_intent.recipient_binding_hash
            == supplier.bank_binding_hash,
            "amount": purchase_intent.amount <= deal.mandate.max_total,
            "currency": purchase_intent.currency == deal.mandate.currency,
        }
        fraud = ControlDecisionRecord(
            decision="ALLOW" if all(checks.values()) else "FREEZE",
            policy_version=deal.mandate.version,
            operation="oracle_verify",
            rule_ids=list(checks),
            reasons=[name for name, passed in checks.items() if not passed],
        )
        oracle = OracleVerificationRecord(
            purchase_intent_id=purchase_intent.intent_id,
            verified=all(checks.values()),
            checks=checks,
            fraud_decision=fraud,
        )
        if not oracle.verified:
            raise TrustControlError("Oracle verification failed")
        if self._runtime.security.financial_kill_switch:
            raise TrustControlError("Financial kill switch is active")
        async with self._payment_lock:
            existing = self._payment_results.get(idempotency_key)
            if existing is None:
                existing = PaymentDraft(
                    payment_draft_id=uuid4(),
                    order_id=uuid4(),
                    amount=quote.total_cost,
                    currency=quote.currency,
                    payee_supplier_id=quote.supplier_id,
                    status=PaymentDraftStatus.AWAITING_CUSTOMER_SIGNATURE,
                    recipient_binding_hash=recipient_binding_hash,
                    requires_human_signature=True,
                )
                self._payment_results[idempotency_key] = existing
        result = ApprovedPurchaseArtifacts(
            purchase_intent=purchase_intent,
            anchor=anchor,
            oracle=oracle,
            payment_draft=existing,
            policy_decision=policy,
            fraud_decision=fraud,
        )
        async with self._payment_lock:
            self._purchase_results[idempotency_key] = result
        return result

    async def verify_ledger(self, deal_id: UUID) -> bool:
        return await self._anchor.verify(deal_id)
