"""
Customers Database Services

Repositories for customer and address data access.
Business logic (e.g. enforcing one default address per customer)
belongs in functions/, not here.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database.repository import BaseRepository
from ..models.customers_db_models import AddressDB, CustomerDB


class CustomerRepository(BaseRepository[CustomerDB]):
    """
    Repository for customer database operations.

    Inherits standard CRUD from BaseRepository.
    Add customer-specific queries here as the service grows.
    """

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(CustomerDB, session)


class AddressRepository(BaseRepository[AddressDB]):
    """
    Repository for address database operations.
    """

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(AddressDB, session)


# ---------------------------------------------------------------------------
# Dependency injection factories
# ---------------------------------------------------------------------------


def get_customer_repository(session: AsyncSession) -> CustomerRepository:
    """Factory for CustomerRepository — use with FastAPI Depends."""
    return CustomerRepository(session)


def get_address_repository(session: AsyncSession) -> AddressRepository:
    """Factory for AddressRepository — use with FastAPI Depends."""
    return AddressRepository(session)
