"""
Orders Service

Entry point for the order-processing service module.
This is a self-contained "mini-API" for managing the order lifecycle.

Endpoints (Phase 1):
    POST   /orders                 — Create a draft order
    GET    /orders/{id}            — Get a single order (own orders only)
    DELETE /orders/{id}            — Cancel a draft order
    POST   /orders/{id}/checkout   — Start checkout (DRAFT → PENDING_PAYMENT)
    POST   /orders/webhooks/stripe — Handle Stripe payment webhook

Usage:
    from app.services.orders import router as orders_router
    app.include_router(orders_router, prefix="/v1")
"""

from fastapi import APIRouter

from .routers import orders_router, webhooks_router

# Router for /orders/* endpoints
orders_api_router = APIRouter(
    prefix="/orders",
    tags=["Orders"],
)
orders_api_router.include_router(orders_router.router)

# Router for /webhooks/* endpoints
webhooks_api_router = APIRouter(
    prefix="/webhooks",
    tags=["Webhooks"],
)
webhooks_api_router.include_router(webhooks_router.router)

__all__ = ["orders_api_router", "webhooks_api_router"]
