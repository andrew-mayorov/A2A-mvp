import hashlib
import json
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator


def utc_now() -> datetime:
    return datetime.now(UTC)


Money = Annotated[Decimal, Field(ge=Decimal("0"), decimal_places=2)]
Score = Annotated[Decimal, Field(ge=Decimal("0"), le=Decimal("100"))]


class DealStatus(StrEnum):
    DRAFT = "draft"
    AWAITING_APPROVAL = "awaiting_approval"
    ORDER_CREATED = "order_created"
    FULFILLING = "fulfilling"
    COMPLETED = "completed"
    FAILED = "failed"
    REJECTED = "rejected"
    CHANGES_REQUESTED = "changes_requested"
    PAYMENT_SIGNATURE_REQUIRED = "payment_signature_required"


class HumanDecisionKind(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
    REQUEST_CHANGES = "request_changes"


class OrderStatus(StrEnum):
    AWARDED = "awarded"
    CONFIRMED_BY_SUPPLIER = "confirmed_by_supplier"


class PaymentDraftStatus(StrEnum):
    CREATED = "created"
    AWAITING_CUSTOMER_SIGNATURE = "awaiting_customer_signature"
    SIGNED = "signed"
    HELD = "held"


class FulfillmentStatus(StrEnum):
    ORDER_CONFIRMED = "order_confirmed"
    PACKED = "packed"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    DOCUMENTS_READY = "documents_ready"
    COMPLETED = "completed"


class RankingWeights(BaseModel):
    price: Decimal
    delivery: Decimal
    warranty: Decimal
    risk: Decimal
    payment_terms: Decimal

    @model_validator(mode="after")
    def validate_sum(self) -> "RankingWeights":
        values = (
            self.price,
            self.delivery,
            self.warranty,
            self.risk,
            self.payment_terms,
        )
        if any(value < 0 for value in values):
            raise ValueError("Ranking weights cannot be negative")
        if abs(sum(values) - Decimal("1")) > Decimal("0.0001"):
            raise ValueError("Ranking weights must sum to 1")
        return self


class ProductRequest(BaseModel):
    sku: str = Field(min_length=2, max_length=100)
    name: str = Field(min_length=2, max_length=500)
    category: str = Field(min_length=2)
    quantity: int = Field(gt=0, le=100_000)


class ProcurementIntent(BaseModel):
    customer_id: str = Field(min_length=2, max_length=100)
    product: ProductRequest
    delivery_city: str = Field(min_length=2, max_length=200)
    delivery_by: date
    max_total: Money | None = None
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    weights: RankingWeights


class Mandate(BaseModel):
    mandate_id: UUID = Field(default_factory=uuid4)
    customer_id: str
    organization_id: str
    agent_id: str
    issuer: str
    authorized_by: str = Field(min_length=2, max_length=100)
    allowed_actions: set[str]
    forbidden_actions: set[str]
    allowed_categories: set[str]
    max_total: Money
    cumulative_amount: Money
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    valid_from: datetime
    expires_at: datetime
    allowed_supplier_ids: set[str] | None = None
    requires_human_approval: bool = True
    required_approvals: set[str]
    revoked_at: datetime | None = None
    signature: str
    version: str

    def permits(self, action: str, *, now: datetime | None = None) -> bool:
        current = now or utc_now()
        return (
            self.revoked_at is None
            and self.valid_from <= current < self.expires_at
            and action in self.allowed_actions
            and action not in self.forbidden_actions
        )


class CreateDealRequest(BaseModel):
    intent: ProcurementIntent
    mandate: Mandate

    @model_validator(mode="after")
    def customer_matches(self) -> "CreateDealRequest":
        if self.intent.customer_id != self.mandate.customer_id:
            raise ValueError("Intent and mandate must belong to the same customer")
        return self


class SupplierSummary(BaseModel):
    supplier_id: str
    name: str
    categories: set[str]
    active: bool = True


class Quote(BaseModel):
    quote_id: UUID = Field(default_factory=uuid4)
    supplier_id: str
    supplier_name: str
    sku: str
    product_name: str
    quantity: int = Field(gt=0)
    unit_price: Money
    delivery_fee: Money
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    vat_rate: Decimal
    delivery_days: int = Field(ge=0)
    warranty_months: int = Field(ge=0)
    supplier_risk: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    payment_delay_days: int = Field(ge=0)
    valid_until: datetime

    @property
    def goods_total(self) -> Decimal:
        return self.unit_price * self.quantity

    @property
    def total_cost(self) -> Decimal:
        return self.goods_total + self.delivery_fee


class ComponentScores(BaseModel):
    price: Score
    delivery: Score
    warranty: Score
    risk: Score
    payment_terms: Score


class EvaluatedQuote(BaseModel):
    quote: Quote
    eligible: bool
    rejection_reasons: list[str] = Field(default_factory=list)
    scores: ComponentScores | None = None
    total_score: Score | None = None


class Comparison(BaseModel):
    evaluated_quotes: list[EvaluatedQuote]
    recommended_quote_id: UUID | None
    explanation: str
    ranking_version: str = "deterministic-v1"


class DealEvent(BaseModel):
    event_id: UUID = Field(default_factory=uuid4)
    event_type: str
    actor: str
    details: dict[str, Any] = Field(default_factory=dict)
    correlation_id: UUID = Field(default_factory=uuid4)
    causation_id: UUID | None = None
    message_id: UUID = Field(default_factory=uuid4)
    payload_hash: str | None = None
    created_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def set_payload_hash(self) -> "DealEvent":
        if self.payload_hash is None:
            payload = {
                "event_type": self.event_type,
                "actor": self.actor,
                "details": self.details,
            }
            encoded = json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            ).encode()
            self.payload_hash = hashlib.sha256(encoded).hexdigest()
        return self


class ApprovalSnapshot(BaseModel):
    snapshot_id: UUID = Field(default_factory=uuid4)
    quote_id: UUID
    supplier_id: str
    supplier_name: str
    sku: str
    product_name: str
    quantity: int
    total_cost: Money
    currency: str
    delivery_days: int
    warranty_months: int
    payment_delay_days: int
    document_hashes: list[str] = Field(default_factory=list)
    bank_requisites_hash: str = Field(min_length=64, max_length=64)
    risk_summary: str
    policy_version: str
    ranking_version: str
    total_score: Score | None = None
    snapshot_hash: str
    created_at: datetime = Field(default_factory=utc_now)


class OrderState(BaseModel):
    order_id: UUID
    supplier_id: str
    quote_id: UUID
    status: OrderStatus
    confirmed_at: datetime | None = None


class PaymentDraft(BaseModel):
    payment_draft_id: UUID
    order_id: UUID
    amount: Money
    currency: str
    payee_supplier_id: str
    status: PaymentDraftStatus
    recipient_binding_hash: str = Field(min_length=64, max_length=64)
    requires_human_signature: bool = True
    created_at: datetime = Field(default_factory=utc_now)


class FulfillmentUpdate(BaseModel):
    status: FulfillmentStatus
    actor: str = "A2:supplier"
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class DocumentRef(BaseModel):
    document_id: UUID = Field(default_factory=uuid4)
    document_type: str
    title: str
    source: str
    sha256: str
    created_at: datetime = Field(default_factory=utc_now)


class DealRecord(BaseModel):
    deal_id: UUID
    status: DealStatus
    intent: ProcurementIntent
    mandate: Mandate
    supplier_ids: list[str] = Field(default_factory=list)
    quotes: list[Quote] = Field(default_factory=list)
    comparison: Comparison | None = None
    selected_quote_id: UUID | None = None
    order_id: UUID | None = None
    payment_draft_id: UUID | None = None
    approval_snapshot: ApprovalSnapshot | None = None
    order: OrderState | None = None
    payment_draft: PaymentDraft | None = None
    human_decision: "HumanDecisionRecord | None" = None
    purchase_intent: "PurchaseIntentRecord | None" = None
    ledger_anchor: "LedgerAnchorRecord | None" = None
    oracle_verification: "OracleVerificationRecord | None" = None
    policy_decisions: list["ControlDecisionRecord"] = Field(default_factory=list)
    fraud_decisions: list["ControlDecisionRecord"] = Field(default_factory=list)
    fulfillment: list[FulfillmentUpdate] = Field(default_factory=list)
    documents: list[DocumentRef] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    events: list[DealEvent] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ApprovalRequest(BaseModel):
    quote_id: UUID
    approved_by: str = Field(min_length=2, max_length=100)
    approval_snapshot_hash: str = Field(min_length=64, max_length=64)
    decision: HumanDecisionKind = HumanDecisionKind.APPROVE
    reason: str | None = Field(default=None, max_length=2000)


class ApprovalResult(BaseModel):
    deal_id: UUID
    status: DealStatus
    selected_quote_id: UUID
    order_id: UUID
    payment_draft_id: UUID
    approval_snapshot_hash: str


class PaymentSignatureRequest(BaseModel):
    signed_by: str = Field(min_length=2, max_length=100)
    payment_draft_id: UUID
    confirmation: bool
    signature_evidence: str | None = Field(default=None, max_length=4000)


class PaymentSignatureResult(BaseModel):
    deal_id: UUID
    payment_draft_id: UUID
    status: DealStatus
    payment_status: PaymentDraftStatus


class EvidenceBundle(BaseModel):
    deal: DealRecord
    events: list[DealEvent]
    approval_snapshot: ApprovalSnapshot | None
    order: OrderState | None
    payment_draft: PaymentDraft | None
    human_decision: "HumanDecisionRecord | None" = None
    purchase_intent: "PurchaseIntentRecord | None" = None
    ledger_anchor: "LedgerAnchorRecord | None" = None
    oracle_verification: "OracleVerificationRecord | None" = None
    policy_decisions: list["ControlDecisionRecord"] = Field(default_factory=list)
    fraud_decisions: list["ControlDecisionRecord"] = Field(default_factory=list)
    fulfillment: list[FulfillmentUpdate]
    documents: list[DocumentRef]
    outbox_messages: list["OutboxMessage"] = Field(default_factory=list)


class OutboxStatus(StrEnum):
    PENDING = "pending"
    PUBLISHED = "published"


class OutboxMessage(BaseModel):
    outbox_id: UUID = Field(default_factory=uuid4)
    aggregate_id: UUID
    recipient_agent_id: str
    message_type: str
    idempotency_key: str
    payload: dict[str, Any]
    status: OutboxStatus = OutboxStatus.PENDING
    attempts: int = 0
    correlation_id: UUID
    causation_id: UUID | None = None
    created_at: datetime = Field(default_factory=utc_now)
    published_at: datetime | None = None


class ParseIntentRequest(BaseModel):
    text: str = Field(min_length=10, max_length=10_000)


class ParsedIntentDraft(BaseModel):
    sku: str | None = None
    product_name: str
    category: str | None = None
    quantity: int = Field(gt=0)
    delivery_city: str | None = None
    delivery_by: date | None = None
    max_total: Decimal | None = Field(default=None, ge=0)


class OrganizationStatus(StrEnum):
    PENDING = "pending"
    VERIFIED = "verified"
    SUSPENDED = "suspended"


class AgentRegistrationStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REVOKED = "revoked"


class UpdateAgentStatusRequest(BaseModel):
    status: AgentRegistrationStatus


class AgentContractStatus(StrEnum):
    UNKNOWN = "unknown"
    PASSED = "passed"
    FAILED = "failed"


class AgentContractCheckResult(BaseModel):
    agent_id: str
    endpoint_url: str
    status: AgentContractStatus
    quote_received: bool = False
    message: str
    checked_at: datetime = Field(default_factory=utc_now)


class AgentHostingMode(StrEnum):
    MANAGED = "managed"
    EXTERNAL = "external"


class CreateOrganizationRequest(BaseModel):
    legal_name: str = Field(min_length=2, max_length=300)
    tax_id: str = Field(min_length=5, max_length=30)
    roles: set[str] = Field(default_factory=lambda: {"supplier"})


class Organization(BaseModel):
    organization_id: UUID = Field(default_factory=uuid4)
    legal_name: str
    tax_id: str
    roles: set[str]
    status: OrganizationStatus = OrganizationStatus.VERIFIED
    created_at: datetime = Field(default_factory=utc_now)


class RegisterSupplierAgentRequest(BaseModel):
    organization_id: UUID
    agent_id: str = Field(min_length=2, max_length=100)
    endpoint_url: str = Field(pattern=r"^https?://")
    categories: set[str] = Field(default_factory=lambda: {"mro.standardized"})
    hosting_mode: AgentHostingMode = AgentHostingMode.EXTERNAL


class AgentRegistration(BaseModel):
    registration_id: UUID = Field(default_factory=uuid4)
    organization_id: UUID
    agent_id: str
    role: str = "A2"
    endpoint_url: str
    categories: set[str]
    hosting_mode: AgentHostingMode
    status: AgentRegistrationStatus
    contract_status: AgentContractStatus = AgentContractStatus.UNKNOWN
    contract_error: str | None = None
    agent_card_snapshot: dict
    last_checked_at: datetime
    created_at: datetime = Field(default_factory=utc_now)


class HumanDecisionRecord(BaseModel):
    decision_id: UUID = Field(default_factory=uuid4)
    decision: HumanDecisionKind
    approver_subject: str
    organization_id: str
    role: str
    snapshot_hash: str = Field(min_length=64, max_length=64)
    authentication_context: dict[str, Any] = Field(default_factory=dict)
    reason: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class PurchaseIntentRecord(BaseModel):
    intent_id: UUID = Field(default_factory=uuid4)
    deal_id: UUID
    approved_snapshot_hash: str = Field(min_length=64, max_length=64)
    buyer_agent_id: str
    supplier_agent_id: str
    amount: Money
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    recipient_binding_hash: str = Field(min_length=64, max_length=64)
    created_at: datetime = Field(default_factory=utc_now)


class LedgerAnchorRecord(BaseModel):
    anchor_id: UUID = Field(default_factory=uuid4)
    deal_id: UUID
    sequence_number: int = Field(gt=0)
    previous_hash: str = Field(min_length=64, max_length=64)
    current_hash: str = Field(min_length=64, max_length=64)
    payload_hash: str = Field(min_length=64, max_length=64)
    created_at: datetime = Field(default_factory=utc_now)


class ControlDecisionRecord(BaseModel):
    decision: str
    policy_version: str
    operation: str
    rule_ids: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)


class OracleVerificationRecord(BaseModel):
    verification_id: UUID = Field(default_factory=uuid4)
    purchase_intent_id: UUID
    verified: bool
    checks: dict[str, bool]
    fraud_decision: ControlDecisionRecord
    created_at: datetime = Field(default_factory=utc_now)


DealRecord.model_rebuild()
ApprovalRequest.model_rebuild()
EvidenceBundle.model_rebuild()
