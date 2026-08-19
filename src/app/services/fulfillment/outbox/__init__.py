"""
Fulfillment Outbox Package

Provides the OutboxEvent DB model, repository, and the enqueue_label_job
helper that writes an outbox event atomically inside an open DB transaction.

Usage:
    async with transaction(session):
        shipment = await shipment_repo.create(...)
        await enqueue_label_job(session, shipment_id=shipment.id, order_id=order.id)
    # The outbox poller in the ARQ worker picks up the event and enqueues
    # the actual ARQ job — guaranteeing at-least-once delivery.
"""

from .models.outbox_db_models import OutboxEventDB, OutboxStatus
from .services.outbox_db_service import OutboxRepository, get_outbox_repository
from .services.outbox_enqueue import enqueue_label_job

__all__ = [
    "OutboxEventDB",
    "OutboxStatus",
    "OutboxRepository",
    "get_outbox_repository",
    "enqueue_label_job",
]
