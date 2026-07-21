from datetime import UTC, datetime, timedelta

import pytest

from sber_a2a.domain.models import ApprovalRequest, DealStatus, HumanDecisionKind
from sber_a2a.services.deals import DealConflictError


@pytest.mark.parametrize("revoked", [False, True])
async def test_expired_or_revoked_mandate_stops_before_rfq(
    container,
    deal_request,
    revoked: bool,
) -> None:
    now = datetime.now(UTC)
    mandate = deal_request.mandate.model_copy(
        update={
            "expires_at": now + timedelta(hours=1) if revoked else now - timedelta(minutes=1),
            "revoked_at": now if revoked else None,
        }
    )
    deal = await container.deals.create(deal_request.model_copy(update={"mandate": mandate}))
    assert deal.status is DealStatus.FAILED
    assert deal.quotes == []
    assert any("Mandate" in error for error in deal.errors)


@pytest.mark.parametrize(
    ("decision", "expected_status"),
    [
        (HumanDecisionKind.REJECT, DealStatus.REJECTED),
        (HumanDecisionKind.REQUEST_CHANGES, DealStatus.CHANGES_REQUESTED),
    ],
)
async def test_non_approval_decisions_create_no_payment_draft(
    container,
    deal_request,
    decision: HumanDecisionKind,
    expected_status: DealStatus,
) -> None:
    deal = await container.deals.create(deal_request)
    updated = await container.deals.decide(
        deal.deal_id,
        ApprovalRequest(
            quote_id=deal.comparison.recommended_quote_id,
            approved_by=deal_request.mandate.authorized_by,
            approval_snapshot_hash=deal.approval_snapshot.snapshot_hash,
            decision=decision,
            reason="test decision",
        ),
    )
    assert updated.status is expected_status
    assert updated.human_decision is not None
    assert updated.payment_draft is None
    assert updated.purchase_intent is None
    with pytest.raises(DealConflictError, match="cannot be approved"):
        await container.deals.approve(
            deal.deal_id,
            ApprovalRequest(
                quote_id=deal.comparison.recommended_quote_id,
                approved_by=deal_request.mandate.authorized_by,
                approval_snapshot_hash=deal.approval_snapshot.snapshot_hash,
            ),
        )
