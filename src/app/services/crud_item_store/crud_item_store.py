"""
CRUD Item Store Service

Entry point for the item-store service module.
This is a complete "mini-API" for managing store items.

Features:
- Full CRUD operations for items
- Advanced filtering and search
- Inventory management
- Price management
- Category management

Usage:
    from app.services.crud_item_store import crud_item_store
    app.include_router(crud_item_store.router, prefix="/api/v1")
"""

from fastapi import APIRouter

# Import routers
from .routers import items

# Create the main router for this service
router = APIRouter(
    prefix="/items",
    tags=["Item Store"],
)

# Include sub-routers
router.include_router(items.router)

__all__ = ["router"]
