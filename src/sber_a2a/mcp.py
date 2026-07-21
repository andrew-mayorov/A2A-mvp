from uuid import UUID

from fastmcp import FastMCP

from sber_a2a.container import Container


def create_mcp_server(container: Container) -> FastMCP:
    mcp = FastMCP(
        "A1 Buyer Agent read-only tools",
        instructions=(
            "Read-only agent-to-tool interface. Human approval, Purchase Intent, "
            "payment and legal operations are intentionally unavailable to models."
        ),
    )

    @mcp.tool
    async def list_supplier_agents() -> list[dict]:
        """List accredited A2 supplier agents visible to the buyer."""
        return [item.model_dump(mode="json") for item in container.registry.list_suppliers()]

    @mcp.tool
    async def get_procurement_deal(deal_id: str) -> dict:
        """Read one buyer-owned procurement deal and its audit events."""
        deal = await container.deals.get(UUID(deal_id))
        return deal.model_dump(mode="json")

    return mcp
