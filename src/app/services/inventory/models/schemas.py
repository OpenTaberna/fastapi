"""
Inventory Pydantic Schemas

API-level input/output validation for the inventory service.
"""

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ============================================================================
# Enums
# ============================================================================


class ReservationStatus(str, Enum):
    """Lifecycle states of a stock reservation."""

    ACTIVE = "active"
    COMMITTED = "committed"
    EXPIRED = "expired"
    RELEASED = "released"


# ============================================================================
# InventoryItem Schemas
# ============================================================================


class InventoryItemBase(BaseModel):
    """Shared inventory item fields."""

    sku: str = Field(..., min_length=1, max_length=100, description="SKU — matches items.sku")
    on_hand: int = Field(..., ge=0, description="Physical stock count in the warehouse")
    reserved: int = Field(default=0, ge=0, description="Units locked by active reservations")


class InventoryItemCreate(InventoryItemBase):
    """Schema for creating a new inventory item record."""

    pass


class InventoryItemUpdate(BaseModel):
    """Schema for partial inventory updates. All fields optional."""

    on_hand: int | None = Field(default=None, ge=0)
    reserved: int | None = Field(default=None, ge=0)


class InventoryItemResponse(InventoryItemBase):
    """Inventory item response schema returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Internal inventory item UUID")
    created_at: datetime = Field(..., description="Record creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")


# ============================================================================
# StockReservation Schemas
# ============================================================================


class StockReservationBase(BaseModel):
    """Shared stock reservation fields."""

    inventory_item_id: UUID = Field(..., description="UUID of the reserved inventory item")
    order_id: UUID = Field(..., description="UUID of the associated order")
    quantity: int = Field(..., gt=0, description="Number of units reserved")
    expires_at: datetime = Field(..., description="Expiry timestamp for this reservation")


class StockReservationCreate(StockReservationBase):
    """Schema for creating a new stock reservation. Status is always ACTIVE on create."""

    pass


class StockReservationResponse(StockReservationBase):
    """Stock reservation response schema returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Internal reservation UUID")
    status: ReservationStatus = Field(..., description="Current reservation lifecycle state")
    created_at: datetime = Field(..., description="Record creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
