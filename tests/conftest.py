from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from sber_a2a.config import Settings
from sber_a2a.container import Container, build_container
from sber_a2a.domain.models import (
    CreateDealRequest,
    Mandate,
    ProcurementIntent,
    ProductRequest,
    RankingWeights,
)


@pytest.fixture
async def container() -> Container:
    instance = build_container(
        Settings(
            llm_provider="disabled",
            database_url="sqlite+aiosqlite:///:memory:",
            _env_file=None,
        )
    )
    yield instance
    await instance.store.close()
    await instance.ledger.close()


@pytest.fixture
def deal_request() -> CreateDealRequest:
    runtime = Settings(_env_file=None).runtime
    profile = runtime.profile
    ranking = runtime.ranking
    return CreateDealRequest(
        intent=ProcurementIntent(
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
        ),
        mandate=Mandate(
            customer_id=profile.buyer_organization_id,
            organization_id=profile.buyer_organization_id,
            agent_id=profile.buyer_agent_id,
            issuer=profile.mandate_issuer,
            authorized_by=profile.approver_subject,
            allowed_actions=set(profile.allowed_actions),
            forbidden_actions=set(profile.forbidden_actions),
            allowed_categories={profile.default_category},
            max_total=profile.default_maximum_amount,
            cumulative_amount=Decimal("0.00"),
            currency=profile.default_currency,
            valid_from=datetime.now(UTC) - timedelta(minutes=1),
            expires_at=datetime.now(UTC) + timedelta(hours=profile.mandate_validity_hours),
            required_approvals={profile.approval_role},
            signature=profile.mandate_signature,
            version=profile.mandate_version,
        ),
    )
