"""
Outbox Event Database Model

Implements the Transactional Outbox Pattern for reliable job enqueuing.

The Problem it solves:
    Enqueuing a job directly into Redis from an HTTP handler has a race
    condition: the DB transaction commits but Redis is unavailable, or the
    process crashes between the DB commit and the Redis enqueue.  The job
    is lost without any record.

The Solution:
    1. Write the outbox event in the *same* DB transaction as the business
       data (e.g. creating a ShipmentDB record).
    2. A background poller (ARQ scheduled job) periodically reads PENDING
       rows and enqueues the corresponding ARQ jobs into Redis.
    3. Once the ARQ job is successfully enqueued, the row is marked ENQUEUED.
    4. If the job succeeds, the row is marked DONE.  If it permanently fails
       (dead-lettered), it is marked DEAD.

Guarantees:
    - At-least-once delivery: even if Redis restarts, the poller will
      re-enqueue any event that has not yet reached DONE.
    - Idempotency: each job carries the outbox_event_id so the ARQ task
      can detect and skip duplicate executions.
"""

from enum import Enum
from uuid import UUID, uuid4

from sqlalchemy import Index, String, Text, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.database.base import Base, TimestampMixin


class OutboxStatus(str, Enum):
    """
    Lifecycle states of an outbox event row.

    PENDING  → written in the business transaction; not yet handed to ARQ.
    ENQUEUED → ARQ job created in Redis; waiting to execute.
    DONE     → ARQ job completed successfully.
    DEAD     → ARQ job exhausted all retries; requires manual investigation.
    """

    PENDING = "pending"
    ENQUEUED = "enqueued"
    DONE = "done"
    DEAD = "dead"


class OutboxEventDB(Base, TimestampMixin):
    """
    Outbox event row — one record per job to be enqueued.

    Columns:
        id:           UUID primary key.
        event_type:   Logical job type name (e.g. "create_label").
        payload:      JSON-serialized job arguments.
        status:       Current lifecycle state (OutboxStatus).
        arq_job_id:   ARQ job ID once enqueued — used to track/deduplicate.
        attempts:     How many times the poller has tried to enqueue this event.
        created_at:   Inherited from TimestampMixin.
        updated_at:   Inherited from TimestampMixin.
    """

    __tablename__ = "outbox_events"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        doc="Internal unique identifier",
    )

    event_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        doc="Logical job type (e.g. 'create_label')",
    )

    payload: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="JSON-serialized job arguments",
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=OutboxStatus.PENDING.value,
        server_default=text("'pending'"),
        index=True,
        doc="Current lifecycle state: pending | enqueued | done | dead",
    )

    arq_job_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        doc="ARQ job ID once the event has been enqueued into Redis",
    )

    attempts: Mapped[int] = mapped_column(
        default=0,
        server_default=text("0"),
        nullable=False,
        doc="Number of times the outbox poller has attempted to enqueue this event",
    )

    __table_args__ = (Index("ix_outbox_events_status_created", "status", "created_at"),)

    def __repr__(self) -> str:
        return (
            f"OutboxEventDB(id={self.id}, event_type={self.event_type!r}, "
            f"status={self.status!r}, attempts={self.attempts})"
        )
