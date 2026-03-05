"""
Shipments Database Services

Repository for shipment data access.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database.repository import BaseRepository
from ..models.shipments_db_models import ShipmentDB


class ShipmentRepository(BaseRepository[ShipmentDB]):
    """
    Repository for shipment database operations.
    """

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(ShipmentDB, session)


# ---------------------------------------------------------------------------
# Dependency injection factory
# ---------------------------------------------------------------------------


def get_shipment_repository(session: AsyncSession) -> ShipmentRepository:
    """Factory for ShipmentRepository — use with FastAPI Depends."""
    return ShipmentRepository(session)
