"""
Order Functions

Business logic and transformation functions for the orders service.
"""

from .inventory_functions import (
    commit_reservation,
    expire_reservations,
    release_reservation,
    reserve_inventory,
)
from .order_creation import resolve_order_lines
from .order_transformations import (
    db_to_checkout_response,
    db_to_order_detail_response,
    db_to_order_response,
)
from .order_validation import assert_order_owned_by, validate_status_transition
from .payment_handlers import (
    extract_order_id_from_webhook,
    handle_payment_failed,
    handle_payment_succeeded,
)

__all__ = [
    # Inventory functions (Phase 1.2)
    "reserve_inventory",
    "release_reservation",
    "commit_reservation",
    "expire_reservations",
    # Order creation (Phase 1.1)
    "resolve_order_lines",
    # Transformations
    "db_to_order_response",
    "db_to_order_detail_response",
    "db_to_checkout_response",
    # Validation
    "validate_status_transition",
    "assert_order_owned_by",
    # Payment webhook handlers (Phase 1.5)
    "extract_order_id_from_webhook",
    "handle_payment_succeeded",
    "handle_payment_failed",
]
