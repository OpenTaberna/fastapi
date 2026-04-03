"""
Order Transformations

Functions for converting between database models and Pydantic response models.
"""

from ..models import (
    CheckoutResponse,
    OrderDB,
    OrderItemDB,
    OrderResponse,
    OrderDetailResponse,
    OrderItemResponse,
)


def db_to_order_response(order: OrderDB) -> OrderResponse:
    """
    Convert an OrderDB instance to an OrderResponse schema.

    Uses Pydantic's model_validate (from_attributes=True) so all field
    coercions (str→OrderStatus, etc.) are handled automatically.

    Args:
        order: SQLAlchemy OrderDB instance

    Returns:
        OrderResponse with all top-level fields
    """
    return OrderResponse.model_validate(order)


def db_to_order_detail_response(
    order: OrderDB,
    items: list[OrderItemDB],
) -> OrderDetailResponse:
    """
    Convert an OrderDB + its OrderItemDB rows into an OrderDetailResponse.

    Args:
        order: SQLAlchemy OrderDB instance
        items: List of OrderItemDB instances belonging to this order

    Returns:
        OrderDetailResponse including the nested line-item list
    """
    order_dict = {
        "id": order.id,
        "customer_id": order.customer_id,
        "status": order.status,
        "total_amount": order.total_amount,
        "currency": order.currency,
        "created_at": order.created_at,
        "updated_at": order.updated_at,
        "deleted_at": order.deleted_at,
        "items": [OrderItemResponse.model_validate(item) for item in items],
    }
    return OrderDetailResponse.model_validate(order_dict)


def db_to_checkout_response(
    order: OrderDB,
    items: list[OrderItemDB],
    client_secret: str,
) -> CheckoutResponse:
    """
    Convert an OrderDB + its OrderItemDB rows into a CheckoutResponse.

    Composes db_to_order_detail_response and extends the result with the PSP
    client_secret token returned to the frontend after a successful PaymentIntent
    creation.

    Args:
        order:         SQLAlchemy OrderDB instance (status=PENDING_PAYMENT).
        items:         List of OrderItemDB instances belonging to this order.
        client_secret: PSP client secret (e.g. Stripe PaymentIntent client_secret).

    Returns:
        CheckoutResponse with nested line items and the client_secret.
    """
    detail = db_to_order_detail_response(order, items)
    return CheckoutResponse(**detail.model_dump(), client_secret=client_secret)
