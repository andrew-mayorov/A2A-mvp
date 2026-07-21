from __future__ import annotations

import json
import secrets
from datetime import timedelta
from pathlib import Path
from uuid import UUID, uuid4

from sber_a2a.domain.contracts import SignedEnvelope, utc_now
from sber_a2a.shared.security.signatures import (
    Ed25519SignatureProvider,
    payload_hash,
)


class EnvelopeVerificationError(ValueError):
    pass


class FilesystemKeyStore:
    def __init__(self, directory: str | Path) -> None:
        self._directory = Path(directory)
        self._index = json.loads((self._directory / "key_index.json").read_text(encoding="utf-8"))

    def provider(self, agent_id: str, *, signing: bool) -> Ed25519SignatureProvider:
        entry = self._index.get(agent_id)
        if entry is None:
            raise EnvelopeVerificationError("Agent key is absent from the registry")
        return Ed25519SignatureProvider.from_files(
            entry["key_id"],
            private_key_path=entry["private_key"] if signing else None,
            public_key_path=entry["public_key"],
        )


def _unsigned(envelope: SignedEnvelope) -> dict:
    return envelope.model_dump(mode="json", exclude={"signature"})


def create_envelope(
    *,
    payload: dict,
    schema_name: str,
    schema_version: str,
    deal_id: UUID,
    sender_agent_id: str,
    recipient_agent_id: str,
    mandate_id: UUID,
    operation: str,
    purpose: str,
    audience: str,
    ttl_seconds: int,
    signer: Ed25519SignatureProvider,
    correlation_id: UUID | None = None,
    causation_id: UUID | None = None,
    idempotency_key: str | None = None,
) -> SignedEnvelope:
    created_at = utc_now()
    provisional = SignedEnvelope(
        schema_name=schema_name,
        schema_version=schema_version,
        correlation_id=correlation_id or uuid4(),
        causation_id=causation_id,
        deal_id=deal_id,
        sender_agent_id=sender_agent_id,
        recipient_agent_id=recipient_agent_id,
        mandate_id=mandate_id,
        key_id=signer.key_id,
        operation=operation,
        purpose=purpose,
        audience=audience,
        created_at=created_at,
        expires_at=created_at + timedelta(seconds=ttl_seconds),
        nonce=secrets.token_urlsafe(24),
        idempotency_key=idempotency_key or f"{deal_id}:{operation}:{uuid4()}",
        payload_hash=payload_hash(payload),
        payload=payload,
        signature="pending",
    )
    return provisional.model_copy(update={"signature": signer.sign(_unsigned(provisional))})


def verify_envelope(
    envelope: SignedEnvelope,
    *,
    verifier: Ed25519SignatureProvider,
    expected_recipient: str,
    expected_audience: str,
) -> None:
    if envelope.expires_at <= utc_now():
        raise EnvelopeVerificationError("Envelope has expired")
    if envelope.recipient_agent_id != expected_recipient:
        raise EnvelopeVerificationError("Envelope recipient binding is invalid")
    if envelope.audience != expected_audience:
        raise EnvelopeVerificationError("Envelope audience binding is invalid")
    if envelope.payload_hash != payload_hash(envelope.payload):
        raise EnvelopeVerificationError("Envelope payload hash is invalid")
    if envelope.key_id != verifier.key_id:
        raise EnvelopeVerificationError("Envelope key ID is invalid")
    if not verifier.verify(_unsigned(envelope), envelope.signature):
        raise EnvelopeVerificationError("Envelope signature is invalid")
