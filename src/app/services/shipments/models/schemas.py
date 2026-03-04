"""
Shipments Pydantic Schemas
"""

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ============================================================================
# Enums
# ============================================================================


class Carrier(str, Enum):
    """Supported shipping carriers."""

    MANUAL = "manual"
    DHL = "dhl"


class LabelFormat(str, Enum):
    """Supported shipping label formats."""

    PDF = "pdf"
    ZPL = "zpl"


class ShipmentStatus(str, Enum):
    """
    Shipment lifecycle states.

        PENDING       → shipment record created, no label yet
        LABEL_CREATED → carrier label generated, ready for pick & pack
        HANDED_OVER   → physically handed to carrier / pickup scan confirmed
    """

    PENDING = "pending"
    LABEL_CREATED = "label_created"
    HANDED_OVER = "handed_over"


# ============================================================================
# Shipment Schemas
# ============================================================================


class ShipmentBase(BaseModel):
    """Shared shipment fields."""

    order_id: UUID = Field(..., description="UUID of the associated order")
    carrier: Carrier = Field(..., description="Shipping carrier")


class ShipmentCreate(ShipmentBase):
    """
    Schema for creating a new shipment record.

    tracking_number may be provided immediately for manual carriers.
    For automated carriers (DHL), it is populated later by the label job.
    """

    tracking_number: str | None = Field(default=None, description="Carrier tracking number")
    label_url: str | None = Field(default=None, description="Label file URL/path in storage")
    label_format: LabelFormat | None = Field(default=None, description="Label file format")


class ShipmentUpdate(BaseModel):
    """Schema for updating a shipment record (e.g. after label creation)."""

    tracking_number: str | None = None
    label_url: str | None = None
    label_format: LabelFormat | None = None
    status: ShipmentStatus | None = None


class ShipmentResponse(ShipmentBase):
    """Shipment response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Internal shipment UUID")
    tracking_number: str | None = Field(default=None, description="Carrier tracking number")
    label_url: str | None = Field(default=None, description="Label file URL/path")
    label_format: LabelFormat | None = Field(default=None, description="Label file format")
    status: ShipmentStatus = Field(..., description="Current shipment status")
    created_at: datetime = Field(..., description="Record creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
