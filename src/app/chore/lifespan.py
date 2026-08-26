"""
Application Lifespan Management

Handles startup and shutdown events for the FastAPI application,
including database initialization and cleanup.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

import app.db_models  # noqa: F401 — registers all ORM models with Base.metadata
from app.shared.config import get_settings
from app.shared.database.base import Base
from app.shared.database.engine import close_database, get_engine, init_database
from app.shared.logger import get_logger
from app.shared.observability import instrument_engine
from app.shared.observability import setup as setup_telemetry
from app.shared.storage.minio_adapter import build_minio_adapter

logger = get_logger(__name__)

# Secrets that must not ship to production with their default placeholder value
_CRITICAL_SETTINGS: tuple[str, ...] = (
    "secret_key",
    "stripe_secret_key",
    "stripe_webhook_secret",
)
_CHANGE_ME_MARKER = "CHANGE_ME"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan events.

    Startup:
        - Initialize database connection pool
        - Create all tables from SQLAlchemy models
        - Ensure MinIO label bucket exists

    Shutdown:
        - Close database connections gracefully
    """
    # Startup: validate secrets before doing anything else
    _validate_critical_secrets()

    # Telemetry before anything else, so startup itself is traced. A disabled
    # or unreachable collector logs a warning and the API starts regardless —
    # observability must not be able to cause the outage it exists to diagnose.
    settings = get_settings()
    setup_telemetry(settings)

    # Startup: Initialize database and create tables
    await init_database()
    engine = get_engine()
    instrument_engine(engine, settings)
    async with engine.begin() as conn:
        # This creates all tables from SQLAlchemy models that inherit from Base
        await conn.run_sync(Base.metadata.create_all)

    # Ensure MinIO label bucket exists (idempotent)
    await _ensure_storage_buckets()

    yield
    # Shutdown
    await close_database()


def _validate_critical_secrets() -> None:
    """
    Warn (or raise in production) when critical secrets are still at their
    ``CHANGE_ME`` default placeholder values.

    Iterates over ``_CRITICAL_SETTINGS`` and checks each value against
    ``_CHANGE_ME_MARKER``.  In non-production environments this is a warning
    log so developers are reminded to configure their ``.env``.  In production
    it raises ``RuntimeError`` to prevent a misconfigured deployment from
    accepting real traffic.

    Args:
        None

    Returns:
        None

    Raises:
        RuntimeError: In production when any critical secret is still a
                      ``CHANGE_ME`` placeholder.
    """
    settings = get_settings()

    for key in _CRITICAL_SETTINGS:
        value: str = getattr(settings, key, "")
        if _CHANGE_ME_MARKER in value:
            message = (
                f"Critical secret '{key}' is still set to its default "
                f"placeholder value (contains '{_CHANGE_ME_MARKER}'). "
                "Set a real value in your .env or environment."
            )
            if settings.environment.is_production():
                raise RuntimeError(message)
            logger.warning(message, extra={"setting": key})


async def _ensure_storage_buckets() -> None:
    """
    Create the shipping-label MinIO bucket if it does not already exist.

    Called once on FastAPI startup.  Idempotent — safe to run on every
    restart.  Failures are logged as warnings and do not block startup,
    since the bucket may already exist and is only required at upload time.

    Returns:
        None
    """
    settings = get_settings()
    adapter = build_minio_adapter(
        endpoint_url=settings.storage_endpoint_url,
        access_key=settings.storage_access_key,
        secret_key=settings.storage_secret_key,
        region=settings.storage_region,
    )
    try:
        await adapter.ensure_bucket(settings.storage_bucket_labels)
        logger.info(
            "Storage bucket ready",
            extra={"bucket": settings.storage_bucket_labels},
        )
    except Exception as exc:
        logger.warning(
            "Could not ensure storage bucket on startup — will retry at first upload",
            extra={"bucket": settings.storage_bucket_labels, "error": str(exc)},
        )
