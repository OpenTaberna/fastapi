"""
Item Database Service

Database operations for the item-store service.
Uses the generic BaseRepository with item-specific queries.
"""

from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database.repository import BaseRepository
from ..models.database import ItemDB


class ItemRepository(BaseRepository[ItemDB]):
    """
    Repository for Item database operations.

    Extends BaseRepository with item-specific queries like:
    - Get by SKU
    - Get by slug
    - Generic search with multiple criteria
    - Field existence checks
    """

    def __init__(self, session: AsyncSession):
        """Initialize item repository with session."""
        super().__init__(ItemDB, session)

    async def get_by_sku(self, sku: str) -> Optional[ItemDB]:
        """
        Get item by SKU (Stock Keeping Unit).

        Args:
            sku: Stock Keeping Unit

        Returns:
            Item or None if not found

        Example:
            >>> item = await repo.get_by_sku("CHAIR-RED-001")
        """
        return await self.get_by(sku=sku)

    async def get_by_slug(self, slug: str) -> Optional[ItemDB]:
        """
        Get item by URL slug.

        Args:
            slug: URL-friendly identifier

        Returns:
            Item or None if not found

        Example:
            >>> item = await repo.get_by_slug("red-wooden-chair")
        """
        return await self.get_by(slug=slug)

    async def search(
        self,
        name: Optional[str] = None,
        status: Optional[str] = None,
        category_uuid: Optional[UUID] = None,
        brand: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[ItemDB]:
        """
        Generic search function for items with multiple optional criteria.

        All criteria are combined with AND logic. Any criteria left as None
        will be ignored in the search.

        Args:
            name: Search term for name (case-insensitive partial match)
            status: Exact status match (draft, active, archived)
            category_uuid: Filter by category UUID
            brand: Filter by brand name
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of matching items

        Examples:
            >>> # Search by name only
            >>> items = await repo.search(name="chair")
            
            >>> # Search active items in category
            >>> items = await repo.search(
            ...     status="active",
            ...     category_uuid=UUID("2f61e8db..."),
            ...     limit=20
            ... )
            
            >>> # Search by brand and status
            >>> items = await repo.search(brand="TestBrand", status="active")
        """
        stmt = select(self.model)
        conditions = []

        # Add filters based on provided criteria
        if name is not None:
            conditions.append(self.model.name.ilike(f"%{name}%"))

        if status is not None:
            conditions.append(self.model.status == status)

        if category_uuid is not None:
            conditions.append(
                self.model.categories.contains([str(category_uuid)])
            )

        if brand is not None:
            conditions.append(self.model.brand == brand)

        # Combine all conditions with AND
        if conditions:
            stmt = stmt.where(and_(*conditions))

        # Apply pagination
        stmt = stmt.offset(skip).limit(limit)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def field_exists(
        self, 
        field_name: str, 
        field_value: Any, 
        exclude_uuid: Optional[UUID] = None
    ) -> bool:
        """
        Generic method to check if a field value already exists.

        Args:
            field_name: Name of the field to check (e.g., "sku", "slug")
            field_value: Value to check for existence
            exclude_uuid: Optionally exclude an item UUID (for updates)

        Returns:
            True if field value exists, False otherwise

        Raises:
            ValueError: If field_name is not a valid column

        Examples:
            >>> # Check if SKU exists
            >>> exists = await repo.field_exists("sku", "CHAIR-RED-001")
            
            >>> # Check if slug exists, excluding current item
            >>> exists = await repo.field_exists(
            ...     "slug", "red-chair", exclude_uuid=item_uuid
            ... )
        """
        # Validate field exists on model
        if not hasattr(self.model, field_name):
            raise ValueError(f"Field '{field_name}' does not exist on ItemDB model")

        field = getattr(self.model, field_name)
        stmt = select(self.model.uuid).where(field == field_value)

        if exclude_uuid:
            stmt = stmt.where(self.model.uuid != exclude_uuid)

        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None


def get_item_repository(session: AsyncSession) -> ItemRepository:
    """
    Dependency injection factory for ItemRepository.

    Args:
        session: Database session (typically from FastAPI dependency)

    Returns:
        ItemRepository instance

    Example:
        >>> # In FastAPI router
        >>> @router.get("/items/{uuid}")
        >>> async def get_item(
        ...     uuid: UUID,
        ...     session: AsyncSession = Depends(get_session),
        ... ):
        ...     repo = get_item_repository(session)
        ...     return await repo.get(uuid)
    """
    return ItemRepository(session)
