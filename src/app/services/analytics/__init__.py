"""
Analytics Service

Admin-only commercial reporting, computed in SQL over the whole order history.

Endpoints:
    GET /admin/analytics/summary     — headline figures vs the previous period
    GET /admin/analytics/timeseries  — the same figures bucketed over time
    GET /admin/analytics/products    — per-SKU performance and dead stock
    GET /admin/analytics/funnel      — where orders stop

Usage:
    from app.services.analytics import analytics_api_router
    app.include_router(analytics_api_router, prefix="/v1")
"""

from fastapi import APIRouter

from .routers import analytics_router

analytics_api_router = APIRouter(
    prefix="/admin/analytics",
    tags=["Analytics"],
)
analytics_api_router.include_router(analytics_router)

__all__ = ["analytics_api_router"]
