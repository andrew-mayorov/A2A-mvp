import asyncio
import hashlib
from decimal import Decimal
from uuid import uuid4

from sber_a2a.domain.models import (
    DealRecord,
    DocumentRef,
    FulfillmentStatus,
    FulfillmentUpdate,
    Quote,
)
from sber_a2a.integrations.contracts import OrderCreationResult


class MockOrderGateway:
    """Demo replacement for future ERP and Sber payment integrations."""

    def __init__(self) -> None:
        self._results: dict[str, OrderCreationResult] = {}
        self._lock = asyncio.Lock()

    async def create_order_and_payment_draft(
        self,
        deal: DealRecord,
        quote: Quote,
        *,
        idempotency_key: str,
    ) -> OrderCreationResult:
        async with self._lock:
            existing = self._results.get(idempotency_key)
            if existing is not None:
                return existing
            result = OrderCreationResult(
                order_id=uuid4(),
                payment_draft_id=uuid4(),
            )
            self._results[idempotency_key] = result
            return result


class MockSupplierRiskGateway:
    """Demo trusted risk source; supplier payload cannot override these values."""

    def __init__(self, risks: dict[str, Decimal]) -> None:
        self._risks = dict(risks)

    async def get_risk(self, supplier_id: str) -> Decimal:
        if supplier_id not in self._risks:
            raise ValueError("Supplier risk is not available from the trusted registry")
        return self._risks[supplier_id]


class MockFulfillmentGateway:
    async def create_demo_timeline(
        self,
        *,
        supplier_id: str,
    ) -> list[FulfillmentUpdate]:
        actor = f"A2:{supplier_id}"
        steps = [
            (FulfillmentStatus.ORDER_CONFIRMED, "Поставщик подтвердил заказ"),
            (FulfillmentStatus.PACKED, "Товар зарезервирован и упакован"),
            (FulfillmentStatus.SHIPPED, "Отгрузка передана в доставку"),
            (FulfillmentStatus.DELIVERED, "Поставка доставлена покупателю"),
            (FulfillmentStatus.DOCUMENTS_READY, "Закрывающие документы готовы"),
            (FulfillmentStatus.COMPLETED, "Демонстрационное исполнение завершено"),
        ]
        return [
            FulfillmentUpdate(
                status=status,
                actor=actor,
                details={"description": description},
            )
            for status, description in steps
        ]


class MockDocumentGateway:
    async def create_demo_documents(
        self,
        *,
        deal: DealRecord,
        quote: Quote,
        order_id,
    ) -> list[DocumentRef]:
        documents = [
            ("invoice", "Счёт на оплату"),
            ("waybill", "Транспортная накладная"),
            ("acceptance_certificate", "Акт приёмки"),
        ]
        return [
            DocumentRef(
                document_type=document_type,
                title=title,
                source=f"mock-edo:{quote.supplier_id}",
                sha256=hashlib.sha256(
                    (f"{deal.deal_id}:{order_id}:{quote.supplier_id}:{document_type}").encode()
                ).hexdigest(),
            )
            for document_type, title in documents
        ]
