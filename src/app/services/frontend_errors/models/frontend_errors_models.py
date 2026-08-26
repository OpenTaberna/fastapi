"""
Frontend Error Schemas

The report endpoint is public, so this schema is a boundary against hostile and
merely broken input alike. A component erroring inside a render loop is not an
attack, and it will still send thousands of reports a second if nothing stops
it.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.shared.responses import BaseResponse

MAX_ERRORS_PER_BATCH = 10
MAX_STACK_CHARS = 4000


class FrontendApp(str, Enum):
    """Which application reported. Closed, so it cannot become a free-text field."""

    STOREFRONT = "storefront"
    ADMIN = "admin"


class FrontendErrorInput(BaseModel):
    """One uncaught error."""

    model_config = ConfigDict(extra="forbid")

    app: FrontendApp
    name: str = Field(max_length=120)
    message: str = Field(max_length=500)
    stack: str | None = Field(default=None)
    path: str | None = Field(default=None, max_length=255)
    occurred_at: datetime

    @field_validator("path", mode="before")
    @classmethod
    def strip_query_string(cls, value: object) -> object:
        """Same reasoning as storefront events: query strings carry accidents."""
        if not isinstance(value, str):
            return value
        for separator in ("?", "#"):
            value = value.split(separator, 1)[0]
        return value[:255]

    @field_validator("stack", mode="before")
    @classmethod
    def bound_stack(cls, value: object) -> object:
        """
        Truncate rather than reject.

        A stack trace is unbounded input from a public endpoint, but it is also
        the single most useful field here. Cutting it keeps the top frames,
        which is where the fault is.
        """
        if not isinstance(value, str):
            return value
        if len(value) <= MAX_STACK_CHARS:
            return value
        return value[:MAX_STACK_CHARS] + "\n… truncated"


class FrontendErrorBatch(BaseModel):
    """A batch from one browser."""

    model_config = ConfigDict(extra="forbid")

    errors: list[FrontendErrorInput] = Field(
        min_length=1, max_length=MAX_ERRORS_PER_BATCH
    )


class FrontendErrorIngestResponse(BaseResponse):
    """How many reports were kept."""

    accepted: int
    rejected: int


class ErrorGroup(BaseModel):
    """Distinct errors, with how often and how recently they happened."""

    app: str
    name: str
    message: str
    occurrences: int
    affected_paths: int = Field(description="Distinct routes this error occurred on")
    browsers: list[str] = Field(
        default_factory=list, description="Coarse browser labels that hit it"
    )
    first_seen: datetime
    last_seen: datetime
    sample_stack: str | None = None


class FrontendErrorsResponse(BaseResponse):
    """
    Errors grouped, because one bug produces thousands of identical rows.

    Reports only what browsers managed to send. An error that breaks the page
    badly enough to stop the reporter is the one you will not see here, so a
    quiet report is weaker evidence than a noisy one.
    """

    enabled: bool
    total_occurrences: int
    groups: list[ErrorGroup] = Field(default_factory=list)
