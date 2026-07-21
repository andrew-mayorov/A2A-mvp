import pytest

from sber_a2a.domain.models import (
    ApprovalRequest,
    DealStatus,
    PaymentDraftStatus,
    PaymentSignatureRequest,
)
from sber_a2a.services.deals import DealConflictError


async def test_authorized_human_creates_one_order_and_payment_draft(
    container,
    deal_request,
) -> None:
    deal = await container.deals.create(deal_request)
    quote_id = deal.comparison.recommended_quote_id

    result = await container.deals.approve(
        deal.deal_id,
        ApprovalRequest(
            quote_id=quote_id,
            approved_by=deal_request.mandate.authorized_by,
            approval_snapshot_hash=deal.approval_snapshot.snapshot_hash,
        ),
    )

    assert result.status is DealStatus.PAYMENT_SIGNATURE_REQUIRED
    assert result.approval_snapshot_hash
    stored = await container.deals.get(deal.deal_id)
    assert stored.order_id == result.order_id
    assert stored.payment_draft_id == result.payment_draft_id
    assert stored.approval_snapshot is not None
    assert stored.approval_snapshot.snapshot_hash == result.approval_snapshot_hash
    assert stored.order is not None
    assert stored.payment_draft is not None
    assert stored.fulfillment == []
    assert stored.documents == []
    assert stored.purchase_intent is not None
    assert stored.ledger_anchor is not None
    assert stored.oracle_verification is not None

    repeated = await container.deals.approve(
        deal.deal_id,
        ApprovalRequest(
            quote_id=quote_id,
            approved_by=deal_request.mandate.authorized_by,
            approval_snapshot_hash=deal.approval_snapshot.snapshot_hash,
        ),
    )
    assert repeated.order_id == result.order_id
    assert repeated.payment_draft_id == result.payment_draft_id
    assert repeated.approval_snapshot_hash == result.approval_snapshot_hash

    signed = await container.deals.sign_payment(
        deal.deal_id,
        PaymentSignatureRequest(
            signed_by=deal_request.mandate.authorized_by,
            payment_draft_id=result.payment_draft_id,
            confirmation=True,
        ),
    )
    assert signed.status is DealStatus.COMPLETED
    assert signed.payment_status is PaymentDraftStatus.SIGNED
    repeated_signature = await container.deals.sign_payment(
        deal.deal_id,
        PaymentSignatureRequest(
            signed_by=deal_request.mandate.authorized_by,
            payment_draft_id=result.payment_draft_id,
            confirmation=True,
        ),
    )
    assert repeated_signature.payment_draft_id == result.payment_draft_id
    assert repeated_signature.status is DealStatus.COMPLETED
    completed = await container.deals.get(deal.deal_id)
    assert completed.fulfillment[-1].status.value == "completed"
    assert {document.document_type for document in completed.documents} == {
        "invoice",
        "waybill",
        "acceptance_certificate",
    }


async def test_unauthorized_human_cannot_approve(
    container,
    deal_request,
) -> None:
    deal = await container.deals.create(deal_request)

    with pytest.raises(DealConflictError, match="not authorized"):
        await container.deals.approve(
            deal.deal_id,
            ApprovalRequest(
                quote_id=deal.comparison.recommended_quote_id,
                approved_by="unknown-user",
                approval_snapshot_hash=deal.approval_snapshot.snapshot_hash,
            ),
        )


async def test_approval_requires_current_snapshot_hash(
    container,
    deal_request,
) -> None:
    deal = await container.deals.create(deal_request)

    with pytest.raises(DealConflictError, match="snapshot hash"):
        await container.deals.approve(
            deal.deal_id,
            ApprovalRequest(
                quote_id=deal.comparison.recommended_quote_id,
                approved_by=deal_request.mandate.authorized_by,
                approval_snapshot_hash="0" * 64,
            ),
        )
