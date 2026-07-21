from typing import Protocol
from uuid import UUID

from sber_a2a.domain.models import Mandate, ProcurementIntent, Quote, SupplierSummary


class SupplierAgent(Protocol):
    @property
    def summary(self) -> SupplierSummary: ...

    async def create_quote(
        self,
        intent: ProcurementIntent,
        *,
        mandate: Mandate | None = None,
        deal_id: UUID | None = None,
    ) -> Quote | None: ...
