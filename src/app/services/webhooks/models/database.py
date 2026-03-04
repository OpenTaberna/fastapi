"""
Webhooks Database Models

SQLAlchemy ORM model for the webhook event inbox.

Purpose: Idempotency. Before processing any incoming webhook event, the
handler checks this table. If the (provider, event_id) pair already exists,
the event is a duplicate and the handler returns 200 immediately without
side effects. Otherwise it inserts a row and processes the event inside the
same DB transaction — guaranteeing exactly-once processing.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.database.base import Base


class WebhookEventDB(Base):
    """
    Webhook event inbox model.

    Stores every received and accepted webhook event for idempotency and audit.

    Columns:
        id:           UUID primary key.
        provider:     Source of the webhook (e.g. 'stripe').
        event_id:     Provider-side event ID (e.g. Stripe evt_xxx).
        payload:      Raw event payload stored as JSONB for auditability.
        processed_at: Timestamp when the event was successfully processed.
                      NULL means the event was received but processing failed.
        created_at:   When the event was first received.

    Constraints:
        UNIQUE(provider, event_id) — prevents duplicate processing.
    """

    __tablename__ = "webhook_events"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        doc="Internal unique identifier",
    )

    provider: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        doc="Webhook source provider (e.g. 'stripe')",
    )

    event_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        doc="Provider-side event ID — unique per provider",
    )

    payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        doc="Raw event payload for auditability",
    )

    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
        doc="When the event was successfully processed (NULL = not yet processed)",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        doc="When the event record was created",
    )

    __table_args__ = (
        UniqueConstraint("provider", "event_id", name="uq_webhook_events_provider_event_id"),
    )

    def __repr__(self) -> str:
        return (
            f"WebhookEventDB(id={self.id}, provider={self.provider!r}, "
            f"event_id={self.event_id!r}, processed_at={self.processed_at})"
        )
