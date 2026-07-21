import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from sber_a2a.domain.models import Mandate, ProcurementIntent, Quote, SupplierSummary
from sber_a2a.suppliers.base import SupplierAgent


@dataclass(frozen=True)
class CatalogItem:
    sku: str
    name: str
    unit_price: Decimal
    delivery_fee: Decimal
    currency: str
    vat_rate: Decimal
    delivery_days: int
    warranty_months: int
    supplier_risk: Decimal
    payment_delay_days: int


class MockSupplierAgent:
    def __init__(
        self,
        supplier_id: str,
        name: str,
        catalog: dict[str, CatalogItem],
        *,
        categories: set[str],
    ) -> None:
        self._summary = SupplierSummary(
            supplier_id=supplier_id,
            name=name,
            categories=categories,
        )
        self._catalog = catalog

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
        item = self._catalog.get(intent.product.sku)
        if item is None:
            return None
        return Quote(
            supplier_id=self.summary.supplier_id,
            supplier_name=self.summary.name,
            sku=item.sku,
            product_name=item.name,
            quantity=intent.product.quantity,
            unit_price=item.unit_price,
            delivery_fee=item.delivery_fee,
            currency=item.currency,
            vat_rate=item.vat_rate,
            delivery_days=item.delivery_days,
            warranty_months=item.warranty_months,
            supplier_risk=item.supplier_risk,
            payment_delay_days=item.payment_delay_days,
            valid_until=datetime.now(UTC) + timedelta(minutes=30),
        )


class SupplierRegistry:
    def __init__(self, agents: list[SupplierAgent]) -> None:
        self._agents = {
            agent.summary.supplier_id: agent for agent in agents if agent.summary.active
        }

    def list_suppliers(self) -> list[SupplierSummary]:
        return [agent.summary for agent in self._agents.values()]

    def discover(
        self,
        category: str,
        allowed_supplier_ids: set[str] | None = None,
    ) -> list[SupplierAgent]:
        return [
            agent
            for supplier_id, agent in self._agents.items()
            if category in agent.summary.categories
            and (allowed_supplier_ids is None or supplier_id in allowed_supplier_ids)
        ]

    def get(self, supplier_id: str) -> SupplierAgent | None:
        return self._agents.get(supplier_id)

    def register(self, agent: SupplierAgent) -> None:
        if not agent.summary.active:
            raise ValueError("Cannot register an inactive supplier agent")
        self._agents[agent.summary.supplier_id] = agent

    def unregister(self, supplier_id: str) -> None:
        self._agents.pop(supplier_id, None)


def load_catalog_supplier(
    supplier_id: str,
    catalog_file: str | Path,
    *,
    trusted_risk: Decimal,
    categories: set[str] | None = None,
) -> MockSupplierAgent:
    payload = json.loads(Path(catalog_file).read_text(encoding="utf-8"))
    configured_categories = categories or set(payload["categories"])
    catalog = {
        item["sku"]: CatalogItem(
            sku=item["sku"],
            name=item["name"],
            unit_price=Decimal(str(item["unit_price"])),
            delivery_fee=Decimal(str(item.get("delivery_fee", "0.00"))),
            currency=str(payload["currency"]),
            vat_rate=Decimal(str(payload["vat_rate"])),
            delivery_days=int(item["delivery_days"]),
            warranty_months=int(item["warranty_months"]),
            supplier_risk=trusted_risk,
            payment_delay_days=int(item.get("payment_delay_days", 0)),
        )
        for item in payload["items"]
    }
    return MockSupplierAgent(
        supplier_id,
        payload.get("name", supplier_id),
        catalog,
        categories=configured_categories,
    )
