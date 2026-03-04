"""
Orders Pydantic Schemas

API-level input/output validation for the orders service.
"""

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ============================================================================
# Enums
# ============================================================================


class OrderStatus(str, Enum):
    """
    Order lifecycle states.

    Valid transitions (enforced by application layer):
        DRAFT → PENDING_PAYMENT (checkout starts)
        PENDING_PAYMENT → PAID (webhook: payment_succeeded)
        PENDING_PAYMENT → CANCELLED (webhook: payment_failed / timeout)
        DRAFT → CANCELLED (customer cancels)
        PAID → READY_TO_SHIP (shipment created)
        READY_TO_SHIP → SHIPPED (handed to carrier)
    """

    DRAFT = "draft"
    PENDING_PAYMENT = "pending_payment"
    PAID = "paid"
    READY_TO_SHIP = "ready_to_ship"
    SHIPPED = "shipped"
    CANCELLED = "cancelled"


# ============================================================================
# OrderItem Schemas
# ============================================================================


class OrderItemBase(BaseModel):
    """Shared order item fields."""

    sku: str = Field(
        ..., min_length=1, max_length=100, description="SKU of the ordered item"
    )
    quantity: int = Field(..., gt=0, description="Number of units ordered")
    unit_price: int = Field(
        ..., ge=0, description="Price per unit at checkout time (in cents)"
    )


class OrderItemCreate(BaseModel):
    """
    Schema for adding a line item during order creation.

    unit_price is NOT provided by the client — it is looked up from the
    item service at checkout time and stored as an immutable snapshot.
    """

    sku: str = Field(
        ..., min_length=1, max_length=100, description="SKU of the item to order"
    )
    quantity: int = Field(..., gt=0, description="Number of units to order")


class OrderItemResponse(OrderItemBase):
    """Order item response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Internal order item UUID")
    order_id: UUID = Field(..., description="UUID of the parent order")
    created_at: datetime = Field(..., description="Record creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")


# ============================================================================
# Order Schemas
# ============================================================================


class OrderBase(BaseModel):
    """Shared order fields."""

    customer_id: UUID = Field(..., description="UUID of the customer")
    currency: str = Field(
        ...,
        min_length=3,
        max_length=3,
        description="ISO 4217 currency code (e.g. 'EUR')",
    )


class OrderCreate(BaseModel):
    """
    Schema for creating a new draft order.

    customer_id is injected from the Keycloak token — never from the
    request body — to prevent customers from creating orders for others.
    """

    items: list[OrderItemCreate] = Field(
        ...,
        min_length=1,
        description="Line items to include in the order",
    )
    currency: str = Field(
        default="EUR",
        min_length=3,
        max_length=3,
        description="ISO 4217 currency code",
    )


class OrderUpdate(BaseModel):
    """Schema for status updates. Used by admin endpoints."""

    status: OrderStatus | None = None


class OrderResponse(OrderBase):
    """Order summary response (list view)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Internal order UUID")
    status: OrderStatus = Field(..., description="Current order status")
    total_amount: int = Field(..., description="Order total in cents")
    created_at: datetime = Field(..., description="Record creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    deleted_at: datetime | None = Field(
        default=None, description="Soft delete timestamp"
    )


class OrderDetailResponse(OrderResponse):
    """Order detail response (single order view) — includes line items."""

    items: list[OrderItemResponse] = Field(
        default_factory=list,
        description="Line items of this order",
    )
