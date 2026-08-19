"""
Orders Database Services

Repositories for orders and order line items.

Note: Status transition validation belongs in functions/ (Phase 1), not here.
The repositories are intentionally "dumb" — they perform data access only.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database.repository import BaseRepository
from app.shared.logger import get_logger
from ..models.orders_db_models import OrderDB, OrderItemDB
from ..models.orders_models import OrderStatus

logger = get_logger(__name__)


class OrderRepository(BaseRepository[OrderDB]):
    """
    Repository for order database operations.

    All list queries automatically exclude soft-deleted orders
    (deleted_at IS NOT NULL). Use get() directly if you need
    to access a deleted record for audit purposes.
    """

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(OrderDB, session)

    async def get_by_customer(
        self,
        customer_id: UUID,
        skip: int = 0,
        limit: int = 50,
    ) -> list[OrderDB]:
        """
        Return all non-deleted orders for a specific customer, newest first.

        Used for the customer-facing order history endpoint.

        Args:
            customer_id: UUID of the customer.
            skip:        Pagination offset.
            limit:       Maximum number of results.

        Returns:
            List of OrderDB instances (soft-deleted orders excluded).
        """
        logger.debug(
            "Getting orders for customer",
            extra={"customer_id": str(customer_id), "skip": skip, "limit": limit},
        )
        stmt = (
            select(self.model)
            .where(
                self.model.customer_id == customer_id,
                self.model.deleted_at.is_(None),
            )
            .order_by(self.model.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_status(
        self,
        status: OrderStatus,
        skip: int = 0,
        limit: int = 50,
    ) -> list[OrderDB]:
        """
        Return all non-deleted orders with a given status, newest first.

        Used for admin order management (filter by status).

        Args:
            status: OrderStatus enum value to filter by.
            skip:   Pagination offset.
            limit:  Maximum number of results.

        Returns:
            List of OrderDB instances (soft-deleted orders excluded).
        """
        logger.debug(
            "Getting orders by status",
            extra={"status": status.value, "skip": skip, "limit": limit},
        )
        stmt = (
            select(self.model)
            .where(
                self.model.status == status.value,
                self.model.deleted_at.is_(None),
            )
            .order_by(self.model.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class OrderItemRepository(BaseRepository[OrderItemDB]):
    """
    Repository for order item database operations.
    """

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(OrderItemDB, session)

    async def get_by_order_ids(self, order_ids: list[UUID]) -> list[OrderItemDB]:
        """
        Bulk-fetch all order items belonging to the given order IDs.

        Used when generating pick lists so an entire batch of orders can be
        loaded in a single query instead of N individual item look-ups.

        Args:
            order_ids: List of order UUIDs whose items should be fetched.

        Returns:
            List of OrderItemDB instances for all supplied order IDs.
            Returns an empty list when order_ids is empty.
        """
        logger.debug(
            "Bulk-fetching order items by order IDs",
            extra={"order_count": len(order_ids)},
        )
        if not order_ids:
            return []

        stmt = select(self.model).where(self.model.order_id.in_(order_ids))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Dependency injection factories
# ---------------------------------------------------------------------------


def get_order_repository(session: AsyncSession) -> OrderRepository:
    """Factory for OrderRepository — use with FastAPI Depends."""
    return OrderRepository(session)


def get_order_item_repository(session: AsyncSession) -> OrderItemRepository:
    """Factory for OrderItemRepository — use with FastAPI Depends."""
    return OrderItemRepository(session)
