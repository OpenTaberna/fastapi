"""
Admin Transformations

Functions for assembling AdminOrderDetailResponse from the set of DB model
instances returned by the admin repository layer.

Each function does exactly one conversion and nothing else — no I/O, no
side-effects, fully unit-testable.
"""

from app.services.customers.models.customers_db_models import AddressDB, CustomerDB
from app.services.customers.models.customers_models import (
    AddressResponse,
    CustomerResponse,
)
from app.services.orders.models.orders_db_models import OrderDB, OrderItemDB
from app.services.orders.models.orders_models import OrderItemResponse, OrderResponse
from app.services.payments.models.payments_db_models import PaymentDB
from app.services.payments.models.payments_models import PaymentResponse
from app.services.shipments.models.shipments_db_models import ShipmentDB
from app.services.shipments.models.shipments_models import ShipmentResponse
from app.shared.logger import get_logger

from ..models.admin_models import AdminOrderDetailResponse

logger = get_logger(__name__)


def db_to_order_response(order: OrderDB) -> OrderResponse:
    """
    Convert an OrderDB row into an OrderResponse (list-view schema).

    Args:
        order: SQLAlchemy OrderDB instance.

    Returns:
        OrderResponse with all top-level order fields.
    """
    logger.debug(
        "Converting OrderDB to OrderResponse", extra={"order_id": str(order.id)}
    )
    return OrderResponse.model_validate(order)


def db_to_admin_order_detail_response(
    order: OrderDB,
    items: list[OrderItemDB],
    customer: CustomerDB | None,
    shipping_address: AddressDB | None,
    payment: PaymentDB | None,
    shipment: ShipmentDB | None,
) -> AdminOrderDetailResponse:
    """
    Assemble an AdminOrderDetailResponse from individually-fetched DB models.

    Each argument comes from a separate repository call. None is a valid value
    for optional related entities (e.g. an order that has no shipment yet).

    Args:
        order:            The OrderDB row being returned.
        items:            All OrderItemDB rows belonging to this order.
        customer:         CustomerDB row for the order's customer, or None.
        shipping_address: The customer's default AddressDB, or None.
        payment:          The PaymentDB row linked to this order, or None.
        shipment:         The ShipmentDB row linked to this order, or None.

    Returns:
        AdminOrderDetailResponse with all nested entities populated.
    """
    logger.debug(
        "Assembling AdminOrderDetailResponse",
        extra={
            "order_id": str(order.id),
            "has_customer": customer is not None,
            "has_payment": payment is not None,
            "has_shipment": shipment is not None,
        },
    )
    order_data = {
        "id": order.id,
        "customer_id": order.customer_id,
        "status": order.status,
        "total_amount": order.total_amount,
        "currency": order.currency,
        "created_at": order.created_at,
        "updated_at": order.updated_at,
        "deleted_at": order.deleted_at,
        "items": [OrderItemResponse.model_validate(item) for item in items],
        "customer": CustomerResponse.model_validate(customer) if customer else None,
        "shipping_address": AddressResponse.model_validate(shipping_address)
        if shipping_address
        else None,
        "payment": PaymentResponse.model_validate(payment) if payment else None,
        "shipment": ShipmentResponse.model_validate(shipment) if shipment else None,
    }
    return AdminOrderDetailResponse.model_validate(order_data)
