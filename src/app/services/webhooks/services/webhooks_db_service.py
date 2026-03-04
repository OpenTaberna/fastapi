"""
Webhooks Database Services

Repository for webhook event inbox.

The key operation here is is_duplicate() — it must be called inside the
same DB transaction as the event processing to guarantee exactly-once semantics.
"""

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database.repository import BaseRepository
from ..models.webhooks_db_models import WebhookEventDB


class WebhookEventRepository(BaseRepository[WebhookEventDB]):
    """
    Repository for webhook event inbox operations.
    """

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(WebhookEventDB, session)

    async def is_duplicate(self, provider: str, event_id: str) -> bool:
        """
        Check whether an event has already been received.

        This is the idempotency guard. Must be called inside the same
        transaction that processes the event, so a concurrent duplicate
        hits the UNIQUE constraint rather than passing through.

        Args:
            provider: Webhook source (e.g. 'stripe').
            event_id: Provider-side event ID (e.g. Stripe evt_xxx).

        Returns:
            True if a record with this (provider, event_id) already exists.
        """
        stmt = select(self.model.id).where(
            and_(
                self.model.provider == provider,
                self.model.event_id == event_id,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None


# ---------------------------------------------------------------------------
# Dependency injection factory
# ---------------------------------------------------------------------------


def get_webhook_event_repository(session: AsyncSession) -> WebhookEventRepository:
    """Factory for WebhookEventRepository — use with FastAPI Depends."""
    return WebhookEventRepository(session)
