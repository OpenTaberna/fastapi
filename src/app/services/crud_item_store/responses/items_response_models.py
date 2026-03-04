"""
Item Response Models

API response schemas for item endpoints.
"""

from datetime import datetime
from uuid import UUID

from pydantic import ConfigDict, Field

from ..models import ItemBase


class ItemResponse(ItemBase):
    """
    Schema for item API responses.

    Extends ItemBase with database-generated fields like UUID and timestamps.
    Used for returning item data from GET, POST, PATCH endpoints.
    """

    uuid: UUID = Field(..., description="Unique item identifier")
    created_at: datetime = Field(..., description="Item creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    model_config = ConfigDict(from_attributes=True)
