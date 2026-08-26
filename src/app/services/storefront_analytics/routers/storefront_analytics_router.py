"""
Storefront Analytics Router

    POST /v1/analytics/events — anonymous shopper events from the storefront

**This endpoint is public.** Anyone able to load the shop can post to it, which
shapes every decision here:

- It is off unless the operator turns it on. Cloning OpenTaberna must not start
  collecting anything.
- It is rate limited, because an open write endpoint otherwise fills a table.
- It validates strictly against a closed event vocabulary, so a client cannot
  write arbitrary values into a table an administrator later reads.
- It stores nothing that identifies a person, so the worst an abusive client can
  achieve is noise in a report.

It returns 202: the events are accepted for storage, and the browser must not
wait on the outcome or retry on failure. Analytics that slow a shop down, or
that retry into a queue during an incident, have made things worse.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.config import get_settings
from app.shared.database.session import get_session_dependency
from app.shared.exceptions import NotFoundError
from app.shared.logger import get_logger
from app.shared.rate_limit import limiter

from ..models import StorefrontEventBatch, StorefrontIngestResponse
from ..services import StorefrontEventRepository

logger = get_logger(__name__)

router = APIRouter()

# Generous enough for a browsing session that batches on navigation, tight
# enough that a script cannot fill the table from one address.
_INGEST_RATE_LIMIT = "120/minute"


@router.post(
    "/events",
    response_model=StorefrontIngestResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Record anonymous storefront events",
    description=(
        "Accepts a batch of anonymous interaction events from the storefront.\n\n"
        "Requires no authentication and records nothing that identifies a person: "
        "no customer id, no email, no IP address and no user agent. A shopper is "
        "represented only by an opaque session id their own browser generated.\n\n"
        "Disabled unless the operator sets `STOREFRONT_ANALYTICS_ENABLED`, and "
        "returns 404 when off so a deployment that has not opted in does not "
        "advertise the capability.\n\n"
        "Returns 202: events are accepted for storage and the browser should "
        "neither wait on the result nor retry."
    ),
    responses={
        404: {"description": "Storefront analytics is not enabled on this deployment."},
        429: {"description": "Rate limit exceeded."},
    },
)
@limiter.limit(_INGEST_RATE_LIMIT)
async def record_events(
    request: Request,
    batch: StorefrontEventBatch,
    session: AsyncSession = Depends(get_session_dependency),
) -> StorefrontIngestResponse:
    settings = get_settings()

    if not settings.storefront_analytics_enabled:
        raise NotFoundError(
            message="Storefront analytics is not enabled on this deployment",
            context={"setting": "STOREFRONT_ANALYTICS_ENABLED"},
        )

    repository = StorefrontEventRepository(session)
    accepted, rejected = await repository.record(batch.events)

    return StorefrontIngestResponse(
        success=True,
        message="Events recorded",
        accepted=accepted,
        rejected=rejected,
    )
