"""
Payments Pydantic Schemas
"""

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ============================================================================
# Enums
# ============================================================================


class PaymentStatus(str, Enum):
    """Payment lifecycle states."""

    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REFUNDED = "refunded"


class PaymentProvider(str, Enum):
    """Supported payment service providers."""

    STRIPE = "stripe"


# ============================================================================
# Payment Schemas
# ============================================================================


class PaymentBase(BaseModel):
    """Shared payment fields."""

    order_id: UUID = Field(..., description="UUID of the associated order")
    provider: PaymentProvider = Field(..., description="PSP provider")
    provider_reference: str = Field(..., description="PSP-side transaction ID")
    amount: int = Field(..., ge=0, description="Charged amount in cents")
    currency: str = Field(..., min_length=3, max_length=3, description="ISO 4217 currency code")


class PaymentCreate(PaymentBase):
    """Schema for creating a new payment record (called internally when PSP session is created)."""

    pass


class PaymentUpdate(BaseModel):
    """Schema for updating payment status — used by the webhook handler."""

    status: PaymentStatus | None = None


class PaymentResponse(PaymentBase):
    """Payment response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Internal payment UUID")
    status: PaymentStatus = Field(..., description="Current payment status")
    created_at: datetime = Field(..., description="Record creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
