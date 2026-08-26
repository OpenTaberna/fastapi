"""
Frontend Errors Service

Uncaught browser errors from the storefront and the admin UI.

S3 gave the API traces and metrics; neither can see a component that throws in
somebody's browser. The server returns 200, the metrics look healthy, and the
shop is broken for a real customer.

Endpoints:
    POST /telemetry/errors        — report (public, rate limited, opt-in)
    GET  /admin/telemetry/errors  — read, grouped (admin)
"""

from fastapi import APIRouter

from app.authorize import require_admin
from fastapi import Depends

from .routers import admin_router, report_router

frontend_errors_api_router = APIRouter(
    prefix="/telemetry",
    tags=["Frontend Errors"],
)
frontend_errors_api_router.include_router(report_router)

admin_frontend_errors_api_router = APIRouter(
    prefix="/admin/telemetry",
    tags=["Frontend Errors"],
    dependencies=[Depends(require_admin)],
)
admin_frontend_errors_api_router.include_router(admin_router)

__all__ = ["admin_frontend_errors_api_router", "frontend_errors_api_router"]
