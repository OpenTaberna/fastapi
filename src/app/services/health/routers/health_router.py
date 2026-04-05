"""
Health Router — Phase 4.1

FastAPI router for liveness and readiness checks:

    GET /health        — Liveness: returns 200 if the API process is alive
    GET /health/ready  — Readiness: returns 200 when DB + Redis are reachable,
                         503 when any dependency is unhealthy
"""

from datetime import UTC, datetime

import redis.asyncio as aioredis
from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.shared.config import get_settings
from app.shared.database.health import check_database_health
from app.shared.logger import get_logger

from ..models import HealthResponse, ReadinessResponse
from ..models.health_models import DependencyStatus

logger = get_logger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# GET /health — Liveness check
# ---------------------------------------------------------------------------


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Liveness check",
    description=(
        "Returns **200 OK** as long as the API process is running and the "
        "event loop is responsive. Does not check external dependencies — "
        "use ``/health/ready`` for that."
    ),
    tags=["Health"],
)
async def liveness() -> HealthResponse:
    """
    Confirm that the API process is alive.

    Args:
        None

    Returns:
        HealthResponse with status='ok' and current UTC timestamp.
    """
    return HealthResponse(timestamp=datetime.now(UTC))


# ---------------------------------------------------------------------------
# GET /health/ready — Readiness check
# ---------------------------------------------------------------------------


@router.get(
    "/health/ready",
    summary="Readiness check",
    description=(
        "Checks that all critical dependencies (PostgreSQL, Redis) are "
        "reachable and responding.  Returns **200 OK** when every dependency "
        "is healthy.  Returns **503 Service Unavailable** with a "
        "``ReadinessResponse`` body when one or more dependencies are down."
    ),
    response_model=ReadinessResponse,
    tags=["Health"],
)
async def readiness() -> JSONResponse:
    """
    Check that all critical dependencies are reachable.

    Probes the database and Redis in parallel and returns a structured
    summary.  The HTTP status reflects the overall health:
        200 — all dependencies healthy
        503 — one or more dependencies unhealthy

    Args:
        None

    Returns:
        JSONResponse with ReadinessResponse body and status 200 or 503.
    """
    db_status = await _check_database()
    redis_status = await _check_redis()

    all_healthy = db_status.healthy and redis_status.healthy
    overall = "ok" if all_healthy else "degraded"

    body = ReadinessResponse(
        status=overall,
        timestamp=datetime.now(UTC),
        database=db_status,
        redis=redis_status,
    )

    http_status = (
        status.HTTP_200_OK if all_healthy else status.HTTP_503_SERVICE_UNAVAILABLE
    )

    logger.info(
        "Readiness check",
        extra={
            "status": overall,
            "db_healthy": db_status.healthy,
            "redis_healthy": redis_status.healthy,
        },
    )

    return JSONResponse(
        status_code=http_status,
        content=body.model_dump(mode="json"),
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


async def _check_database() -> DependencyStatus:
    """
    Probe the database with a simple SELECT 1 query.

    Args:
        None

    Returns:
        DependencyStatus with healthy flag, latency, and optional error string.
    """
    result = await check_database_health()
    return DependencyStatus(
        healthy=result["healthy"],
        latency_ms=result.get("latency_ms"),
        error=result.get("error"),
    )


async def _check_redis() -> DependencyStatus:
    """
    Probe Redis with a PING command.

    Establishes a short-lived connection from the settings URL, issues PING,
    and measures round-trip latency.  The connection is closed immediately
    after the check — this does not reuse the ARQ worker pool.

    Args:
        None

    Returns:
        DependencyStatus with healthy flag, latency, and optional error string.
    """
    settings = get_settings()
    start = datetime.now(UTC)

    try:
        client = aioredis.from_url(settings.redis_url, decode_responses=True)
        await client.ping()
        await client.aclose()

        latency_ms = (datetime.now(UTC) - start).total_seconds() * 1000
        return DependencyStatus(healthy=True, latency_ms=round(latency_ms, 2))

    except Exception as exc:
        latency_ms = (datetime.now(UTC) - start).total_seconds() * 1000
        logger.warning(
            "Redis health check failed",
            extra={"error": str(exc), "latency_ms": round(latency_ms, 2)},
        )
        return DependencyStatus(
            healthy=False,
            latency_ms=round(latency_ms, 2),
            error=str(exc),
        )
