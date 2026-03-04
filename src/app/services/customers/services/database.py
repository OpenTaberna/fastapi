"""
Customers Database Services

Repositories for customer and address data access.
Business logic (e.g. enforcing one default address per customer)
belongs in functions/, not here.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database.repository import BaseRepository
from ..models.database import AddressDB, CustomerDB


class CustomerRepository(BaseRepository[CustomerDB]):
    """
    Repository for customer database operations.

    Inherits standard CRUD from BaseRepository.
    Add customer-specific queries here as the service grows.
    """

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(CustomerDB, session)

    async def get_by_keycloak_id(self, keycloak_user_id: str) -> CustomerDB | None:
        """
        Look up a customer by their Keycloak subject claim.

        Used on every authenticated request to resolve the customer record.

        Args:
            keycloak_user_id: The 'sub' claim from the Keycloak JWT.

        Returns:
            CustomerDB instance or None if not yet registered.
        """
        return await self.get_by(keycloak_user_id=keycloak_user_id)

    async def get_by_email(self, email: str) -> CustomerDB | None:
        """
        Look up a customer by email address.

        Args:
            email: Customer email address.

        Returns:
            CustomerDB instance or None.
        """
        return await self.get_by(email=email)


class AddressRepository(BaseRepository[AddressDB]):
    """
    Repository for address database operations.
    """

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(AddressDB, session)

    async def get_all_for_customer(self, customer_id: UUID) -> list[AddressDB]:
        """
        Return all addresses belonging to a customer.

        Args:
            customer_id: UUID of the customer.

        Returns:
            List of AddressDB instances (may be empty).
        """
        stmt = select(self.model).where(self.model.customer_id == customer_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_default_for_customer(self, customer_id: UUID) -> AddressDB | None:
        """
        Return the default address for a customer, if one exists.

        Args:
            customer_id: UUID of the customer.

        Returns:
            Default AddressDB instance or None.
        """
        stmt = select(self.model).where(
            self.model.customer_id == customer_id,
            self.model.is_default.is_(True),
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Dependency injection factories
# ---------------------------------------------------------------------------


def get_customer_repository(session: AsyncSession) -> CustomerRepository:
    """Factory for CustomerRepository — use with FastAPI Depends."""
    return CustomerRepository(session)


def get_address_repository(session: AsyncSession) -> AddressRepository:
    """Factory for AddressRepository — use with FastAPI Depends."""
    return AddressRepository(session)
