"""
Returns Service — Phase 4.4

Handles customer return requests (RMA — Return Merchandise Authorization).

Endpoints:
    POST  /orders/{id}/returns  — Customer files a return for a SHIPPED order
    PATCH /admin/returns/{id}   — Admin approves / rejects / completes an RMA

Usage:
    from app.services.returns import returns_api_router, admin_returns_api_router
    app.include_router(returns_api_router, prefix="/v1")
    app.include_router(admin_returns_api_router, prefix="/v1")
"""

from fastapi import APIRouter

from .routers.admin_returns_router import router as _admin_returns_router
from .routers.returns_router import router as _returns_router

# Customer-facing: POST /orders/{id}/returns
returns_api_router = APIRouter(prefix="/orders", tags=["Orders"])
returns_api_router.include_router(_returns_router)

# Admin-facing: PATCH /admin/returns/{id}
admin_returns_api_router = APIRouter(prefix="/admin/returns", tags=["Admin"])
admin_returns_api_router.include_router(_admin_returns_router)

__all__ = ["returns_api_router", "admin_returns_api_router"]
