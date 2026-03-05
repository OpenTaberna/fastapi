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
        logger.debug("Getting active reservations for order", extra={"order_id": str(order_id)})
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
