"""
Admin Pydantic Schemas

API-level input/output schemas for admin order management endpoints (Phase 2).

All response schemas are read-only (from_attributes=True). Input schemas are
validated strictly — reason is required for every manual status override so
there is always an audit trail in the structured application log.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.services.customers.models.customers_models import (
    AddressResponse,
    CustomerResponse,
)
from app.services.orders.models.orders_models import (
    OrderDetailResponse,
    OrderResponse,
    OrderStatus,
)
from app.services.payments.models.payments_models import PaymentResponse
from app.services.shipments.models.shipments_models import Carrier, ShipmentResponse


# ============================================================================
# Response schemas
# ============================================================================


class AdminOrderDetailResponse(OrderDetailResponse):
    """
    Extended order detail response for admin endpoints.

    Adds related entities (customer, address, payment, shipment) that are
    unnecessary for the customer-facing view but required by admin operations.
    """

    customer: CustomerResponse | None = Field(
        default=None, description="Customer who placed the order"
    )
    shipping_address: AddressResponse | None = Field(
        default=None, description="Customer's default shipping address"
    )
    payment: PaymentResponse | None = Field(
        default=None, description="Associated payment record"
    )
    shipment: ShipmentResponse | None = Field(
        default=None, description="Associated shipment record"
    )


class AdminOrderListResponse(BaseModel):
    """Paginated order list response for admin list endpoint."""

    model_config = ConfigDict(from_attributes=True)

    orders: list[OrderResponse] = Field(
        default_factory=list, description="Page of orders"
    )
    total: int = Field(..., description="Total number of matching orders")
    skip: int = Field(..., description="Pagination offset applied")
    limit: int = Field(..., description="Pagination page size applied")


# ============================================================================
# Pick-list schemas
# ============================================================================


class PickListItem(BaseModel):
    """
    Aggregated pick list entry for a single SKU across multiple PAID orders.

    Used by warehouse staff to pull all required units for a fulfilment batch
    in one pass through the warehouse.
    """

    sku: str = Field(..., description="Product SKU to pick")
    total_quantity: int = Field(
        ..., description="Total units required across all included orders"
    )
    order_count: int = Field(..., description="Number of orders that contain this SKU")


class PickListResponse(BaseModel):
    """
    Aggregated pick list covering all orders in a fulfilment batch.

    Generated over every order currently in PAID status so the admin can
    pick all goods in one warehouse run before creating individual shipments.
    """

    items: list[PickListItem] = Field(
        default_factory=list,
        description="SKU-level pick items, sorted by SKU ascending",
    )
    order_ids: list[UUID] = Field(
        default_factory=list,
        description="IDs of the orders included in this pick list",
    )
    generated_at: datetime = Field(
        ..., description="UTC timestamp when the pick list was generated"
    )


# ============================================================================
# Request (input) schemas
# ============================================================================


class AdminStatusOverrideRequest(BaseModel):
    """
    Request body for the manual order status override endpoint.

    `reason` is mandatory so that every admin-driven state change is
    accompanied by an explanation that ends up in the structured log.
    """

    status: OrderStatus = Field(..., description="Target order status")
    reason: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Plain-text reason for the override (written to audit log)",
    )


class AdminCreateShipmentRequest(BaseModel):
    """
    Request body for creating a manual shipment record.

    For manual carriers the tracking number can be provided up front.
    For automated carriers (DHL, Phase 3) it is populated later by the
    label job and left None here.
    """

    carrier: Carrier = Field(
        default=Carrier.MANUAL, description="Shipping carrier for this shipment"
    )
    tracking_number: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        description="Carrier tracking number (optional — can be added later)",
    )
