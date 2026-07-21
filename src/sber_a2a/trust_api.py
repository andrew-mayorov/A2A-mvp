from __future__ import annotations

from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse

from sber_a2a.config import Settings
from sber_a2a.trust_infrastructure.ledger import DatabaseHashChainAnchor
from sber_a2a.trust_infrastructure.service import TrustedInfrastructureService


def create_trust_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    runtime = settings.runtime
    ledger = DatabaseHashChainAnchor(settings.database_url)
    service = TrustedInfrastructureService(runtime, ledger)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        await ledger.initialize()
        yield
        await ledger.close()

    app = FastAPI(
        title="Trusted Infrastructure API",
        version="0.3.0",
        description=(
            "Registry, mandate, policy, fraud, ledger, oracle, approval and payment "
            "controls. This service is not an A2A negotiating agent."
        ),
        lifespan=lifespan,
    )
    app.state.trust_service = service

    @app.get("/health")
    async def health() -> dict:
        return {
            "status": "ok",
            "role": "Trusted Infrastructure",
            "negotiating_agent": False,
            "llm_authoritative": False,
        }

    @app.get("/ready")
    async def ready() -> dict:
        try:
            await ledger.initialize()
            database_ready = True
        except Exception:
            database_ready = False
        registry_ready = sum(item.status == "active" for item in runtime.suppliers) >= 2
        return {
            "status": "ready" if database_ready and registry_ready else "degraded",
            "checks": {
                "database": database_ready,
                "registry": registry_ready,
                "financial_kill_switch": runtime.security.financial_kill_switch,
            },
        }

    @app.get("/metrics", response_class=PlainTextResponse)
    async def metrics() -> PlainTextResponse:
        active = sum(item.status == "active" for item in runtime.suppliers)
        return PlainTextResponse(
            content=(
                "# TYPE a2a_registry_active_agents gauge\n"
                f"a2a_registry_active_agents {active}\n"
                "# TYPE a2a_financial_kill_switch gauge\n"
                f"a2a_financial_kill_switch "
                f"{int(runtime.security.financial_kill_switch)}\n"
            ),
            media_type="text/plain; version=0.0.4",
        )

    @app.get("/api/v1/registry/agents")
    async def agents() -> list[dict]:
        return [
            {
                "agent_id": item.agent_id,
                "organization_id": item.organization_id,
                "name": item.name,
                "role": "A2",
                "endpoint": item.endpoint,
                "categories": item.categories,
                "status": item.status,
                "risk_tier": item.risk_tier,
                "bank_binding_hash": item.bank_binding_hash,
            }
            for item in runtime.suppliers
        ]

    @app.get("/api/v1/ledger/deals/{deal_id}/integrity")
    async def ledger_integrity(deal_id: UUID) -> dict:
        anchors = await ledger.list(deal_id)
        if not anchors:
            raise HTTPException(status_code=404, detail="Ledger chain not found")
        return {
            "deal_id": str(deal_id),
            "integrity_valid": await ledger.verify(deal_id),
            "anchors": [item.model_dump(mode="json") for item in anchors],
        }

    return app


def run() -> None:
    import uvicorn

    settings = Settings()
    uvicorn.run(create_trust_app(settings), host=settings.app_host, port=settings.app_port)


app = create_trust_app()
