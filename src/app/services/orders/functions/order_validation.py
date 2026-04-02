"""
Order Validation Functions

Business-rule checks for the orders service.
These are pure functions (no I/O) and are fully unit-testable.
"""

from uuid import UUID

from app.shared.exceptions import access_denied, invalid_state
from app.shared.logger import get_logger
from ..models import OrderDB, OrderStatus

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Valid status transitions (application-level enforcement)
# ---------------------------------------------------------------------------

_ALLOWED_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.DRAFT: {OrderStatus.PENDING_PAYMENT, OrderStatus.CANCELLED},
    OrderStatus.PENDING_PAYMENT: {OrderStatus.PAID, OrderStatus.CANCELLED},
    OrderStatus.PAID: {OrderStatus.READY_TO_SHIP},
    OrderStatus.READY_TO_SHIP: {OrderStatus.SHIPPED},
    OrderStatus.SHIPPED: set(),
    OrderStatus.CANCELLED: set(),
}


def validate_status_transition(order: OrderDB, target_status: OrderStatus) -> None:
    """
    Assert that moving order from its current status to target_status is allowed.

    Valid transitions:
        DRAFT            → PENDING_PAYMENT | CANCELLED
        PENDING_PAYMENT  → PAID | CANCELLED
        PAID             → READY_TO_SHIP
        READY_TO_SHIP    → SHIPPED
        SHIPPED          → (terminal — no transitions)
        CANCELLED        → (terminal — no transitions)

    Args:
        order:         The current OrderDB row.
        target_status: The status we want to transition to.

    Raises:
        BusinessRuleError: If the transition is not permitted.
    """
    current = OrderStatus(order.status)
    allowed = _ALLOWED_TRANSITIONS.get(current, set())

    if target_status not in allowed:
        logger.warning(
            "Invalid order status transition attempted",
            extra={
                "order_id": str(order.id),
                "current_status": current.value,
                "target_status": target_status.value,
            },
        )
        raise invalid_state(
            current_state=current.value,
            message=(
                f"Order cannot transition from '{current.value}' "
                f"to '{target_status.value}'. "
                f"Allowed transitions: {[s.value for s in allowed] or 'none (terminal state)'}."
            ),
        )

    logger.debug(
        "Order status transition validated",
        extra={
            "order_id": str(order.id),
            "from": current.value,
            "to": target_status.value,
        },
    )


def assert_order_owned_by(order: OrderDB, customer_id: UUID) -> None:
    """
    Raise AccessDenied if the order does not belong to the given customer.

    This is the authorization check that prevents customers from accessing
    other customers' orders. Called before any read or mutation on a single order.

    Args:
        order:       The OrderDB row fetched from the database.
        customer_id: UUID of the authenticated customer (from Keycloak token).

    Raises:
        AuthorizationError: If order.customer_id != customer_id.
    """
    if order.customer_id != customer_id:
        logger.warning(
            "Unauthorized order access attempt",
            extra={
                "order_id": str(order.id),
                "order_customer_id": str(order.customer_id),
                "requesting_customer_id": str(customer_id),
            },
        )
        raise access_denied(
            resource="Order",
            action="access",
            message="You do not have permission to access this order",
        )
