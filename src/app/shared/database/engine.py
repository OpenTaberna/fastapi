"""
Database Engine Management

Handles database engine creation, configuration, and lifecycle.
"""

from typing import Optional

from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncEngine,
)
from sqlalchemy.pool import NullPool, QueuePool

from app.shared.database.utils import (
    get_logger,
    get_settings,
    DatabaseError,
    InternalError,
)

logger = get_logger(__name__)


# Global engine instance (singleton)
_engine: Optional[AsyncEngine] = None


def create_engine(
    database_url: Optional[str] = None,
    pool_size: int = 20,
    max_overflow: int = 40,
    pool_timeout: int = 30,
    pool_recycle: int = 3600,
    pool_pre_ping: bool = True,
    echo: bool = False,
    echo_pool: bool = False,
    server_settings: Optional[dict[str, str]] = None,
) -> AsyncEngine:
    """
    Create async database engine with connection pooling.

    Args:
        database_url: Database connection URL (defaults to config)
        pool_size: Number of connections to maintain
        max_overflow: Maximum additional connections
        pool_timeout: Timeout for getting connection from pool
        pool_recycle: Recycle connections after this many seconds
        pool_pre_ping: Test connections before using
        echo: Log all SQL statements
        echo_pool: Log connection pool events
        server_settings: PostgreSQL server-side settings

    Returns:
        Configured AsyncEngine instance

    Example:
        >>> engine = create_engine()
        >>> async with engine.begin() as conn:
        ...     await conn.execute(text("SELECT 1"))
    """
    # Load from config if available
    if database_url is None and get_settings:
        settings = get_settings()
        database_url = settings.database_url
        pool_size = settings.database_pool_size
        max_overflow = settings.database_max_overflow
        pool_timeout = settings.database_pool_timeout
        pool_recycle = settings.database_pool_recycle
        pool_pre_ping = settings.database_pool_pre_ping
        echo = settings.database_echo
        echo_pool = settings.database_echo_pool
        server_settings = settings.database_server_settings

    if not database_url:
        error_msg = "Database URL is required but not provided"
        logger.error(error_msg)
        raise DatabaseError(
            message=error_msg,
            context={"pool_size": pool_size, "max_overflow": max_overflow},
        )

    # Build connect_args
    connect_args = {}
    if server_settings:
        connect_args["server_settings"] = server_settings

    # Add timeouts
    connect_args["command_timeout"] = 60
    connect_args["timeout"] = 60

    logger.info(
        "Creating database engine",
        extra={
            "pool_size": pool_size,
            "max_overflow": max_overflow,
            "pool_recycle": pool_recycle,
            "pool_pre_ping": pool_pre_ping,
        },
    )

    try:
        engine = create_async_engine(
            database_url,
            echo=echo,
            echo_pool=echo_pool,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_timeout=pool_timeout,
            pool_recycle=pool_recycle,
            pool_pre_ping=pool_pre_ping,
            poolclass=QueuePool,
            connect_args=connect_args,
        )
        logger.info("Database engine created successfully")
        return engine
    except Exception as e:
        logger.error(
            "Failed to create database engine",
            extra={"error": str(e), "database_url_masked": "***"},
            exc_info=True,
        )
        raise DatabaseError(
            message="Failed to create database engine",
            context={"pool_size": pool_size, "max_overflow": max_overflow},
            original_exception=e,
        )


def create_test_engine(database_url: str) -> AsyncEngine:
    """
    Create engine for testing with NullPool.

    NullPool doesn't maintain connections, useful for tests
    where we want fresh connections each time.

    Args:
        database_url: Test database connection URL

    Returns:
        AsyncEngine configured for testing

    Example:
        >>> engine = create_test_engine("postgresql+asyncpg://...")
    """
    logger.info("Creating test database engine")

    return create_async_engine(
        database_url,
        echo=False,
        poolclass=NullPool,  # No connection pooling for tests
    )


async def init_database(engine: Optional[AsyncEngine] = None) -> AsyncEngine:
    """
    Initialize database connection.

    Creates global engine instance if not exists.
    Should be called on application startup.

    Args:
        engine: Optional engine to use instead of creating new one

    Returns:
        Initialized engine

    Example:
        >>> # In main.py startup
        >>> @app.on_event("startup")
        >>> async def startup():
        ...     await init_database()
    """
    global _engine

    if engine:
        _engine = engine
        logger.info("Database initialized with provided engine")
        return _engine

    if _engine is None:
        _engine = create_engine()
        logger.info("Database initialized")
    else:
        logger.debug("Database already initialized")

    return _engine


async def close_database() -> None:
    """
    Close database connection and cleanup.

    Should be called on application shutdown.

    Example:
        >>> # In main.py shutdown
        >>> @app.on_event("shutdown")
        >>> async def shutdown():
        ...     await close_database()
    """
    global _engine

    if _engine:
        logger.info("Closing database connection")
        await _engine.dispose()
        _engine = None
        logger.info("Database connection closed")
    else:
        logger.debug("No database connection to close")


def get_engine() -> AsyncEngine:
    """
    Get global database engine.

    Returns:
        Global AsyncEngine instance

    Raises:
        InternalError: If database not initialized

    Example:
        >>> engine = get_engine()
        >>> async with engine.begin() as conn:
        ...     result = await conn.execute(select(User))
    """
    if _engine is None:
        error_msg = "Database not initialized. Call init_database() first."
        logger.error(error_msg)
        raise InternalError(
            message=error_msg,
            context={"action": "get_engine", "state": "not_initialized"},
        )
    return _engine
