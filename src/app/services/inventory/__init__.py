"""
Inventory Service Package

Handles stock levels and reservations.

Endpoints:
    POST   /admin/inventory              — Create inventory record for a SKU
    GET    /admin/inventory              — List all inventory items (paginated)
    GET    /admin/inventory/by-sku/{sku} — Get inventory item by SKU
    GET    /admin/inventory/{id}         — Get inventory item by UUID
    PATCH  /admin/inventory/{id}         — Update on_hand stock count
    DELETE /admin/inventory/{id}         — Remove an inventory record

Usage:
    from app.services.inventory import inventory_api_router
    app.include_router(inventory_api_router, prefix="/v1")
"""

from fastapi import APIRouter

from .routers import inventory_router

inventory_api_router = APIRouter(
    prefix="/admin/inventory",
    tags=["Inventory"],
)
inventory_api_router.include_router(inventory_router)

__all__ = ["inventory_api_router"]

from .routers import inventory_router

inventory_api_router = APIRouter(
    prefix="/admin/inventory",
    tags=["Admin", "Inventory"],
)
inventory_api_router.include_router(inventory_router)

__all__ = ["inventory_api_router"]
