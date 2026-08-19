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
from app.shared.storage.minio_adapter import build_minio_adapter

logger = get_logger(__name__)


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
    # Startup: Initialize database and create tables
    await init_database()
    engine = get_engine()
    async with engine.begin() as conn:
        # This creates all tables from SQLAlchemy models that inherit from Base
        await conn.run_sync(Base.metadata.create_all)

    # Ensure MinIO label bucket exists (idempotent)
    await _ensure_storage_buckets()

    yield
    # Shutdown
    await close_database()


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
