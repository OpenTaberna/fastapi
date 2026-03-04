"""
Shipments Database Services

Repository for shipment data access.
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database.repository import BaseRepository
from ..models.database import ShipmentDB


class ShipmentRepository(BaseRepository[ShipmentDB]):
    """
    Repository for shipment database operations.
    """

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(ShipmentDB, session)

    async def get_by_order(self, order_id: UUID) -> ShipmentDB | None:
        """
        Return the shipment record for a given order.

        Args:
            order_id: UUID of the associated order.

        Returns:
            ShipmentDB instance or None if no shipment has been created yet.
        """
        return await self.get_by(order_id=order_id)


# ---------------------------------------------------------------------------
# Dependency injection factory
# ---------------------------------------------------------------------------


def get_shipment_repository(session: AsyncSession) -> ShipmentRepository:
    """Factory for ShipmentRepository — use with FastAPI Depends."""
    return ShipmentRepository(session)
