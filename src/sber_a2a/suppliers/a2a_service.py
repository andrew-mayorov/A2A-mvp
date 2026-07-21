from typing import Any
from uuid import uuid4

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events.event_queue_v2 import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import (
    add_a2a_routes_to_fastapi,
    create_agent_card_routes,
    create_jsonrpc_routes,
    create_rest_routes,
)
from a2a.server.tasks import InMemoryTaskStore
from a2a.types.a2a_pb2 import (
    AgentCapabilities,
    AgentCard,
    AgentInterface,
    AgentSkill,
    Artifact,
    Part,
    Task,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
)
from fastapi import FastAPI
from google.protobuf.json_format import MessageToDict
from google.protobuf.struct_pb2 import Struct, Value
from google.protobuf.timestamp_pb2 import Timestamp

from sber_a2a.config import Settings
from sber_a2a.domain.contracts import SignedEnvelope
from sber_a2a.domain.models import ProcurementIntent
from sber_a2a.shared.security.envelopes import (
    FilesystemKeyStore,
    create_envelope,
    verify_envelope,
)
from sber_a2a.suppliers.mock import MockSupplierAgent, load_catalog_supplier


def _now() -> Timestamp:
    value = Timestamp()
    value.GetCurrentTime()
    return value


def _data_part(value: dict) -> Part:
    data = Struct()
    data.update(value)
    return Part(data=Value(struct_value=data), media_type="application/json")


class SupplierQuoteExecutor(AgentExecutor):
    def __init__(
        self,
        supplier: MockSupplierAgent,
        *,
        key_store: FilesystemKeyStore,
        audience: str,
        envelope_ttl_seconds: int,
    ) -> None:
        self._supplier = supplier
        self._key_store = key_store
        self._audience = audience
        self._envelope_ttl_seconds = envelope_ttl_seconds

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        task_id = context.task_id or str(uuid4())
        context_id = context.context_id or str(uuid4())
        message = context.message
        if message is None:
            raise ValueError("A procurement intent message is required")
        data_parts = [part.data for part in message.parts if part.HasField("data")]
        if not data_parts:
            raise ValueError("A structured procurement intent part is required")

        envelope_data = MessageToDict(data_parts[0], preserving_proto_field_name=True)
        envelope_json = envelope_data.get("signed_envelope_json")
        if not isinstance(envelope_json, str):
            raise ValueError("A signed RFQ envelope is required")
        envelope = SignedEnvelope.model_validate_json(envelope_json)
        verifier = self._key_store.provider(envelope.sender_agent_id, signing=False)
        verify_envelope(
            envelope,
            verifier=verifier,
            expected_recipient=self._supplier.summary.supplier_id,
            expected_audience=self._audience,
        )
        if envelope.operation != "send_rfq":
            raise ValueError("Unsupported signed envelope operation")
        intent = ProcurementIntent.model_validate(envelope.payload)
        await event_queue.enqueue_event(
            Task(
                id=task_id,
                context_id=context_id,
                status=TaskStatus(
                    state=TaskState.TASK_STATE_WORKING,
                    timestamp=_now(),
                ),
                history=[message],
            )
        )

        quote = await self._supplier.create_quote(intent)
        artifact_payload: dict[str, Any]
        if quote is None:
            artifact_payload = {"status": "no_quote"}
        else:
            signer = self._key_store.provider(
                self._supplier.summary.supplier_id,
                signing=True,
            )
            response_envelope = create_envelope(
                payload=quote.model_dump(mode="json"),
                schema_name="a2a.procurement.quote",
                schema_version="1.0.0",
                deal_id=envelope.deal_id,
                sender_agent_id=self._supplier.summary.supplier_id,
                recipient_agent_id=envelope.sender_agent_id,
                mandate_id=envelope.mandate_id,
                operation="return_quote",
                purpose="supplier_quote_response",
                audience=self._audience,
                ttl_seconds=self._envelope_ttl_seconds,
                signer=signer,
                correlation_id=envelope.correlation_id,
                causation_id=envelope.message_id,
                idempotency_key=f"{envelope.idempotency_key}:quote",
            )
            artifact_payload = {
                "status": "quoted",
                "signed_envelope_json": response_envelope.model_dump_json(),
            }
        await event_queue.enqueue_event(
            TaskArtifactUpdateEvent(
                task_id=task_id,
                context_id=context_id,
                artifact=Artifact(
                    artifact_id=str(uuid4()),
                    name="sber.procurement.quote.v1",
                    parts=[_data_part(artifact_payload)],
                ),
                last_chunk=True,
            )
        )
        await event_queue.enqueue_event(
            TaskStatusUpdateEvent(
                task_id=task_id,
                context_id=context_id,
                status=TaskStatus(
                    state=TaskState.TASK_STATE_COMPLETED,
                    timestamp=_now(),
                ),
            )
        )

    async def cancel(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        await event_queue.enqueue_event(
            TaskStatusUpdateEvent(
                task_id=context.task_id,
                context_id=context.context_id,
                status=TaskStatus(
                    state=TaskState.TASK_STATE_CANCELED,
                    timestamp=_now(),
                ),
            )
        )


def create_supplier_app(
    supplier_id: str | None = None,
    *,
    public_url: str | None = None,
    settings: Settings | None = None,
) -> FastAPI:
    settings = settings or Settings()
    configured_id = supplier_id or settings.supplier_id
    seeds = settings.supplier_seeds
    if configured_id is None:
        if not seeds:
            raise RuntimeError("No supplier is configured")
        configured_id = seeds[0].agent_id
    seed = next((item for item in seeds if item.agent_id == configured_id), None)
    if seed is None:
        raise RuntimeError("SUPPLIER_ID is not present in the runtime configuration")
    public_url = (public_url or settings.public_url or seed.endpoint).rstrip("/")
    supplier = load_catalog_supplier(
        seed.agent_id,
        seed.catalog_file,
        trusted_risk=seed.risk,
        categories=set(seed.categories),
    )
    key_store = FilesystemKeyStore(settings.effective_keys_directory)
    card = AgentCard(
        name=supplier.summary.name,
        description=f"Demo A2 supplier agent owned by {supplier.summary.name}",
        supported_interfaces=[
            AgentInterface(
                url=f"{public_url}/a2a",
                protocol_binding="JSONRPC",
                protocol_version="1.0",
            ),
            AgentInterface(
                url=public_url,
                protocol_binding="HTTP+JSON",
                protocol_version="1.0",
            ),
        ],
        version="0.2.0",
        capabilities=AgentCapabilities(streaming=False),
        default_input_modes=["application/json"],
        default_output_modes=["application/json"],
        skills=[
            AgentSkill(
                id="procurement-rfq",
                name="Create supplier quote",
                description="Accept a structured RFQ and return a quote artifact.",
                tags=["procurement", "rfq", "mro"],
            )
        ],
    )
    handler = DefaultRequestHandler(
        agent_executor=SupplierQuoteExecutor(
            supplier,
            key_store=key_store,
            audience=settings.runtime.oidc.audience,
            envelope_ttl_seconds=settings.runtime.security.nonce_ttl_seconds,
        ),
        task_store=InMemoryTaskStore(),
        agent_card=card,
    )
    app = FastAPI(
        title=f"A2 Supplier Agent — {supplier.summary.name}",
        version="0.2.0",
    )

    @app.get("/health")
    async def health() -> dict:
        return {
            "status": "ok",
            "role": "A2",
            "supplier_id": supplier.summary.supplier_id,
        }

    add_a2a_routes_to_fastapi(
        app,
        agent_card_routes=create_agent_card_routes(card),
        jsonrpc_routes=create_jsonrpc_routes(handler, rpc_url="/a2a"),
        rest_routes=create_rest_routes(handler),
    )
    return app


def run() -> None:
    import uvicorn

    settings = Settings()
    uvicorn.run(
        create_supplier_app(settings=settings),
        host=settings.app_host,
        port=settings.app_port,
    )
