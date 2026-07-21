from __future__ import annotations

import asyncio
import os
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

from sber_a2a.config import Settings
from sber_a2a.domain.models import Mandate, ProcurementIntent, ProductRequest, RankingWeights
from sber_a2a.shared.security.envelopes import FilesystemKeyStore
from sber_a2a.shared.security.outbound import OutboundPolicy
from sber_a2a.suppliers.remote import RemoteSupplierAgent


async def main() -> None:
    settings = Settings(_env_file=None)
    runtime = settings.runtime
    profile = runtime.profile
    ranking = runtime.ranking
    endpoints = [item.strip() for item in os.environ["SMOKE_ENDPOINTS"].split(",")]
    seeds = runtime.suppliers[: len(endpoints)]
    if len(endpoints) < runtime.profile.minimum_quotes or len(seeds) != len(endpoints):
        raise RuntimeError("Smoke requires configured endpoints for the minimum A2 count")
    key_store = FilesystemKeyStore(settings.effective_keys_directory)
    outbound = OutboundPolicy(
        allowed_schemes=frozenset(runtime.network.allowed_schemes),
        allowed_ports=frozenset(runtime.network.allowed_ports),
        allow_private_networks=runtime.network.allow_private_networks,
    )
    agents = [
        RemoteSupplierAgent(
            seed.agent_id,
            endpoint,
            name=seed.name,
            categories=set(seed.categories),
            timeout_seconds=runtime.network.read_timeout_seconds,
            max_attempts=runtime.network.max_attempts,
            buyer_agent_id=profile.buyer_agent_id,
            audience=runtime.oidc.audience,
            envelope_ttl_seconds=runtime.security.nonce_ttl_seconds,
            key_store=key_store,
            outbound_policy=outbound,
        )
        for seed, endpoint in zip(seeds, endpoints, strict=True)
    ]
    now = datetime.now(UTC)
    intent = ProcurementIntent(
        customer_id=profile.buyer_organization_id,
        product=ProductRequest(
            sku=profile.default_sku,
            name=profile.default_product_name,
            category=profile.default_category,
            quantity=profile.default_quantity,
        ),
        delivery_city=profile.delivery_city,
        delivery_by=date.today() + timedelta(days=profile.delivery_days),
        max_total=profile.default_maximum_amount,
        currency=profile.default_currency,
        weights=RankingWeights(
            price=ranking.price,
            delivery=ranking.delivery,
            warranty=ranking.warranty,
            risk=ranking.risk,
            payment_terms=ranking.payment_terms,
        ),
    )
    mandate = Mandate(
        customer_id=profile.buyer_organization_id,
        organization_id=profile.buyer_organization_id,
        agent_id=profile.buyer_agent_id,
        issuer=profile.mandate_issuer,
        authorized_by=profile.approver_subject,
        allowed_actions=set(profile.allowed_actions),
        forbidden_actions=set(profile.forbidden_actions),
        allowed_categories={profile.default_category},
        max_total=profile.default_maximum_amount,
        cumulative_amount=0,
        currency=profile.default_currency,
        valid_from=now - timedelta(minutes=1),
        expires_at=now + timedelta(hours=profile.mandate_validity_hours),
        required_approvals={profile.approval_role},
        signature=profile.mandate_signature,
        version=profile.mandate_version,
    )
    deal_id = uuid4()
    quotes = await asyncio.gather(
        *(agent.create_quote(intent, mandate=mandate, deal_id=deal_id) for agent in agents)
    )
    received = [quote for quote in quotes if quote is not None]
    if {quote.supplier_id for quote in received} != {seed.agent_id for seed in seeds}:
        raise RuntimeError("Not every direct A2 endpoint returned a verified signed Quote")
    print(
        {
            "deal_id": str(deal_id),
            "verified_signed_quotes": [
                {
                    "supplier_id": quote.supplier_id,
                    "quote_id": str(quote.quote_id),
                    "total_cost": str(quote.total_cost),
                }
                for quote in received
            ],
        }
    )


if __name__ == "__main__":
    asyncio.run(main())
