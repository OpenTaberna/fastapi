"""
Application Lifespan Management

Handles startup and shutdown events for the FastAPI application,
including database initialization and cleanup.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.shared.database.base import Base
from app.shared.database.engine import close_database, get_engine, init_database


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan events.

    Startup:
        - Initialize database connection pool
        - Create all tables from SQLAlchemy models

    Shutdown:
        - Close database connections gracefully
    """
    # Startup: Initialize database and create tables
    await init_database()
    engine = get_engine()
    async with engine.begin() as conn:
        # This creates all tables from SQLAlchemy models that inherit from Base
        await conn.run_sync(Base.metadata.create_all)
    yield
    # Shutdown
    await close_database()
