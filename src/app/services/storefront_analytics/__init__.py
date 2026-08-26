"""
Storefront Analytics Service

Anonymous shopper telemetry from the storefront, so the funnel can begin before
an order exists.

Endpoints:
    POST /analytics/events — record anonymous storefront events (public)

The admin-facing read side lives in `services/analytics`, alongside the order
figures it has to be read together with.

Usage:
    from app.services.storefront_analytics import storefront_analytics_api_router
    app.include_router(storefront_analytics_api_router, prefix="/v1")
"""

from fastapi import APIRouter

from .routers import storefront_analytics_router

storefront_analytics_api_router = APIRouter(
    prefix="/analytics",
    tags=["Storefront Analytics"],
)
storefront_analytics_api_router.include_router(storefront_analytics_router)

__all__ = ["storefront_analytics_api_router"]
