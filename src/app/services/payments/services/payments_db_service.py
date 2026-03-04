"""
Payments Database Services

Repository for payment data access.
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database.repository import BaseRepository
from ..models.payments_db_models import PaymentDB


class PaymentRepository(BaseRepository[PaymentDB]):
    """
    Repository for payment database operations.
    """

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(PaymentDB, session)

    async def get_by_order(self, order_id: UUID) -> PaymentDB | None:
        """
        Return the payment record for a given order.

        Args:
            order_id: UUID of the associated order.

        Returns:
            PaymentDB instance or None.
        """
        return await self.get_by(order_id=order_id)

    async def get_by_provider_reference(
        self, provider_reference: str
    ) -> PaymentDB | None:
        """
        Return a payment by its PSP-side reference ID.

        Used by the webhook handler to look up which payment is being updated.

        Args:
            provider_reference: PSP transaction ID (e.g. Stripe pi_xxx).

        Returns:
            PaymentDB instance or None.
        """
        return await self.get_by(provider_reference=provider_reference)


# ---------------------------------------------------------------------------
# Dependency injection factory
# ---------------------------------------------------------------------------


def get_payment_repository(session: AsyncSession) -> PaymentRepository:
    """Factory for PaymentRepository — use with FastAPI Depends."""
    return PaymentRepository(session)
