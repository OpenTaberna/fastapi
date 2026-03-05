"""
Webhooks Database Services

Repository for webhook event inbox.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database.repository import BaseRepository
from ..models.webhooks_db_models import WebhookEventDB


class WebhookEventRepository(BaseRepository[WebhookEventDB]):
    """
    Repository for webhook event inbox operations.
    """

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(WebhookEventDB, session)


# ---------------------------------------------------------------------------
# Dependency injection factory
# ---------------------------------------------------------------------------


def get_webhook_event_repository(session: AsyncSession) -> WebhookEventRepository:
    """Factory for WebhookEventRepository — use with FastAPI Depends."""
    return WebhookEventRepository(session)
