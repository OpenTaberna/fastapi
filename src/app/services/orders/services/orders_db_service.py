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
from ..models.orders_db_models import OrderDB, OrderItemDB
from ..models.orders_models import OrderStatus


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

    async def get_all_for_order(self, order_id: UUID) -> list[OrderItemDB]:
        """
        Return all line items for a given order.

        Args:
            order_id: UUID of the parent order.

        Returns:
            List of OrderItemDB instances.
        """
        stmt = select(self.model).where(self.model.order_id == order_id)
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
