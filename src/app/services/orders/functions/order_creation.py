"""
Order Creation Functions

Business logic for the order creation flow: catalogue lookups,
price snapshotting, and total calculation.

Extracted from the orders router so the router contains only HTTP/transport
concerns. All catalogue-lookup and pricing logic lives here.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.crud_item_store.models import ItemDB
from app.shared.exceptions import entity_not_found
from app.shared.logger import get_logger

from ..models import OrderItemCreate

logger = get_logger(__name__)


async def resolve_order_lines(
    session: AsyncSession,
    items: list[OrderItemCreate],
) -> tuple[list[tuple[OrderItemCreate, int]], int]:
    """
    Resolve SKUs to current prices and calculate the order total.

    Performs a single bulk SELECT against the item catalogue to look up all
    requested SKUs. Raises NotFoundError (404) if any SKU is missing. Returns
    a list of (OrderItemCreate, unit_price_cents) pairs and the pre-computed
    total_amount in cents.

    Args:
        session: Active AsyncSession (read-only; no transaction required).
        items:   Line items from OrderCreate, each carrying a SKU and quantity.

    Returns:
        Tuple of:
          - resolved_lines: list of (OrderItemCreate, unit_price_cents) pairs
          - total_amount:   sum of unit_price × quantity across all lines (cents)

    Raises:
        NotFoundError (404): If any SKU does not exist in the catalogue.
    """
    sku_list = [line.sku for line in items]
    stmt = select(ItemDB).where(ItemDB.sku.in_(sku_list))
    result = await session.execute(stmt)
    items_by_sku: dict[str, ItemDB] = {row.sku: row for row in result.scalars().all()}

    for line in items:
        if line.sku not in items_by_sku:
            raise entity_not_found("Item", line.sku)

    total_amount = 0
    resolved_lines: list[tuple[OrderItemCreate, int]] = []
    for line in items:
        unit_price: int = items_by_sku[line.sku].price[
            "amount"
        ]  # JSONB price.amount (cents)
        total_amount += unit_price * line.quantity
        resolved_lines.append((line, unit_price))

    return resolved_lines, total_amount
