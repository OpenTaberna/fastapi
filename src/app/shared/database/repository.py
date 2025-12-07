"""
Base Repository Pattern

Generic CRUD repository with async support and type safety.
Framework-agnostic and reusable across different APIs.
"""

from typing import Any, Generic, Optional, Sequence, Type, TypeVar

from sqlalchemy import Delete, Select, Update, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database.base import Base

from app.shared.database.utils import get_logger, DatabaseError, NotFoundError

logger = get_logger(__name__)


# Type variable for model classes
ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """
    Generic repository for CRUD operations.

    Provides type-safe, async database operations following the
    Repository pattern. Can be subclassed for specific models.

    Type Parameters:
        ModelType: SQLAlchemy model class

    Example:
        >>> # Direct usage
        >>> user_repo = BaseRepository(User, session)
        >>> user = await user_repo.get(1)
        >>>
        >>> # Subclass for specific model
        >>> class UserRepository(BaseRepository[User]):
        ...     def __init__(self, session: AsyncSession):
        ...         super().__init__(User, session)
        ...
        ...     async def get_by_email(self, email: str) -> Optional[User]:
        ...         return await self.get_by(email=email)
    """

    def __init__(self, model: Type[ModelType], session: AsyncSession):
        """
        Initialize repository.

        Args:
            model: SQLAlchemy model class
            session: Database session
        """
        self.model = model
        self.session = session

    async def get(self, id: Any) -> Optional[ModelType]:
        """
        Get entity by primary key.

        Args:
            id: Primary key value

        Returns:
            Model instance or None if not found

        Example:
            >>> user = await repo.get(1)
            >>> if user:
            ...     print(user.name)
        """
        logger.debug(f"Getting {self.model.__name__} by id", extra={"id": id})
        return await self.session.get(self.model, id)

    async def get_by(self, **filters) -> Optional[ModelType]:
        """
        Get single entity by filters.

        Args:
            **filters: Column=value filters

        Returns:
            First matching model instance or None

        Example:
            >>> user = await repo.get_by(email="john@example.com")
            >>> user = await repo.get_by(name="John", active=True)
        """
        logger.debug(
            f"Getting {self.model.__name__} by filters",
            extra={"filters": filters},
        )
        stmt = select(self.model).filter_by(**filters)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all(
        self,
        skip: int = 0,
        limit: Optional[int] = None,
    ) -> Sequence[ModelType]:
        """
        Get all entities with pagination.

        Args:
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of model instances

        Example:
            >>> users = await repo.get_all(skip=0, limit=10)
            >>> for user in users:
            ...     print(user.name)
        """
        logger.debug(
            f"Getting all {self.model.__name__}",
            extra={"skip": skip, "limit": limit},
        )
        stmt = select(self.model).offset(skip)
        if limit:
            stmt = stmt.limit(limit)

        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def filter(
        self,
        skip: int = 0,
        limit: Optional[int] = None,
        **filters,
    ) -> Sequence[ModelType]:
        """
        Get entities matching filters with pagination.

        Args:
            skip: Number of records to skip
            limit: Maximum number of records to return
            **filters: Column=value filters

        Returns:
            List of matching model instances

        Example:
            >>> active_users = await repo.filter(active=True, limit=10)
            >>> recent_posts = await repo.filter(
            ...     published=True,
            ...     skip=0,
            ...     limit=20
            ... )
        """
        logger.debug(
            f"Filtering {self.model.__name__}",
            extra={"filters": filters, "skip": skip, "limit": limit},
        )
        stmt = select(self.model).filter_by(**filters).offset(skip)
        if limit:
            stmt = stmt.limit(limit)

        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def create(self, **attributes) -> ModelType:
        """
        Create new entity.

        Args:
            **attributes: Model attributes

        Returns:
            Created model instance with generated ID

        Example:
            >>> user = await repo.create(
            ...     name="John Doe",
            ...     email="john@example.com"
            ... )
            >>> print(user.id)  # Auto-generated ID
        """
        logger.debug(
            f"Creating {self.model.__name__}",
            extra={"attributes": attributes},
        )
        try:
            instance = self.model(**attributes)
            self.session.add(instance)
            await self.session.flush()
            await self.session.refresh(instance)
            logger.debug(
                f"{self.model.__name__} created successfully",
                extra={"id": getattr(instance, "id", None)},
            )
            return instance
        except Exception as e:
            logger.error(
                f"Failed to create {self.model.__name__}",
                extra={"error": str(e), "attributes": attributes},
                exc_info=True,
            )
            raise DatabaseError(
                message=f"Failed to create {self.model.__name__}",
                context={"entity_type": self.model.__name__, "attributes": attributes},
                original_exception=e,
            )

    async def create_many(self, items: list[dict[str, Any]]) -> Sequence[ModelType]:
        """
        Create multiple entities in bulk.

        Args:
            items: List of attribute dictionaries

        Returns:
            List of created model instances

        Example:
            >>> users = await repo.create_many([
            ...     {"name": "John", "email": "john@example.com"},
            ...     {"name": "Jane", "email": "jane@example.com"},
            ... ])
        """
        logger.debug(
            f"Creating {len(items)} {self.model.__name__} instances",
        )
        try:
            instances = [self.model(**item) for item in items]
            self.session.add_all(instances)
            await self.session.flush()
            for instance in instances:
                await self.session.refresh(instance)
            logger.debug(f"Created {len(instances)} {self.model.__name__} instances")
            return instances
        except Exception as e:
            logger.error(
                f"Failed to create {len(items)} {self.model.__name__} instances",
                extra={"error": str(e), "count": len(items)},
                exc_info=True,
            )
            raise DatabaseError(
                message=f"Failed to bulk create {self.model.__name__}",
                context={"entity_type": self.model.__name__, "count": len(items)},
                original_exception=e,
            )

    async def update(self, id: Any, **attributes) -> Optional[ModelType]:
        """
        Update entity by primary key.

        Args:
            id: Primary key value
            **attributes: Attributes to update

        Returns:
            Updated model instance or None if not found

        Example:
            >>> user = await repo.update(1, name="John Smith")
            >>> if user:
            ...     print(user.name)  # "John Smith"
        """
        logger.debug(
            f"Updating {self.model.__name__}",
            extra={"id": id, "attributes": attributes},
        )
        instance = await self.get(id)
        if instance:
            for key, value in attributes.items():
                setattr(instance, key, value)
            await self.session.flush()
            await self.session.refresh(instance)
        return instance

    async def update_many(self, **filters) -> int:
        """
        Update multiple entities matching filters.

        Args:
            **filters: Must include filter conditions and 'values' dict

        Returns:
            Number of updated records

        Example:
            >>> count = await repo.update_many(
            ...     filters={"active": True},
            ...     values={"verified": True}
            ... )
            >>> print(f"Updated {count} records")
        """
        values = filters.pop("values", {})
        logger.debug(
            f"Updating many {self.model.__name__}",
            extra={"filters": filters, "values": values},
        )
        stmt = update(self.model).filter_by(**filters).values(**values)
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount  # type: ignore

    async def delete(self, id: Any) -> bool:
        """
        Delete entity by primary key.

        Args:
            id: Primary key value

        Returns:
            True if deleted, False if not found

        Example:
            >>> deleted = await repo.delete(1)
            >>> if deleted:
            ...     print("User deleted")
        """
        logger.debug(
            f"Deleting {self.model.__name__}",
            extra={"id": id},
        )
        instance = await self.get(id)
        if instance:
            await self.session.delete(instance)
            await self.session.flush()
            return True
        return False

    async def delete_many(self, **filters) -> int:
        """
        Delete multiple entities matching filters.

        Args:
            **filters: Column=value filters

        Returns:
            Number of deleted records

        Example:
            >>> count = await repo.delete_many(active=False)
            >>> print(f"Deleted {count} inactive users")
        """
        logger.debug(
            f"Deleting many {self.model.__name__}",
            extra={"filters": filters},
        )
        stmt = delete(self.model).filter_by(**filters)
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount  # type: ignore

    async def count(self, **filters) -> int:
        """
        Count entities matching filters.

        Args:
            **filters: Column=value filters (optional)

        Returns:
            Number of matching records

        Example:
            >>> total = await repo.count()
            >>> active_count = await repo.count(active=True)
        """
        logger.debug(
            f"Counting {self.model.__name__}",
            extra={"filters": filters},
        )
        stmt = select(func.count()).select_from(self.model)
        if filters:
            stmt = stmt.filter_by(**filters)

        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def exists(self, **filters) -> bool:
        """
        Check if entity exists matching filters.

        Args:
            **filters: Column=value filters

        Returns:
            True if at least one record exists

        Example:
            >>> exists = await repo.exists(email="john@example.com")
            >>> if exists:
            ...     raise ValueError("Email already taken")
        """
        count = await self.count(**filters)
        return count > 0

    async def execute(self, statement: Select | Update | Delete) -> Any:
        """
        Execute custom SQLAlchemy statement.

        For complex queries not covered by repository methods.

        Args:
            statement: SQLAlchemy select/update/delete statement

        Returns:
            Query result

        Example:
            >>> # Complex query
            >>> stmt = select(User).where(
            ...     User.created_at > datetime.now() - timedelta(days=7)
            ... ).order_by(User.created_at.desc())
            >>> result = await repo.execute(stmt)
            >>> recent_users = result.scalars().all()
        """
        logger.debug(f"Executing custom statement for {self.model.__name__}")
        return await self.session.execute(statement)

    # Helper methods that raise exceptions (optional, for convenience)

    async def get_or_raise(self, id: Any) -> ModelType:
        """
        Get entity by ID or raise NotFoundError.

        Args:
            id: Primary key value

        Returns:
            Model instance

        Raises:
            NotFoundError: If entity not found

        Example:
            >>> try:
            ...     user = await repo.get_or_raise(999)
            ... except NotFoundError:
            ...     return error_response("User not found")
        """
        entity = await self.get(id)
        if entity is None:
            logger.warning(f"{self.model.__name__} not found", extra={"id": id})
            raise NotFoundError(
                message=f"{self.model.__name__} not found",
                context={"entity_type": self.model.__name__, "id": id},
            )
        return entity

    async def get_by_or_raise(self, **filters) -> ModelType:
        """
        Get entity by filters or raise NotFoundError.

        Args:
            **filters: Column=value filters

        Returns:
            Model instance

        Raises:
            NotFoundError: If entity not found

        Example:
            >>> user = await repo.get_by_or_raise(email="john@example.com")
        """
        entity = await self.get_by(**filters)
        if entity is None:
            logger.warning(
                f"{self.model.__name__} not found", extra={"filters": filters}
            )
            raise NotFoundError(
                message=f"{self.model.__name__} not found",
                context={"entity_type": self.model.__name__, "filters": filters},
            )
        return entity


__all__ = ["BaseRepository", "ModelType"]
