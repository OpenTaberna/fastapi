"""
Item Response Models

API response schemas for item endpoints.
"""

from datetime import datetime
from uuid import UUID

from pydantic import ConfigDict, Field

from ..models import ItemBase


_ITEM_EXAMPLE = {
    "uuid": "2f61e8db-1234-4abc-8def-426614174000",
    "sku": "CHAIR-RED-001",
    "status": "active",
    "name": "Red Wooden Chair",
    "slug": "red-wooden-chair",
    "short_description": "A comfortable red wooden chair.",
    "description": "<p>Handcrafted red wooden chair with ergonomic design.</p>",
    "categories": ["a1b2c3d4-0000-0000-0000-000000000001"],
    "brand": "WoodCraft",
    "price": {
        "amount": 4999,
        "currency": "EUR",
        "includes_tax": True,
        "original_amount": 5999,
        "tax_class": "standard",
    },
    "media": {
        "main_image": "https://cdn.example.com/items/chair-red-001.jpg",
        "gallery": [
            "https://cdn.example.com/items/chair-red-001-side.jpg",
            "https://cdn.example.com/items/chair-red-001-back.jpg",
        ],
    },
    "inventory": {
        "stock_quantity": 42,
        "stock_status": "in_stock",
        "allow_backorder": False,
    },
    "shipping": {
        "is_physical": True,
        "weight": {"value": 4.5, "unit": "kg"},
        "dimensions": {"width": 45.0, "height": 90.0, "length": 45.0, "unit": "cm"},
        "shipping_class": "standard",
    },
    "attributes": {"color": "red", "material": "oak"},
    "identifiers": {
        "barcode": "4006381333931",
        "manufacturer_part_number": "WC-CHAIR-RED-01",
        "country_of_origin": "DE",
    },
    "custom": {},
    "system": {"log_table": None},
    "created_at": "2026-01-15T10:30:00Z",
    "updated_at": "2026-02-20T14:00:00Z",
}


class ItemResponse(ItemBase):
    """
    Schema for item API responses.

    Extends ItemBase with database-generated fields like UUID and timestamps.
    Used for returning item data from GET, POST, PATCH endpoints.
    """

    uuid: UUID = Field(..., description="Unique item identifier")
    created_at: datetime = Field(..., description="Item creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={"example": _ITEM_EXAMPLE},
    )
