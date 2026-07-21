from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from sber_a2a.domain.contracts import Mandate, ToolDefinition, ToolRisk
from sber_a2a.shared.security.envelopes import (
    EnvelopeVerificationError,
    create_envelope,
    verify_envelope,
)
from sber_a2a.shared.security.outbound import OutboundPolicy, OutboundPolicyError
from sber_a2a.shared.security.signatures import Ed25519SignatureProvider, canonical_json
from sber_a2a.trust_infrastructure.tool_runtime import (
    ToolCaller,
    ToolRuntime,
    ToolRuntimeError,
)


def _mandate() -> Mandate:
    now = datetime.now(UTC)
    return Mandate(
        version="test-v1",
        principal="subject-1",
        organization_id="tenant-1",
        agent_id="agent-1",
        issuer="issuer-1",
        allowed_actions=frozenset({"read_catalog"}),
        forbidden_actions=frozenset({"execute_payment"}),
        allowed_categories=frozenset({"category-1"}),
        allowed_counterparties=frozenset({"agent-2"}),
        maximum_amount=Decimal("100.00"),
        cumulative_amount=Decimal("0.00"),
        currency="RUB",
        valid_from=now - timedelta(minutes=1),
        valid_until=now + timedelta(minutes=5),
        required_approvals=("approver",),
        signature="test-signature",
    )


def test_canonical_json_is_order_independent() -> None:
    assert canonical_json({"b": 2, "a": 1}) == canonical_json({"a": 1, "b": 2})


def test_forged_signed_envelope_is_rejected() -> None:
    signer = Ed25519SignatureProvider.generate("buyer-key-v1")
    attacker = Ed25519SignatureProvider.generate("attacker-key-v1")
    envelope = create_envelope(
        payload={"sku": "item-1"},
        schema_name="rfq",
        schema_version="1",
        deal_id=uuid4(),
        sender_agent_id="buyer",
        recipient_agent_id="supplier",
        mandate_id=uuid4(),
        operation="send_rfq",
        purpose="quote",
        audience="a2a",
        ttl_seconds=60,
        signer=signer,
    )
    forged = envelope.model_copy(update={"signature": attacker.sign({"forged": True})})
    with pytest.raises(EnvelopeVerificationError, match="signature"):
        verify_envelope(
            forged,
            verifier=signer,
            expected_recipient="supplier",
            expected_audience="a2a",
        )


async def test_outbound_policy_blocks_private_network_in_production(monkeypatch) -> None:
    def private_result(*_args, **_kwargs):
        return [(2, 1, 6, "", ("127.0.0.1", 443))]

    monkeypatch.setattr("socket.getaddrinfo", private_result)
    policy = OutboundPolicy(
        allowed_schemes=frozenset({"https"}),
        allowed_ports=frozenset({443}),
        allow_private_networks=False,
    )
    with pytest.raises(OutboundPolicyError, match="Private or loopback"):
        await policy.validate_url("https://supplier.example")


async def test_model_cannot_invoke_financial_tool() -> None:
    async def audit(_record):
        return None

    async def handler(_payload):
        return {"status": "created"}

    runtime = ToolRuntime(audit)
    runtime.register(
        ToolDefinition(
            tool_id="payment.create_draft",
            version="1",
            owner="payment-gatekeeper",
            description="Create a payment draft",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            risk_level=ToolRisk.FINANCIAL,
            side_effect="draft",
            oauth_scopes=frozenset({"payment:draft"}),
            allowed_agent_roles=frozenset({"buyer"}),
            required_mandate_actions=frozenset({"read_catalog"}),
            requires_human_approval=False,
            timeout_seconds=Decimal("1"),
            idempotency_strategy="key",
            policy_hook="payment",
            audit_policy="full",
        ),
        handler,
    )
    with pytest.raises(ToolRuntimeError, match="Models cannot invoke"):
        await runtime.execute(
            "payment.create_draft",
            "1",
            {},
            caller=ToolCaller(
                subject="model",
                tenant_id="tenant-1",
                agent_id="agent-1",
                agent_role="buyer",
                oauth_scopes=frozenset({"payment:draft"}),
                caller_kind="model",
            ),
            mandate=_mandate(),
            idempotency_key="test-idempotency-key",
        )
