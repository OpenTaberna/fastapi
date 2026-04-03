"""
Admin Order Database Service

Admin-specific repository that extends OrderRepository with queries that
operate across all customers (no ownership filter) and support status-based
filtering for the admin order list.

The base OrderRepository customer-scoped methods are intentionally not
overridden — admin code should use the methods defined here to make it
explicit that no ownership check is being applied.
"""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.orders.models.orders_db_models import OrderDB, OrderItemDB
from app.services.orders.models.orders_models import OrderStatus
from app.shared.database.repository import BaseRepository
from app.shared.logger import get_logger

logger = get_logger(__name__)


class AdminOrderRepository(BaseRepository[OrderDB]):
    """
    Repository for admin-level order queries.

    Unlike OrderRepository (customer-scoped), these methods return orders
    across all customers. Soft-deleted records are excluded by default.
    """

    def __init__(self, session: AsyncSession) -> None:
        """
        Initialise with the shared async session.

        Args:
            session: SQLAlchemy AsyncSession provided by the DI container.
        """
        super().__init__(OrderDB, session)

    async def list_orders(
        self,
        status: OrderStatus | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[OrderDB]:
        """
        Return a paginated, newest-first list of all non-deleted orders.

        Args:
            status: When provided, filters to orders in this status only.
            skip:   Number of records to skip (pagination offset).
            limit:  Maximum number of records to return.

        Returns:
            List of OrderDB instances ordered by created_at descending.
        """
        logger.debug(
            "Admin listing orders",
            extra={
                "status": status.value if status else None,
                "skip": skip,
                "limit": limit,
            },
        )
        stmt = select(self.model).where(self.model.deleted_at.is_(None))

        if status is not None:
            stmt = stmt.where(self.model.status == status.value)

        stmt = stmt.order_by(self.model.created_at.desc()).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_orders(self, status: OrderStatus | None = None) -> int:
        """
        Count all non-deleted orders, optionally filtered by status.

        Used alongside list_orders to build the pagination metadata returned
        in AdminOrderListResponse.

        Args:
            status: When provided, counts only orders in this status.

        Returns:
            Integer count of matching non-deleted orders.
        """
        stmt = (
            select(func.count())
            .select_from(self.model)
            .where(self.model.deleted_at.is_(None))
        )

        if status is not None:
            stmt = stmt.where(self.model.status == status.value)

        logger.debug(
            "Admin counting orders",
            extra={"status": status.value if status else None},
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def get_items_for_orders(self, order_ids: list[UUID]) -> list[OrderItemDB]:
        """
        Bulk-fetch all order items belonging to the given order IDs.

        Used when generating pick lists so the entire PAID batch can be
        loaded in a single query instead of N individual item look-ups.

        Args:
            order_ids: List of order UUIDs whose items should be fetched.

        Returns:
            List of OrderItemDB instances for all supplied order IDs.
            Returns an empty list when order_ids is empty.
        """
        logger.debug(
            "Bulk-fetching order items for pick list",
            extra={"order_count": len(order_ids)},
        )
        if not order_ids:
            return []

        stmt = select(OrderItemDB).where(OrderItemDB.order_id.in_(order_ids))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Dependency injection factory
# ---------------------------------------------------------------------------


def get_admin_order_repository(session: AsyncSession) -> AdminOrderRepository:
    """
    Factory for AdminOrderRepository — use with FastAPI Depends.

    Args:
        session: AsyncSession provided by get_session_dependency.

    Returns:
        A new AdminOrderRepository bound to the given session.
    """
    return AdminOrderRepository(session)
