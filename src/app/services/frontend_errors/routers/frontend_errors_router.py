"""
Frontend Error Router

    POST /v1/telemetry/errors        — report uncaught browser errors (public)
    GET  /v1/admin/telemetry/errors  — read them, grouped (admin)

The report endpoint is public because the storefront's visitors are not signed
in, and an error that happens before login is exactly the one worth catching.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.analytics.functions import build_period
from app.shared.config import get_settings
from app.shared.database.session import get_session_dependency
from app.shared.exceptions import NotFoundError
from app.shared.logger import get_logger
from app.shared.rate_limit import limiter

from ..functions import coarse_browser
from ..models import (
    ErrorGroup,
    FrontendErrorBatch,
    FrontendErrorIngestResponse,
    FrontendErrorsResponse,
)
from ..services import FrontendErrorRepository

logger = get_logger(__name__)

report_router = APIRouter()
admin_router = APIRouter()

# Deliberately tighter than the analytics ingest. A component throwing inside a
# render loop is the normal failure mode here, and it will report as fast as the
# browser can loop.
_REPORT_RATE_LIMIT = "30/minute"


@report_router.post(
    "/errors",
    response_model=FrontendErrorIngestResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Report uncaught frontend errors",
    description=(
        "Accepts uncaught errors from the storefront or admin UI.\n\n"
        "Public, because storefront visitors are not signed in and an error "
        "before login is exactly the one worth catching. Records no IP, no raw "
        "user agent and no identity — the user agent is reduced server-side to "
        "a coarse family and major version, which is enough to reproduce a bug "
        "and not enough to recognise anyone.\n\n"
        "Disabled unless `FRONTEND_ERRORS_ENABLED` is set, returning 404 while off."
    ),
    responses={
        404: {"description": "Frontend error reporting is not enabled."},
        429: {"description": "Rate limit exceeded."},
    },
)
@limiter.limit(_REPORT_RATE_LIMIT)
async def report_errors(
    request: Request,
    batch: FrontendErrorBatch,
    session: AsyncSession = Depends(get_session_dependency),
) -> FrontendErrorIngestResponse:
    settings = get_settings()

    if not settings.frontend_errors_enabled:
        raise NotFoundError(
            message="Frontend error reporting is not enabled on this deployment",
            context={"setting": "FRONTEND_ERRORS_ENABLED"},
        )

    # Read here and reduced immediately. The raw string never reaches storage.
    browser = coarse_browser(request.headers.get("user-agent"))

    repository = FrontendErrorRepository(session)
    accepted, rejected = await repository.record(batch.errors, browser)

    if accepted:
        logger.warning(
            "Frontend errors reported",
            extra={
                "count": accepted,
                "app": batch.errors[0].app.value,
                "first_message": batch.errors[0].message[:200],
                "browser": browser,
            },
        )

    return FrontendErrorIngestResponse(
        success=True,
        message="Errors recorded",
        accepted=accepted,
        rejected=rejected,
    )


@admin_router.get(
    "/errors",
    response_model=FrontendErrorsResponse,
    summary="Frontend errors, grouped (admin)",
    description=(
        "Distinct errors with occurrence counts, ordered by frequency.\n\n"
        "Grouped by application, error class and message rather than by stack: "
        "the same fault reached from two routes produces two stacks and is one "
        "bug.\n\n"
        "Reports only what browsers managed to send. An error that breaks a page "
        "badly enough to stop the reporter is the one that will not appear here, "
        "so a quiet report is weaker evidence than a noisy one."
    ),
    dependencies=[Depends(get_settings)],
)
async def list_errors(
    date_from: date | None = Query(None, alias="from"),
    date_to: date | None = Query(None, alias="to"),
    app: str | None = Query(None, pattern="^(storefront|admin)$"),
    limit: int = Query(25, ge=1, le=200),
    session: AsyncSession = Depends(get_session_dependency),
) -> FrontendErrorsResponse:
    settings = get_settings()
    period = build_period(date_from, date_to, settings.shop_timezone, default_days=7)

    repository = FrontendErrorRepository(session)
    groups = await repository.grouped(period.start, period.end, app, limit)
    total = await repository.total(period.start, period.end, app)

    return FrontendErrorsResponse(
        success=True,
        message="Frontend errors retrieved successfully",
        enabled=settings.frontend_errors_enabled,
        total_occurrences=total,
        groups=[ErrorGroup(**group) for group in groups],
    )
