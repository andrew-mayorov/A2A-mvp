import asyncio

from httpx import ASGITransport, AsyncClient

from sber_a2a.api import create_app
from sber_a2a.config import Settings
from sber_a2a.container import build_container


async def test_health_and_buyer_agent_card(container) -> None:
    app = create_app(container)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        health = await client.get("/health")
        card = await client.get("/.well-known/agent-card.json")
    assert health.status_code == 200
    assert health.json() == {
        "status": "ok",
        "role": "A1 Buyer Agent",
        "llm_enabled": False,
        "llm_provider": "disabled",
    }
    assert card.status_code == 200
    assert card.json()["name"] == "A1 Buyer Procurement Agent"


async def test_agent_card_uses_configured_public_url() -> None:
    container = build_container(
        Settings(
            llm_provider="disabled",
            database_url="sqlite+aiosqlite:///:memory:",
            public_url="http://a1:8100",
            _env_file=None,
        )
    )
    app = create_app(container)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        card = await client.get("/.well-known/agent-card.json")
    interfaces = card.json()["supportedInterfaces"]
    assert interfaces[0]["url"] == "http://a1:8100/a2a"
    assert interfaces[1]["url"] == "http://a1:8100"


async def test_rest_deal_flow_requires_separate_payment_signature(
    container,
    deal_request,
) -> None:
    app = create_app(container)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post(
            "/api/v1/deals",
            json=deal_request.model_dump(mode="json"),
        )
        assert created.status_code == 202
        payload = created.json()
        for _ in range(50):
            payload = (await client.get(f"/api/v1/deals/{payload['deal_id']}")).json()
            if payload["status"] != "draft":
                break
            await asyncio.sleep(0.01)
        approved = await client.post(
            f"/api/v1/deals/{payload['deal_id']}/approve",
            json={
                "quote_id": payload["comparison"]["recommended_quote_id"],
                "approved_by": deal_request.mandate.authorized_by,
                "approval_snapshot_hash": payload["approval_snapshot"]["snapshot_hash"],
            },
        )
        assert approved.status_code == 200
        assert approved.json()["status"] == "payment_signature_required"
        before_signature = await client.get(f"/api/v1/deals/{payload['deal_id']}/evidence")
        assert before_signature.json()["fulfillment"] == []
        signed = await client.post(
            f"/api/v1/deals/{payload['deal_id']}/payment-signature",
            json={
                "signed_by": deal_request.mandate.authorized_by,
                "payment_draft_id": approved.json()["payment_draft_id"],
                "confirmation": True,
            },
        )
        evidence = await client.get(f"/api/v1/deals/{payload['deal_id']}/evidence")
    assert signed.status_code == 200
    assert signed.json()["status"] == "completed"
    assert evidence.json()["ledger_anchor"]["current_hash"]
    assert evidence.json()["oracle_verification"]["verified"] is True
    assert evidence.json()["payment_draft"]["status"] == "signed"
    assert evidence.json()["fulfillment"][-1]["status"] == "completed"


async def test_readiness_reports_database_and_suppliers(container) -> None:
    app = create_app(container)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.json()["checks"]["database"] is True
    assert response.json()["checks"]["active_suppliers"] >= 2


async def test_llm_endpoint_is_explicitly_unavailable_without_key(container) -> None:
    app = create_app(container)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/intents/parse",
            json={"text": "Купи 20 подшипников 6205-2RS с доставкой в Москву"},
        )
    assert response.status_code == 503
