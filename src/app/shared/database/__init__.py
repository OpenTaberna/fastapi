"""
Database Module

Generic database layer with async support for PostgreSQL.
Framework-agnostic, follows SOLID principles, and can be reused across APIs.

Components:
    - Engine and session management
    - Base repository pattern with CRUD operations
    - Transaction management
    - Health checks
    - Migration support

Example:
    >>> from app.shared.database import get_session, init_database
    >>>
    >>> # Initialize database
    >>> await init_database()
    >>>
    >>> # Use session
    >>> async with get_session() as session:
    ...     result = await session.execute(select(User))
    ...     users = result.scalars().all()
"""

from app.shared.database.engine import (
    init_database,
    close_database,
    get_engine,
)
from app.shared.database.session import (
    get_session,
    get_session_dependency,
    AsyncSession,
)
from app.shared.database.base import Base, TimestampMixin, SoftDeleteMixin
from app.shared.database.repository import BaseRepository
from app.shared.database.transaction import transaction
from app.shared.database.health import check_database_health

__all__ = [
    # Engine
    "init_database",
    "close_database",
    "get_engine",
    # Session
    "get_session",
    "get_session_dependency",
    "AsyncSession",
    # Base
    "Base",
    "TimestampMixin",
    "SoftDeleteMixin",
    # Repository
    "BaseRepository",
    # Transaction
    "transaction",
    # Health
    "check_database_health",
]
