"""
Webhooks Pydantic Schemas
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class WebhookEventCreate(BaseModel):
    """
    Schema for inserting a new webhook event record.

    Used internally by the webhook handler — never exposed to the public API.
    """

    provider: str = Field(..., description="Webhook source provider (e.g. 'stripe')")
    event_id: str = Field(..., description="Provider-side event ID")
    payload: dict = Field(..., description="Raw event payload")


class WebhookEventResponse(BaseModel):
    """Webhook event response schema — for audit/admin views."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Internal event UUID")
    provider: str = Field(..., description="Webhook source provider")
    event_id: str = Field(..., description="Provider-side event ID")
    payload: dict = Field(..., description="Raw event payload")
    processed_at: datetime | None = Field(
        default=None, description="Processing timestamp"
    )
    created_at: datetime = Field(..., description="Record creation timestamp")
