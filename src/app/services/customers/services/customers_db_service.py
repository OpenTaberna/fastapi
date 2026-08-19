"""
Customers Database Services

Repositories for customer and address data access.
Business rules (e.g. enforcing one default address per customer) live here,
not in the router.
"""

from typing import Sequence
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database.repository import BaseRepository
from app.shared.exceptions import access_denied, entity_not_found

from ..models.customers_db_models import AddressDB, CustomerDB
from ..models.customers_models import (
    AddressCreate,
    AddressUpdate,
    CustomerCreate,
    CustomerUpdate,
)


class CustomerRepository(BaseRepository[CustomerDB]):
    """Repository for customer database operations."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(CustomerDB, session)

    async def get_by_keycloak_id(self, keycloak_user_id: str) -> CustomerDB | None:
        """Look up a customer by their Keycloak subject claim."""
        return await self.get_by(keycloak_user_id=keycloak_user_id)

    async def get_by_keycloak_id_or_404(self, keycloak_user_id: str) -> CustomerDB:
        """Look up a customer by Keycloak ID, raising 404 if not found."""
        customer = await self.get_by_keycloak_id(keycloak_user_id)
        if customer is None:
            raise entity_not_found("Customer", keycloak_user_id)
        return customer

    async def create_customer(self, payload: CustomerCreate) -> CustomerDB:
        """Create and return a customer from validated profile data."""
        return await self.create(**payload.model_dump())

    async def update_customer(
        self,
        customer_id: UUID,
        payload: CustomerUpdate,
    ) -> CustomerDB:
        """Partially update a customer record. Returns the updated record."""
        data = payload.model_dump(exclude_unset=True)
        if not data:
            customer = await self.get(customer_id)
            if customer is None:
                raise entity_not_found("Customer", customer_id)
            return customer
        updated = await self.update(customer_id, **data)
        if updated is None:
            raise entity_not_found("Customer", customer_id)
        return updated


class AddressRepository(BaseRepository[AddressDB]):
    """Repository for address database operations."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(AddressDB, session)

    async def get_for_customer(self, customer_id: UUID) -> Sequence[AddressDB]:
        """Return all addresses belonging to *customer_id*."""
        return await self.filter(customer_id=customer_id)

    async def _clear_default(self, customer_id: UUID) -> None:
        """Unset is_default on all existing addresses for *customer_id*."""
        stmt = (
            update(AddressDB)
            .where(AddressDB.customer_id == customer_id)
            .values(is_default=False)
            .execution_options(synchronize_session="fetch")
        )
        await self.session.execute(stmt)

    async def create_address(
        self, customer_id: UUID, payload: AddressCreate
    ) -> AddressDB:
        """
        Create a new address.

        If ``is_default=True`` the existing default (if any) is cleared first.
        """
        if payload.is_default:
            await self._clear_default(customer_id)
        return await self.create(customer_id=customer_id, **payload.model_dump())

    async def update_address(
        self,
        address_id: UUID,
        customer_id: UUID,
        payload: AddressUpdate,
    ) -> AddressDB:
        """
        Partially update an address.

        Raises:
            NotFoundError (404): Address does not exist.
            AuthorizationError (403): Address belongs to a different customer.
        """
        address = await self.get(address_id)
        if address is None:
            raise entity_not_found("Address", address_id)
        if address.customer_id != customer_id:
            raise access_denied(
                resource="Address",
                message=f"Address '{address_id}' does not belong to this customer",
            )

        data = payload.model_dump(exclude_unset=True)
        if data.get("is_default"):
            await self._clear_default(customer_id)
        if not data:
            return address
        return await self.update(address_id, **data)

    async def delete_address(self, address_id: UUID, customer_id: UUID) -> None:
        """
        Delete an address.

        Raises:
            NotFoundError (404): Address does not exist.
            AuthorizationError (403): Address belongs to a different customer.
        """
        address = await self.get(address_id)
        if address is None:
            raise entity_not_found("Address", address_id)
        if address.customer_id != customer_id:
            raise access_denied(
                resource="Address",
                message=f"Address '{address_id}' does not belong to this customer",
            )
        await self.delete(address_id)


# ---------------------------------------------------------------------------
# Dependency injection factories
# ---------------------------------------------------------------------------


def get_customer_repository(session: AsyncSession) -> CustomerRepository:
    """Factory for CustomerRepository — use with FastAPI Depends."""
    return CustomerRepository(session)


def get_address_repository(session: AsyncSession) -> AddressRepository:
    """Factory for AddressRepository — use with FastAPI Depends."""
    return AddressRepository(session)
