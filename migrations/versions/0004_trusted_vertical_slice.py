"""Add tenant-scoped trusted infrastructure artifact stores.

Revision ID: 0004
Revises: 0003
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _artifact_table(name: str, id_column: str) -> None:
    op.create_table(
        name,
        sa.Column(id_column, sa.String(length=100), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("deal_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint(id_column),
    )
    op.create_index(f"ix_{name}_organization_id", name, ["organization_id"])
    op.create_index(f"ix_{name}_deal_id", name, ["deal_id"])
    op.create_index(f"ix_{name}_status", name, ["status"])


def _drop_artifact_table(name: str) -> None:
    op.drop_index(f"ix_{name}_status", table_name=name)
    op.drop_index(f"ix_{name}_deal_id", table_name=name)
    op.drop_index(f"ix_{name}_organization_id", table_name=name)
    op.drop_table(name)


def upgrade() -> None:
    _artifact_table("subjects", "subject_id")
    _artifact_table("agents", "agent_id")
    _artifact_table("agent_cards", "agent_card_id")
    _artifact_table("agent_keys", "key_id")
    _artifact_table("attestations", "attestation_id")
    _artifact_table("mandates", "mandate_id")
    _artifact_table("tool_manifests", "manifest_id")
    _artifact_table("rfqs", "rfq_id")
    _artifact_table("quotes", "quote_id")
    _artifact_table("quote_documents", "quote_document_id")
    _artifact_table("comparisons", "comparison_id")
    _artifact_table("approvals", "approval_id")
    _artifact_table("purchase_intents", "intent_id")
    _artifact_table("oracle_verifications", "verification_id")
    _artifact_table("payment_drafts", "payment_draft_id")
    _artifact_table("fulfillment_events", "fulfillment_event_id")
    _artifact_table("document_refs", "document_ref_id")
    _artifact_table("policy_decisions", "policy_decision_id")
    _artifact_table("fraud_decisions", "fraud_decision_id")

    op.create_table(
        "mandate_usage",
        sa.Column("usage_id", sa.String(length=36), nullable=False),
        sa.Column("mandate_id", sa.String(length=100), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("deal_id", sa.String(length=36), nullable=False),
        sa.Column("operation", sa.String(length=100), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("usage_id"),
        sa.UniqueConstraint("idempotency_key", name="uq_mandate_usage_idempotency"),
    )
    op.create_index("ix_mandate_usage_mandate_id", "mandate_usage", ["mandate_id"])
    op.create_index("ix_mandate_usage_deal_id", "mandate_usage", ["deal_id"])

    op.create_table(
        "ledger_anchors",
        sa.Column("anchor_id", sa.String(length=36), nullable=False),
        sa.Column("deal_id", sa.String(length=36), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("previous_hash", sa.String(length=64), nullable=False),
        sa.Column("current_hash", sa.String(length=64), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("anchor_id"),
        sa.UniqueConstraint("deal_id", "sequence_number", name="uq_anchor_deal_sequence"),
        sa.UniqueConstraint("deal_id", "current_hash", name="uq_anchor_deal_hash"),
    )
    op.create_index("ix_ledger_anchors_deal_id", "ledger_anchors", ["deal_id"])

    op.create_table(
        "inbox",
        sa.Column("message_id", sa.String(length=100), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("sender_agent_id", sa.String(length=100), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("message_id"),
    )
    op.create_index("ix_inbox_organization_id", "inbox", ["organization_id"])

    op.create_table(
        "idempotency_records",
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("operation", sa.String(length=100), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("response_payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("idempotency_key"),
    )
    op.create_index(
        "ix_idempotency_records_organization_id",
        "idempotency_records",
        ["organization_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_idempotency_records_organization_id",
        table_name="idempotency_records",
    )
    op.drop_table("idempotency_records")
    op.drop_index("ix_inbox_organization_id", table_name="inbox")
    op.drop_table("inbox")
    op.drop_index("ix_ledger_anchors_deal_id", table_name="ledger_anchors")
    op.drop_table("ledger_anchors")
    op.drop_index("ix_mandate_usage_deal_id", table_name="mandate_usage")
    op.drop_index("ix_mandate_usage_mandate_id", table_name="mandate_usage")
    op.drop_table("mandate_usage")
    for name in reversed(
        [
            "subjects",
            "agents",
            "agent_cards",
            "agent_keys",
            "attestations",
            "mandates",
            "tool_manifests",
            "rfqs",
            "quotes",
            "quote_documents",
            "comparisons",
            "approvals",
            "purchase_intents",
            "oracle_verifications",
            "payment_drafts",
            "fulfillment_events",
            "document_refs",
            "policy_decisions",
            "fraud_decisions",
        ]
    ):
        _drop_artifact_table(name)
