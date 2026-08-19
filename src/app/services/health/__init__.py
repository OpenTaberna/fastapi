"""
Health Service — Phase 4.1

Provides liveness and readiness check endpoints:
    GET /health        — Liveness: API process is running
    GET /health/ready  — Readiness: DB + Redis are reachable

Usage:
    from app.services.health import health_api_router
    app.include_router(health_api_router)
"""

from fastapi import APIRouter

from .routers.health_router import router as health_router

health_api_router = APIRouter(tags=["Health"])
health_api_router.include_router(health_router)

__all__ = ["health_api_router"]
