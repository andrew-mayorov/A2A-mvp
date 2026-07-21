import asyncio
from datetime import UTC, date, datetime, timedelta

from sber_a2a.container import build_container
from sber_a2a.domain.models import (
    ApprovalRequest,
    CreateDealRequest,
    Mandate,
    PaymentSignatureRequest,
    ProcurementIntent,
    ProductRequest,
    RankingWeights,
)


async def main() -> None:
    container = build_container()
    runtime = container.settings.runtime
    profile = runtime.profile
    ranking = runtime.ranking
    now = datetime.now(UTC)
    request = CreateDealRequest(
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
            cumulative_amount=0,
            currency=profile.default_currency,
            valid_from=now,
            expires_at=now + timedelta(hours=profile.mandate_validity_hours),
            required_approvals={profile.approval_role},
            signature=profile.mandate_signature,
            version=profile.mandate_version,
        ),
    )
    deal = await container.deals.create(request)
    print("=== A1 collected and deterministically ranked direct A2 quotes ===")
    print(deal.model_dump_json(indent=2))

    snapshot = deal.approval_snapshot
    if deal.comparison and deal.comparison.recommended_quote_id and snapshot:
        approval = await container.deals.approve(
            deal.deal_id,
            ApprovalRequest(
                quote_id=deal.comparison.recommended_quote_id,
                approved_by=profile.approver_subject,
                approval_snapshot_hash=snapshot.snapshot_hash,
            ),
        )
        print("=== Human-approved purchase intent and payment draft ===")
        print(approval.model_dump_json(indent=2))
        signed = await container.deals.sign_payment(
            deal.deal_id,
            PaymentSignatureRequest(
                signed_by=profile.approver_subject,
                payment_draft_id=approval.payment_draft_id,
                confirmation=True,
                signature_evidence="demo-human-bank-signature",
            ),
        )
        print("=== Human bank-signature simulation completed ===")
        print(signed.model_dump_json(indent=2))


def run() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    run()
