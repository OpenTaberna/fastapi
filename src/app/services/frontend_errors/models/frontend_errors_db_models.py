"""
Frontend Error Database Model

One row per reported uncaught error from a browser.

As with storefront_events, what is absent matters: no IP address, no raw user
agent, no customer id, no email. `browser` holds a coarse family and major
version parsed server-side — enough to reproduce a bug, not enough to recognise
anyone.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Index, String, Text, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.database.base import Base


class FrontendErrorDB(Base):
    """An uncaught error reported by one of the frontends."""

    __tablename__ = "frontend_errors"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )

    app: Mapped[str] = mapped_column(
        String(20), nullable=False, doc="storefront | admin"
    )
    name: Mapped[str] = mapped_column(
        String(120), nullable=False, doc="Error class, e.g. TypeError"
    )
    message: Mapped[str] = mapped_column(String(500), nullable=False)
    stack: Mapped[str | None] = mapped_column(
        Text, nullable=True, doc="Truncated at ingest — a full trace is unbounded input"
    )
    path: Mapped[str | None] = mapped_column(
        String(255), nullable=True, doc="Route only; query strings are stripped"
    )
    browser: Mapped[str] = mapped_column(
        String(60),
        nullable=False,
        server_default=text("'unknown'"),
        doc="Coarse family and major version. Never the raw user agent.",
    )

    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        Index("ix_frontend_errors_occurred_at", "occurred_at"),
        Index("ix_frontend_errors_app_occurred", "app", "occurred_at"),
        # Grouping is the only way anyone reads this table: one bug in a render
        # loop produces thousands of identical rows, and the useful question is
        # "which distinct errors, how often".
        Index("ix_frontend_errors_grouping", "app", "name", "message"),
    )

    def __repr__(self) -> str:
        return f"FrontendErrorDB(id={self.id}, app={self.app!r}, name={self.name!r})"
