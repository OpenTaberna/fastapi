"""
Storefront Analytics Schemas

The ingest endpoint is **public**. Anyone who can load the shop can post to it,
so validation here is a boundary against abuse rather than a convenience for a
well-behaved client: every field is bounded, the event vocabulary is closed, and
the batch size is capped.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.shared.responses import BaseResponse

# Cap on events per request. Enough for a page's worth of activity, small
# enough that a single request cannot be used to bulk-insert.
MAX_EVENTS_PER_BATCH = 50


class StorefrontEventType(str, Enum):
    """
    The closed set of things the storefront reports.

    Closed on purpose: an open string would let a client write arbitrary values
    into a table an administrator later reads, and would make the funnel
    definition drift silently as the frontend changed.
    """

    PAGE_VIEW = "page_view"
    PRODUCT_VIEW = "product_view"
    ADD_TO_CART = "add_to_cart"
    CHECKOUT_STARTED = "checkout_started"


class StorefrontEventInput(BaseModel):
    """One reported interaction."""

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(
        min_length=8,
        max_length=64,
        description="Opaque browser-generated id. Must not identify a person.",
    )
    event_type: StorefrontEventType
    path: str | None = Field(default=None, max_length=255)
    sku: str | None = Field(default=None, max_length=100)
    order_id: UUID | None = None
    occurred_at: datetime

    @field_validator("path", mode="before")
    @classmethod
    def strip_query_string(cls, value: object) -> object:
        """
        Keep the route, discard everything after ? or #, then bound the length.

        A query string is where personal data ends up by accident — an email in
        a share link, a token in a redirect. Dropping it at the boundary means
        it can never be stored, rather than relying on the client not to send it.

        Runs before validation rather than after so an over-long path is
        truncated rather than rejected. A long URL is a client being untidy, not
        a client being hostile, and discarding the whole event would lose a real
        page view over it.
        """
        if not isinstance(value, str):
            return value
        for separator in ("?", "#"):
            value = value.split(separator, 1)[0]
        return value[:255]


class StorefrontEventBatch(BaseModel):
    """A batch of events from one browser."""

    model_config = ConfigDict(extra="forbid")

    events: list[StorefrontEventInput] = Field(
        min_length=1,
        max_length=MAX_EVENTS_PER_BATCH,
        description=f"At most {MAX_EVENTS_PER_BATCH} events per request",
    )


class StorefrontIngestResponse(BaseResponse):
    """How many events were kept."""

    accepted: int = Field(description="Events stored")
    rejected: int = Field(
        description="Events discarded, e.g. a timestamp outside the accepted window"
    )
