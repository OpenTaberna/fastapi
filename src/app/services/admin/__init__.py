"""
Admin Service

Entry point for the admin fulfillment service module (Phase 2).
Provides admin-only endpoints for order management, packing documents,
manual shipment creation, and shipping confirmation.

Endpoints:
    GET    /admin/orders                    — Paginated order list (status filter)
    GET    /admin/orders/pick-list          — Batch pick list (all PAID orders)
    GET    /admin/orders/{id}               — Full order detail
    PATCH  /admin/orders/{id}/status        — Manual status override (audit log)
    GET    /admin/orders/{id}/packing-slip  — Printable HTML packing slip
    POST   /admin/orders/{id}/shipments     — Create shipment → READY_TO_SHIP
    POST   /admin/orders/{id}/ship          — Mark SHIPPED + send tracking email

Usage:
    from app.services.admin import admin_api_router
    app.include_router(admin_api_router, prefix="/v1")
"""

from fastapi import APIRouter

from .routers import admin_router

admin_api_router = APIRouter(
    prefix="/admin/orders",
    tags=["Admin"],
)
admin_api_router.include_router(admin_router)

__all__ = ["admin_api_router"]
