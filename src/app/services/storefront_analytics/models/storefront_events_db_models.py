"""
Storefront Analytics Database Models

One table holding anonymous shopper events sent by the storefront.

**What is deliberately not here matters more than what is.** There is no
customer id, no email, no IP address and no user agent. A shopper is identified
only by `session_id`, an opaque value the browser generates and discards when
the tab closes. Nothing in this table can be traced to a person, which is what
keeps the shop free of a consent banner and the operator out of a category of
obligation nobody wants.

`order_id` is the single join back to identified data, and it points at an order
the shopper themselves created — it reveals nothing the orders table does not
already hold.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Index, String, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.database.base import Base


class StorefrontEventDB(Base):
    """A single anonymous interaction in the storefront."""

    __tablename__ = "storefront_events"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )

    session_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        doc="Opaque, browser-generated, per-session. Not a user identifier.",
    )

    event_type: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        doc="page_view | product_view | add_to_cart | checkout_started",
    )

    path: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        doc="Route path only. Query strings are stripped before storage.",
    )

    sku: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        doc="Product the event concerns, for product_view and add_to_cart.",
    )

    order_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=True,
        doc=(
            "Set on checkout_started. Deliberately not a foreign key: the event "
            "is a record of what a browser reported, and must survive the order "
            "being deleted rather than disappearing with it and silently "
            "improving the conversion rate."
        ),
    )

    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        doc="When the browser says it happened. Clamped by the API on ingest.",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        doc="When the API stored it. Trustworthy, unlike occurred_at.",
    )

    __table_args__ = (
        Index("ix_storefront_events_occurred_at", "occurred_at"),
        Index("ix_storefront_events_type_occurred", "event_type", "occurred_at"),
        Index("ix_storefront_events_session", "session_id"),
    )

    def __repr__(self) -> str:
        return (
            f"StorefrontEventDB(id={self.id}, event_type={self.event_type!r}, "
            f"session_id={self.session_id!r})"
        )
