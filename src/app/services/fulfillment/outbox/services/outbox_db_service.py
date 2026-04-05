"""
Outbox Repository

Data access layer for OutboxEventDB rows.

Extends BaseRepository with two domain-specific queries:
    - list_pending: fetch all PENDING rows ordered by creation time
                    (used by the outbox poller in the ARQ worker).
    - mark_enqueued: atomically set status=ENQUEUED and record the ARQ job ID.
    - mark_done:     set status=DONE after the ARQ job completes successfully.
    - mark_dead:     set status=DEAD after exhausting all retries.
"""

import json
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database.repository import BaseRepository

from ..models.outbox_db_models import OutboxEventDB, OutboxStatus


class OutboxRepository(BaseRepository[OutboxEventDB]):
    """
    Repository for outbox event database operations.

    Extends BaseRepository with outbox-specific queries needed by the
    poller and the job completion callbacks.
    """

    def __init__(self, session: AsyncSession) -> None:
        """
        Args:
            session: Active AsyncSession from the connection pool.
        """
        super().__init__(OutboxEventDB, session)

    async def list_pending(self, limit: int = 100) -> list[OutboxEventDB]:
        """
        Fetch PENDING outbox events ordered oldest-first.

        Called by the outbox poller to find events that need to be handed
        off to the ARQ job queue.

        Args:
            limit: Maximum number of rows to return per sweep.

        Returns:
            List of OutboxEventDB rows with status=PENDING, oldest first.
        """
        result = await self.session.execute(
            select(OutboxEventDB)
            .where(OutboxEventDB.status == OutboxStatus.PENDING.value)
            .order_by(OutboxEventDB.created_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def mark_enqueued(self, event_id: UUID, arq_job_id: str) -> OutboxEventDB:
        """
        Advance an event from PENDING to ENQUEUED and record the ARQ job ID.

        Args:
            event_id:   UUID of the outbox event row to update.
            arq_job_id: ARQ job ID returned by arq.ArqRedis.enqueue_job().

        Returns:
            Updated OutboxEventDB row.
        """
        return await self.update(
            event_id,
            status=OutboxStatus.ENQUEUED.value,
            arq_job_id=arq_job_id,
        )

    async def mark_done(self, event_id: UUID) -> OutboxEventDB:
        """
        Advance an event to DONE after its ARQ job completed successfully.

        Args:
            event_id: UUID of the outbox event row to mark as done.

        Returns:
            Updated OutboxEventDB row.
        """
        return await self.update(event_id, status=OutboxStatus.DONE.value)

    async def mark_dead(self, event_id: UUID) -> OutboxEventDB:
        """
        Advance an event to DEAD after all ARQ retries were exhausted.

        Args:
            event_id: UUID of the outbox event row to dead-letter.

        Returns:
            Updated OutboxEventDB row.
        """
        return await self.update(event_id, status=OutboxStatus.DEAD.value)

    async def increment_attempts(self, event_id: UUID) -> OutboxEventDB:
        """
        Increment the attempt counter on an outbox event row.

        Called each time the poller processes the event, whether or not
        the enqueue succeeds, so stale rows do not loop forever.

        Args:
            event_id: UUID of the outbox event row to update.

        Returns:
            Updated OutboxEventDB row.
        """
        event = await self.get(event_id)
        return await self.update(event_id, attempts=(event.attempts or 0) + 1)

    async def get_payload(self, event_id: UUID) -> dict:
        """
        Fetch and deserialize the JSON payload of an outbox event.

        Args:
            event_id: UUID of the outbox event to read.

        Returns:
            Deserialized payload dict.
        """
        event = await self.get(event_id)
        return json.loads(event.payload)


# ---------------------------------------------------------------------------
# Dependency injection factory
# ---------------------------------------------------------------------------


def get_outbox_repository(session: AsyncSession) -> OutboxRepository:
    """
    Factory for OutboxRepository — use with FastAPI Depends or ARQ context.

    Args:
        session: Active AsyncSession.

    Returns:
        Configured OutboxRepository instance.
    """
    return OutboxRepository(session)
