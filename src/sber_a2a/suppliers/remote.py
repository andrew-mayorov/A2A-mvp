import asyncio
from uuid import UUID, uuid4

import httpx
from a2a.client import ClientCallContext, ClientConfig, ClientFactory
from a2a.types.a2a_pb2 import Message, Part, Role, SendMessageRequest
from google.protobuf.json_format import MessageToDict
from google.protobuf.struct_pb2 import Struct, Value

from sber_a2a.domain.contracts import SignedEnvelope
from sber_a2a.domain.models import Mandate, ProcurementIntent, Quote, SupplierSummary
from sber_a2a.shared.security.envelopes import (
    FilesystemKeyStore,
    create_envelope,
    verify_envelope,
)
from sber_a2a.shared.security.outbound import OutboundPolicy


class RemoteSupplierAgent:
    def __init__(
        self,
        supplier_id: str,
        endpoint: str,
        *,
        name: str | None = None,
        categories: set[str],
        timeout_seconds: float,
        max_attempts: int,
        buyer_agent_id: str | None = None,
        audience: str | None = None,
        envelope_ttl_seconds: int | None = None,
        key_store: FilesystemKeyStore | None = None,
        outbound_policy: OutboundPolicy | None = None,
    ) -> None:
        self._endpoint = endpoint.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._max_attempts = max_attempts
        self._buyer_agent_id = buyer_agent_id
        self._audience = audience
        self._envelope_ttl_seconds = envelope_ttl_seconds
        self._key_store = key_store
        self._outbound_policy = outbound_policy
        self._summary = SupplierSummary(
            supplier_id=supplier_id,
            name=name or supplier_id,
            categories=categories,
        )

    @property
    def summary(self) -> SupplierSummary:
        return self._summary

    async def create_quote(
        self,
        intent: ProcurementIntent,
        *,
        mandate: Mandate | None = None,
        deal_id: UUID | None = None,
    ) -> Quote | None:
        if mandate is None or deal_id is None:
            raise ValueError("Remote A2A RFQ requires a mandate and deal ID")
        if (
            self._buyer_agent_id is None
            or self._audience is None
            or self._envelope_ttl_seconds is None
            or self._key_store is None
            or self._outbound_policy is None
        ):
            raise ValueError("Remote A2A security dependencies are not configured")
        last_error: Exception | None = None
        for attempt in range(1, self._max_attempts + 1):
            try:
                return await self._request_quote(intent, mandate, deal_id)
            except (httpx.HTTPError, TimeoutError, ValueError) as exc:
                last_error = exc
                if attempt < self._max_attempts:
                    await asyncio.sleep(0.1 * attempt)
        if last_error is None:
            raise RuntimeError("Remote quote request exhausted without a result")
        raise last_error

    async def _request_quote(
        self,
        intent: ProcurementIntent,
        mandate: Mandate,
        deal_id: UUID,
    ) -> Quote | None:
        outbound_policy = self._outbound_policy
        key_store = self._key_store
        buyer_agent_id = self._buyer_agent_id
        audience = self._audience
        envelope_ttl_seconds = self._envelope_ttl_seconds
        if (
            outbound_policy is None
            or key_store is None
            or buyer_agent_id is None
            or audience is None
            or envelope_ttl_seconds is None
        ):
            raise ValueError("Remote A2A security dependencies are not configured")
        await outbound_policy.validate_url(self._endpoint)
        signer = key_store.provider(buyer_agent_id, signing=True)
        envelope = create_envelope(
            payload=intent.model_dump(mode="json"),
            schema_name="a2a.procurement.rfq",
            schema_version="1.0.0",
            deal_id=deal_id,
            sender_agent_id=buyer_agent_id,
            recipient_agent_id=self.summary.supplier_id,
            mandate_id=mandate.mandate_id,
            operation="send_rfq",
            purpose="request_supplier_quote",
            audience=audience,
            ttl_seconds=envelope_ttl_seconds,
            signer=signer,
            idempotency_key=f"{deal_id}:rfq:{self.summary.supplier_id}",
        )
        data = Struct()
        data.update({"signed_envelope_json": envelope.model_dump_json()})
        async with httpx.AsyncClient(
            timeout=self._timeout_seconds,
            trust_env=False,
            follow_redirects=False,
        ) as http:
            factory = ClientFactory(
                ClientConfig(
                    streaming=False,
                    httpx_client=http,
                    supported_protocol_bindings=["JSONRPC"],
                )
            )
            client = await factory.create_from_url(self._endpoint)
            request = SendMessageRequest(
                message=Message(
                    message_id=str(uuid4()),
                    role=Role.ROLE_USER,
                    parts=[
                        Part(
                            data=Value(struct_value=data),
                            media_type="application/json",
                        )
                    ],
                )
            )
            quote_payload: dict | None = None
            async for response in client.send_message(
                request,
                context=ClientCallContext(timeout=self._timeout_seconds),
            ):
                if not response.HasField("task"):
                    continue
                for artifact in response.task.artifacts:
                    for part in artifact.parts:
                        if part.HasField("data"):
                            quote_payload = MessageToDict(
                                part.data,
                                preserving_proto_field_name=True,
                            )
            await client.close()

        if quote_payload is None:
            raise ValueError("Supplier returned no quote artifact")
        if quote_payload.get("status") == "no_quote":
            return None
        response_envelope_json = quote_payload.get("signed_envelope_json")
        if not isinstance(response_envelope_json, str):
            raise ValueError("Supplier returned no signed Quote envelope")
        response_envelope = SignedEnvelope.model_validate_json(response_envelope_json)
        verifier = key_store.provider(self.summary.supplier_id, signing=False)
        verify_envelope(
            response_envelope,
            verifier=verifier,
            expected_recipient=buyer_agent_id,
            expected_audience=audience,
        )
        if response_envelope.correlation_id != envelope.correlation_id:
            raise ValueError("Supplier quote correlation ID does not match RFQ")
        return Quote.model_validate(response_envelope.payload)
