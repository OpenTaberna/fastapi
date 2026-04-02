"""
Orders Response Documentation Package

Contains OpenAPI documentation helpers (response example dicts) for the
orders endpoints. Pydantic response schemas live in models/, not here.
"""

from .order_docs import (
    CANCEL_ORDER_RESPONSES,
    CHECKOUT_ORDER_RESPONSES,
    CREATE_ORDER_RESPONSES,
    GET_ORDER_RESPONSES,
    STRIPE_WEBHOOK_RESPONSES,
)

__all__ = [
    "CREATE_ORDER_RESPONSES",
    "GET_ORDER_RESPONSES",
    "CANCEL_ORDER_RESPONSES",
    "CHECKOUT_ORDER_RESPONSES",
    "STRIPE_WEBHOOK_RESPONSES",
]
