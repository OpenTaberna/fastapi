"""
Health Check Pydantic Schemas — Phase 4.1

Response models for the liveness and readiness endpoints.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """
    Liveness check response.

    Returned by ``GET /health``.  A 200 status means the API process is alive
    and the event loop is responsive.  No dependency checks are performed here
    — that is the job of the readiness endpoint.
    """

    status: str = Field(default="ok", description="Always 'ok' for a live process")
    timestamp: datetime = Field(..., description="UTC timestamp of the check")


class DependencyStatus(BaseModel):
    """
    Status report for a single external dependency (DB, Redis, etc.).
    """

    healthy: bool = Field(..., description="True if the dependency responded correctly")
    latency_ms: float | None = Field(
        default=None, description="Round-trip latency in milliseconds"
    )
    error: str | None = Field(default=None, description="Error message if unhealthy")


class ReadinessResponse(BaseModel):
    """
    Readiness check response.

    Returned by ``GET /health/ready``.  Checks that all critical dependencies
    (database, Redis) are reachable.  Returns 200 when every dependency is
    healthy, 503 Service Unavailable otherwise.
    """

    status: str = Field(
        ..., description="'ok' if all dependencies healthy, 'degraded' otherwise"
    )
    timestamp: datetime = Field(..., description="UTC timestamp of the check")
    database: DependencyStatus = Field(..., description="PostgreSQL connectivity")
    redis: DependencyStatus = Field(..., description="Redis connectivity")
