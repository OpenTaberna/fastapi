"""
Inventory Database Services

Repositories for inventory items and stock reservations.

Important: The actual reservation/commit/release logic lives in
functions/ (Phase 1), NOT here. Repositories only handle raw data access.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database.repository import BaseRepository
from app.shared.exceptions import duplicate_entry
from app.shared.exceptions.enums import ErrorCode
from app.shared.exceptions.errors import BusinessRuleError
from app.shared.logger import get_logger
from ..models.inventory_db_models import InventoryItemDB, StockReservationDB

logger = get_logger(__name__)


class InventoryRepository(BaseRepository[InventoryItemDB]):
    """
    Repository for inventory item database operations.
    """

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(InventoryItemDB, session)

    async def get_available_quantity(self, sku: str) -> int:
        """
        Return the number of units available for reservation (on_hand - reserved).

        Uses a single column SELECT instead of fetching the full ORM object —
        important when called repeatedly during checkout under load.

        Args:
            sku: The SKU string.

        Returns:
            Available quantity. Returns 0 if the SKU is not tracked.
        """
        logger.debug("Getting available quantity", extra={"sku": sku})
        stmt = select(
            (self.model.on_hand - self.model.reserved).label("available")
        ).where(self.model.sku == sku)
        result = await self.session.execute(stmt)
        available = result.scalar_one_or_none()
        if available is None:
            return 0
        return max(0, available)

    async def create_inventory_item(self, sku: str, on_hand: int) -> InventoryItemDB:
        """
        Create a new inventory record, guarding against duplicate SKUs.

        Raises:
            ValidationError (422): If a record for this SKU already exists.
        """
        existing = await self.get_by(sku=sku)
        if existing:
            raise duplicate_entry("InventoryItem", "sku", sku)
        return await self.create(sku=sku, on_hand=on_hand, reserved=0)

    async def update_stock(
        self, inventory_id: UUID, update_data: dict
    ) -> InventoryItemDB | None:
        """
        Update inventory stock, enforcing the on_hand >= reserved invariant.

        Args:
            inventory_id: UUID of the inventory record.
            update_data:  Dict of fields to update (from InventoryItemUpdate).

        Returns:
            Updated InventoryItemDB, or None if not found.

        Raises:
            BusinessRuleError (400): If new on_hand would be less than current reserved.
        """
        item = await self.get(inventory_id)
        if item is None:
            return None
        if "on_hand" in update_data and update_data["on_hand"] < item.reserved:
            raise BusinessRuleError(
                message=(
                    f"on_hand cannot be less than current reserved quantity ({item.reserved})"
                ),
                error_code=ErrorCode.BUSINESS_RULE_VIOLATION,
                context={"field": "on_hand", "constraint": "on_hand >= reserved"},
            )
        return await self.update(inventory_id, **update_data)


class StockReservationRepository(BaseRepository[StockReservationDB]):
    """
    Repository for stock reservation database operations.
    """

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(StockReservationDB, session)

    async def get_active_for_order(self, order_id: UUID) -> list[StockReservationDB]:
        """
        Return all ACTIVE reservations for a given order.

        Args:
            order_id: UUID of the order.

        Returns:
            List of active StockReservationDB instances.
        """
        logger.debug(
            "Getting active reservations for order", extra={"order_id": str(order_id)}
        )
        stmt = select(self.model).where(
            and_(
                self.model.order_id == order_id,
                self.model.status == "active",
            )
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_expired_active(self, now: datetime) -> list[StockReservationDB]:
        """
        Return all ACTIVE reservations whose expiry timestamp has passed.

        Used by the background cleanup job (Phase 1 — expire_reservations).

        Args:
            now: Current UTC datetime.

        Returns:
            List of expired-but-still-active StockReservationDB instances.
        """
        logger.debug("Getting expired active reservations")
        stmt = select(self.model).where(
            and_(
                self.model.status == "active",
                self.model.expires_at <= now,
            )
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Dependency injection factories
# ---------------------------------------------------------------------------


def get_inventory_repository(session: AsyncSession) -> InventoryRepository:
    """Factory for InventoryRepository — use with FastAPI Depends."""
    return InventoryRepository(session)


def get_stock_reservation_repository(
    session: AsyncSession,
) -> StockReservationRepository:
    """Factory for StockReservationRepository — use with FastAPI Depends."""
    return StockReservationRepository(session)
