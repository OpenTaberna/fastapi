"""
Database Session Management

Provides async session factory and dependency injection helpers.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.shared.database.engine import get_engine

from app.shared.database.utils import get_logger, DatabaseError

logger = get_logger(__name__)


def create_session_factory() -> async_sessionmaker[AsyncSession]:
    """
    Create async session factory.

    Returns:
        Configured async_sessionmaker

    Example:
        >>> factory = create_session_factory()
        >>> async with factory() as session:
        ...     result = await session.execute(select(User))
    """
    engine = get_engine()

    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,  # Don't expire objects after commit
        autoflush=False,  # Manual control over flushing
        autocommit=False,  # Explicit transaction control
    )


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Get async database session context manager.

    Automatically handles:
    - Session creation
    - Transaction commit on success
    - Rollback on exception
    - Session cleanup

    Yields:
        AsyncSession for database operations

    Example:
        >>> async with get_session() as session:
        ...     user = User(name="John")
        ...     session.add(user)
        ...     await session.commit()
        ...     # Session automatically closes
    """
    factory = create_session_factory()
    session = factory()

    try:
        logger.debug("Database session created")
        yield session
        await session.commit()
        logger.debug("Database session committed")
    except (RequestValidationError, HTTPException):
        # FastAPI validation and HTTP errors should pass through unchanged
        await session.rollback()
        logger.debug("Database session rolled back due to FastAPI exception")
        raise
    except DatabaseError:
        # Already a DatabaseError, just rollback and re-raise
        await session.rollback()
        logger.warning("Database session rolled back due to DatabaseError")
        raise
    except Exception as e:
        await session.rollback()
        logger.error(
            "Database session rolled back due to unexpected error",
            extra={"error": str(e), "error_type": type(e).__name__},
            exc_info=True,
        )
        # Wrap in DatabaseError for consistency
        raise DatabaseError(
            message="Database session failed",
            context={"error_type": type(e).__name__},
            original_exception=e,
        )
    finally:
        await session.close()
        logger.debug("Database session closed")


async def get_session_dependency() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency for database session.

    Use with Depends() in route handlers.

    Yields:
        AsyncSession for route handler

    Example:
        >>> from fastapi import Depends
        >>>
        >>> @router.get("/users/{user_id}")
        >>> async def get_user(
        ...     user_id: int,
        ...     session: AsyncSession = Depends(get_session_dependency)
        ... ):
        ...     result = await session.execute(
        ...         select(User).where(User.id == user_id)
        ...     )
        ...     return result.scalar_one_or_none()
    """
    async with get_session() as session:
        yield session


__all__ = [
    "AsyncSession",
    "create_session_factory",
    "get_session",
    "get_session_dependency",
]
