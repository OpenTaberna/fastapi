"""
Payments Database Services

Repository for payment data access.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database.repository import BaseRepository
from ..models.payments_db_models import PaymentDB


class PaymentRepository(BaseRepository[PaymentDB]):
    """
    Repository for payment database operations.
    """

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(PaymentDB, session)


# ---------------------------------------------------------------------------
# Dependency injection factory
# ---------------------------------------------------------------------------


def get_payment_repository(session: AsyncSession) -> PaymentRepository:
    """Factory for PaymentRepository — use with FastAPI Depends."""
    return PaymentRepository(session)
