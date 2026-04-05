"""
Fulfillment Service — Phase 3

DHL label generation, ARQ job queue, and outbox pattern.

Endpoints (mounted under /admin/orders by the admin router):
    POST  /admin/orders/{id}/label  — trigger label job via outbox
    GET   /admin/orders/{id}/label  — download label PDF/ZPL from storage

Usage:
    from app.services.fulfillment import fulfillment_api_router
    app.include_router(fulfillment_api_router, prefix="/v1")
"""

from fastapi import APIRouter

from .routers import fulfillment_router

fulfillment_api_router = APIRouter(
    prefix="/admin/orders",
    tags=["Admin"],
)
fulfillment_api_router.include_router(fulfillment_router)

__all__ = ["fulfillment_api_router"]
