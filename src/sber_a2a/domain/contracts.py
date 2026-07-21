from __future__ import annotations

import re
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

Money = Decimal
SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")


def utc_now() -> datetime:
    return datetime.now(UTC)


class StrictContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AgentStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REVOKED = "revoked"
    EXPIRED = "expired"


class Decision(StrEnum):
    ALLOW = "ALLOW"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    ESCALATE = "ESCALATE"
    DENY = "DENY"
    FREEZE = "FREEZE"


class HumanDecisionType(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
    REQUEST_CHANGES = "request_changes"


class PublicKeyReference(StrictContract):
    key_id: str
    algorithm: str
    public_key: str
    valid_from: datetime
    valid_until: datetime | None = None
    revoked_at: datetime | None = None


class AgentAttestation(StrictContract):
    attestation_id: UUID = Field(default_factory=uuid4)
    issuer: str
    subject_agent_id: str
    statement_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    issued_at: datetime
    expires_at: datetime
    signature: str


class AgentCardSnapshot(StrictContract):
    card_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    card: dict[str, Any]
    captured_at: datetime = Field(default_factory=utc_now)


class AgentPassport(StrictContract):
    schema_version: str
    agent_id: str
    organization_id: str
    owner_legal_name: str
    owner_tax_id: str
    operator: str
    role: str
    endpoint: str
    capabilities: frozenset[str]
    skills: frozenset[str]
    protocols: frozenset[str]
    tool_manifest_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    agent_card: AgentCardSnapshot
    keys: tuple[PublicKeyReference, ...]
    attestations: tuple[AgentAttestation, ...] = ()
    risk_tier: str
    status: AgentStatus
    valid_from: datetime
    valid_until: datetime
    revocation_reason: str | None = None


class Mandate(StrictContract):
    mandate_id: UUID = Field(default_factory=uuid4)
    version: str
    principal: str
    organization_id: str
    agent_id: str
    issuer: str
    allowed_actions: frozenset[str]
    forbidden_actions: frozenset[str]
    allowed_categories: frozenset[str]
    allowed_counterparties: frozenset[str]
    maximum_amount: Money = Field(ge=0, decimal_places=2)
    cumulative_amount: Money = Field(ge=0, decimal_places=2)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    valid_from: datetime
    valid_until: datetime
    required_approvals: tuple[str, ...]
    revoked_at: datetime | None = None
    signature: str

    def permits(self, action: str, *, now: datetime | None = None) -> bool:
        current = now or utc_now()
        return (
            self.revoked_at is None
            and self.valid_from <= current < self.valid_until
            and action in self.allowed_actions
            and action not in self.forbidden_actions
        )


class ToolRisk(StrEnum):
    READ_ONLY = "read_only"
    ANALYSIS = "analysis"
    DRAFT = "draft"
    COMMIT = "commit"
    LEGAL = "legal"
    FINANCIAL = "financial"
    CRITICAL = "critical"


class ToolDefinition(StrictContract):
    tool_id: str
    version: str
    owner: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    risk_level: ToolRisk
    side_effect: str
    oauth_scopes: frozenset[str]
    allowed_agent_roles: frozenset[str]
    required_mandate_actions: frozenset[str]
    requires_human_approval: bool
    timeout_seconds: Decimal = Field(gt=0)
    idempotency_strategy: str
    policy_hook: str
    audit_policy: str


class ToolManifest(StrictContract):
    manifest_id: str
    version: str
    owner: str
    tools: tuple[ToolDefinition, ...]
    manifest_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class SignedEnvelope(StrictContract):
    schema_name: str
    schema_version: str
    message_id: UUID = Field(default_factory=uuid4)
    correlation_id: UUID
    causation_id: UUID | None = None
    deal_id: UUID
    sender_agent_id: str
    recipient_agent_id: str
    mandate_id: UUID
    key_id: str
    operation: str
    purpose: str
    audience: str
    created_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime
    nonce: str = Field(min_length=16, max_length=256)
    idempotency_key: str = Field(min_length=8, max_length=256)
    payload_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    payload: dict[str, Any]
    signature: str

    @model_validator(mode="after")
    def expiry_is_after_creation(self) -> SignedEnvelope:
        if self.expires_at <= self.created_at:
            raise ValueError("Envelope expiry must be after creation")
        return self


class Need(StrictContract):
    need_id: UUID = Field(default_factory=uuid4)
    organization_id: str
    sku: str
    product_name: str
    category: str
    quantity: int = Field(gt=0)
    delivery_city: str
    delivery_by: date
    maximum_amount: Money = Field(ge=0, decimal_places=2)
    currency: str = Field(pattern=r"^[A-Z]{3}$")


class RFQ(StrictContract):
    rfq_id: UUID = Field(default_factory=uuid4)
    need: Need
    requested_documents: tuple[str, ...]


class QuoteLine(StrictContract):
    sku: str
    product_name: str
    quantity: int = Field(gt=0)
    unit_price: Money = Field(ge=0, decimal_places=2)
    tax_amount: Money = Field(ge=0, decimal_places=2)


class QuoteDocument(StrictContract):
    document_id: UUID = Field(default_factory=uuid4)
    document_type: str
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    media_type: str


class Quote(StrictContract):
    quote_id: UUID = Field(default_factory=uuid4)
    rfq_id: UUID
    supplier_agent_id: str
    lines: tuple[QuoteLine, ...]
    delivery_fee: Money = Field(ge=0, decimal_places=2)
    total_amount: Money = Field(ge=0, decimal_places=2)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    delivery_days: int = Field(ge=0)
    warranty_months: int = Field(ge=0)
    payment_delay_days: int = Field(ge=0)
    documents: tuple[QuoteDocument, ...]
    bank_requisites_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    valid_until: datetime


class QuoteValidationResult(StrictContract):
    quote_id: UUID
    valid: bool
    reasons: tuple[str, ...]
    checked_at: datetime = Field(default_factory=utc_now)


class ComparisonResult(StrictContract):
    ranking_version: str
    quote_ids: tuple[UUID, ...]
    scores: dict[UUID, Decimal]
    recommended_quote_id: UUID | None
    explanation: str


class ApprovalRequest(StrictContract):
    approval_request_id: UUID = Field(default_factory=uuid4)
    deal_id: UUID
    snapshot_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    requested_role: str
    requested_at: datetime = Field(default_factory=utc_now)


class ApprovalSnapshot(StrictContract):
    snapshot_id: UUID = Field(default_factory=uuid4)
    deal_id: UUID
    quote_id: UUID
    supplier_agent_id: str
    amount: Money = Field(ge=0, decimal_places=2)
    currency: str
    product: str
    quantity: int = Field(gt=0)
    delivery: str
    document_hashes: tuple[str, ...]
    bank_requisites_hash: str
    risk_summary: str
    policy_version: str
    ranking_version: str
    snapshot_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class HumanDecision(StrictContract):
    decision_id: UUID = Field(default_factory=uuid4)
    decision: HumanDecisionType
    approver_subject: str
    organization_id: str
    role: str
    authentication_context: dict[str, Any]
    snapshot_hash: str
    reason: str | None = None
    signature: str | None = None
    decided_at: datetime = Field(default_factory=utc_now)


class PurchaseIntent(StrictContract):
    intent_id: UUID = Field(default_factory=uuid4)
    deal_id: UUID
    approved_snapshot_hash: str
    buyer_agent_id: str
    supplier_agent_id: str
    amount: Money = Field(ge=0, decimal_places=2)
    currency: str
    recipient_binding_hash: str
    created_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime


class SupplierCommitment(StrictContract):
    commitment_id: UUID = Field(default_factory=uuid4)
    purchase_intent_id: UUID
    supplier_agent_id: str
    accepted: bool
    commitment_hash: str
    created_at: datetime = Field(default_factory=utc_now)


class LedgerAnchor(StrictContract):
    anchor_id: UUID = Field(default_factory=uuid4)
    deal_id: UUID
    sequence_number: int = Field(gt=0)
    previous_hash: str
    current_hash: str
    payload_hash: str
    created_at: datetime = Field(default_factory=utc_now)


class FraudDecision(StrictContract):
    decision: Decision
    policy_version: str
    rule_ids: tuple[str, ...]
    reasons: tuple[str, ...]
    decided_at: datetime = Field(default_factory=utc_now)


class PolicyDecision(FraudDecision):
    operation: str


class OracleVerification(StrictContract):
    verification_id: UUID = Field(default_factory=uuid4)
    purchase_intent_id: UUID
    verified: bool
    checks: dict[str, bool]
    fraud_decision: FraudDecision
    verified_at: datetime = Field(default_factory=utc_now)


class PaymentDraftRequest(StrictContract):
    request_id: UUID = Field(default_factory=uuid4)
    purchase_intent_id: UUID
    oracle_verification_id: UUID
    recipient_binding_hash: str
    amount: Money = Field(ge=0, decimal_places=2)
    currency: str
    idempotency_key: str


class PaymentDraft(StrictContract):
    payment_draft_id: UUID = Field(default_factory=uuid4)
    request_id: UUID
    status: str
    amount: Money
    currency: str
    recipient_binding_hash: str
    requires_human_signature: bool = True
    created_at: datetime = Field(default_factory=utc_now)


class DeliveryEvent(StrictContract):
    event_id: UUID = Field(default_factory=uuid4)
    deal_id: UUID
    status: str
    actor_agent_id: str
    evidence_hash: str
    occurred_at: datetime = Field(default_factory=utc_now)


class DocumentReference(StrictContract):
    document_id: UUID = Field(default_factory=uuid4)
    deal_id: UUID
    document_type: str
    content_hash: str
    storage_reference: str
    created_at: datetime = Field(default_factory=utc_now)


class EvidenceRecord(StrictContract):
    sequence_number: int = Field(gt=0)
    record_type: str
    payload_hash: str
    previous_hash: str
    current_hash: str
    occurred_at: datetime


class EvidenceBundle(StrictContract):
    schema_version: str
    deal_id: UUID
    organization_id: str
    records: tuple[EvidenceRecord, ...]
    integrity_valid: bool
    exported_at: datetime = Field(default_factory=utc_now)
