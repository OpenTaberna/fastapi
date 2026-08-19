"""
Outbox Enqueue Helper

Provides enqueue_label_job — the single function that writes a CREATE_LABEL
outbox event into the database within an already-open transaction.

This is the only write path for label jobs.  Callers must NOT enqueue ARQ
jobs directly; all job creation goes through this function so the outbox
guarantee holds:

    The outbox event and the business data (e.g. ShipmentDB row) are committed
    in the same DB transaction.  If the process crashes before Redis is
    reached, the outbox poller in the ARQ worker will re-enqueue on the next
    sweep — guaranteeing at-least-once delivery with no data loss.
"""

import json
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.logger import get_logger

from ..models.outbox_db_models import OutboxEventDB, OutboxStatus

logger = get_logger(__name__)

# Event type constant — must match the ARQ task function name in jobs/
CREATE_LABEL_EVENT = "create_label"


async def enqueue_label_job(
    session: AsyncSession,
    shipment_id: UUID,
    order_id: UUID,
    label_format: str,
) -> OutboxEventDB:
    """
    Write a CREATE_LABEL outbox event row within the caller's DB transaction.

    The caller is responsible for opening (and committing) the transaction.
    This function only inserts the row — it does NOT touch Redis.

    Args:
        session:      Active AsyncSession with an open transaction.
        shipment_id:  UUID of the ShipmentDB record to generate a label for.
        order_id:     UUID of the associated OrderDB record.
        label_format: "pdf" or "zpl" — passed through to the ARQ job.

    Returns:
        The newly created OutboxEventDB row (status=PENDING).
    """
    payload = json.dumps(
        {
            "shipment_id": str(shipment_id),
            "order_id": str(order_id),
            "label_format": label_format,
        }
    )

    event = OutboxEventDB(
        event_type=CREATE_LABEL_EVENT,
        payload=payload,
        status=OutboxStatus.PENDING.value,
        attempts=0,
    )
    session.add(event)
    # Flush to generate the PK so callers can read event.id if needed,
    # but do NOT commit — the caller owns the transaction boundary.
    await session.flush()

    logger.info(
        "Outbox event written",
        extra={
            "event_id": str(event.id),
            "event_type": CREATE_LABEL_EVENT,
            "shipment_id": str(shipment_id),
            "order_id": str(order_id),
        },
    )
    return event
