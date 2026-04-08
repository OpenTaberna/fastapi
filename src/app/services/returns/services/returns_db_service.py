"""
Returns Database Service — Phase 4.4

Repository for return (RMA) data access.

Uses the shared BaseRepository for generic CRUD, and adds a
``get_by_order_id`` query for the uniqueness guard in the customer endpoint.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database.repository import BaseRepository

from ..models.returns_db_models import ReturnDB


class ReturnRepository(BaseRepository[ReturnDB]):
    """
    Repository for return request database operations.
    """

    def __init__(self, session: AsyncSession) -> None:
        """
        Args:
            session: Active AsyncSession passed from a FastAPI dependency.
        """
        super().__init__(ReturnDB, session)

    async def get_by_order_id(self, order_id: UUID) -> ReturnDB | None:
        """
        Fetch the return request associated with a specific order.

        Used to enforce the one-return-per-order business rule.

        Args:
            order_id: UUID of the order to look up.

        Returns:
            ReturnDB instance if one exists, otherwise None.
        """
        stmt = select(ReturnDB).where(ReturnDB.order_id == order_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Dependency injection factory
# ---------------------------------------------------------------------------


def get_return_repository(session: AsyncSession) -> ReturnRepository:
    """
    Factory for ReturnRepository — use with FastAPI Depends.

    Args:
        session: Active AsyncSession (provided by get_session_dependency).

    Returns:
        ReturnRepository bound to the given session.
    """
    return ReturnRepository(session)
