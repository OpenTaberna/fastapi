"""
Database Migration Support

Utilities for Alembic migrations and schema management.
"""

from pathlib import Path
from typing import Optional

from alembic import command
from alembic.config import Config as AlembicConfig

from app.shared.database.utils import get_logger

logger = get_logger(__name__)


def get_alembic_config(
    migrations_dir: Optional[Path] = None,
) -> AlembicConfig:
    """
    Get Alembic configuration.

    Args:
        migrations_dir: Path to migrations directory (defaults to ./migrations)

    Returns:
        Configured AlembicConfig instance

    Example:
        >>> config = get_alembic_config()
        >>> command.upgrade(config, "head")
    """
    if migrations_dir is None:
        # Default to ./migrations in project root
        migrations_dir = Path.cwd() / "migrations"

    alembic_ini = migrations_dir / "alembic.ini"

    if not alembic_ini.exists():
        raise FileNotFoundError(
            f"alembic.ini not found at {alembic_ini}. "
            "Run 'alembic init migrations' first."
        )

    config = AlembicConfig(str(alembic_ini))
    config.set_main_option("script_location", str(migrations_dir))

    return config


async def run_migrations(
    revision: str = "head",
    migrations_dir: Optional[Path] = None,
) -> None:
    """
    Run database migrations to specified revision.

    Args:
        revision: Target revision (default: "head" for latest)
        migrations_dir: Path to migrations directory

    Example:
        >>> # Migrate to latest
        >>> await run_migrations()
        >>>
        >>> # Migrate to specific revision
        >>> await run_migrations("ae1027a6acf")
    """
    logger.info(
        "Running database migrations",
        extra={"revision": revision},
    )

    try:
        config = get_alembic_config(migrations_dir)
        command.upgrade(config, revision)

        logger.info("Database migrations completed successfully")

    except Exception as e:
        logger.error(
            "Database migration failed",
            extra={"error": str(e)},
            exc_info=True,
        )
        raise


async def rollback_migration(
    revision: str = "-1",
    migrations_dir: Optional[Path] = None,
) -> None:
    """
    Rollback database migration.

    Args:
        revision: Target revision (default: "-1" for one step back)
        migrations_dir: Path to migrations directory

    Example:
        >>> # Rollback one migration
        >>> await rollback_migration()
        >>>
        >>> # Rollback to specific revision
        >>> await rollback_migration("base")
    """
    logger.info(
        "Rolling back database migration",
        extra={"revision": revision},
    )

    try:
        config = get_alembic_config(migrations_dir)
        command.downgrade(config, revision)

        logger.info("Database rollback completed successfully")

    except Exception as e:
        logger.error(
            "Database rollback failed",
            extra={"error": str(e)},
            exc_info=True,
        )
        raise


async def create_migration(
    message: str,
    autogenerate: bool = True,
    migrations_dir: Optional[Path] = None,
) -> None:
    """
    Create new migration file.

    Args:
        message: Migration description
        autogenerate: Auto-detect model changes
        migrations_dir: Path to migrations directory

    Example:
        >>> await create_migration("add user table")
        >>> await create_migration("add email to user", autogenerate=True)
    """
    logger.info(
        "Creating migration",
        extra={"message": message, "autogenerate": autogenerate},
    )

    try:
        config = get_alembic_config(migrations_dir)
        command.revision(
            config,
            message=message,
            autogenerate=autogenerate,
        )

        logger.info("Migration created successfully")

    except Exception as e:
        logger.error(
            "Migration creation failed",
            extra={"error": str(e)},
            exc_info=True,
        )
        raise


async def get_migration_history(
    migrations_dir: Optional[Path] = None,
) -> list[str]:
    """
    Get migration history.

    Args:
        migrations_dir: Path to migrations directory

    Returns:
        List of migration revisions

    Example:
        >>> history = await get_migration_history()
        >>> print(f"Total migrations: {len(history)}")
    """
    try:
        get_alembic_config(migrations_dir)
        # This would need to be implemented to actually query Alembic
        # For now, return empty list
        logger.debug("Retrieved migration history")
        return []

    except Exception as e:
        logger.error(
            "Failed to retrieve migration history",
            extra={"error": str(e)},
            exc_info=True,
        )
        raise


__all__ = [
    "get_alembic_config",
    "run_migrations",
    "rollback_migration",
    "create_migration",
    "get_migration_history",
]
