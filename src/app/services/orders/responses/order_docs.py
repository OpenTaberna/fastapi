"""
OpenAPI Documentation for Orders Endpoints

All error examples are built programmatically from actual response model
instances so they can never drift from the real API output.
"""

from app.shared.responses import ErrorResponse, ValidationErrorResponse


# ---------------------------------------------------------------------------
# Helpers (mirrors item_docs.py)
# ---------------------------------------------------------------------------


def _err(
    status: int, code: str, category: str, message: str, details: dict | None = None
) -> dict:
    """Build an error example dict from an actual ErrorResponse instance."""
    return ErrorResponse(
        status_code=status,
        error_code=code,
        error_category=category,
        message=message,
        details=details,
    ).model_dump(mode="json", exclude_none=True)


def _validation_err(message: str, errors: list[dict]) -> dict:
    """Build a validation error example dict."""
    return ValidationErrorResponse(
        message=message,
        validation_errors=errors,
    ).model_dump(mode="json", exclude_none=True)


# ---------------------------------------------------------------------------
# Shared error examples
# ---------------------------------------------------------------------------

INVALID_UUID_EXAMPLE = _validation_err(
    message="Validation failed",
    errors=[
        {
            "loc": ["path", "id"],
            "msg": "Input should be a valid UUID",
            "type": "uuid_parsing",
        }
    ],
)

ORDER_NOT_FOUND_EXAMPLE = _err(
    status=404,
    code="entity_not_found",
    category="not_found",
    message="Order with ID '123e4567-e89b-12d3-a456-426614174000' not found",
    details={
        "entity_type": "Order",
        "entity_id": "123e4567-e89b-12d3-a456-426614174000",
    },
)

ORDER_ACCESS_DENIED_EXAMPLE = _err(
    status=403,
    code="access_denied",
    category="authorization",
    message="You do not have permission to access this order",
    details={"resource": "Order", "action": "access"},
)

ORDER_NOT_DRAFT_EXAMPLE = _err(
    status=400,
    code="invalid_state",
    category="business_rule",
    message="Order cannot transition from 'pending_payment' to 'cancelled'. "
    "Allowed transitions: ['paid', 'cancelled'].",
    details={"current_state": "pending_payment"},
)

ORDER_CHECKOUT_CONFLICT_EXAMPLE = _err(
    status=400,
    code="invalid_state",
    category="business_rule",
    message="Order cannot transition from 'paid' to 'pending_payment'. "
    "Allowed transitions: ['ready_to_ship'].",
    details={"current_state": "paid"},
)

ORDER_INSUFFICIENT_STOCK_EXAMPLE = _err(
    status=400,
    code="operation_not_allowed",
    category="business_rule",
    message="Insufficient stock for SKU 'CHAIR-RED-001': requested 3, available 1",
    details={
        "operation": "reserve_inventory",
        "reason": "Insufficient stock for SKU 'CHAIR-RED-001': requested 3, available 1",
    },
)

ITEM_NOT_FOUND_EXAMPLE = _err(
    status=404,
    code="entity_not_found",
    category="not_found",
    message="Item with ID 'CHAIR-RED-001' not found",
    details={"entity_type": "Item", "entity_id": "CHAIR-RED-001"},
)

ITEM_NO_PRICE_EXAMPLE = _err(
    status=400,
    code="operation_not_allowed",
    category="business_rule",
    message=(
        "Operation not allowed: create_order - Item 'CHAIR-RED-001' has no "
        "valid price in catalogue (expected JSONB price.amount in cents)"
    ),
    details={
        "operation": "create_order",
        "reason": (
            "Item 'CHAIR-RED-001' has no valid price in catalogue "
            "(expected JSONB price.amount in cents)"
        ),
    },
)

PSP_ERROR_EXAMPLE = _err(
    status=502,
    code="external_service_error",
    category="external_service",
    message="PSP call failed: Stripe PaymentIntent creation failed",
    details={"service_name": "Stripe"},
)

DATABASE_ERROR_EXAMPLE = _err(
    status=500,
    code="database_query_error",
    category="database",
    message="Database operation failed",
    details={"error_type": "DatabaseError"},
)

WEBHOOK_MISSING_SIG_EXAMPLE = _err(
    status=400,
    code="operation_not_allowed",
    category="business_rule",
    message="Operation not allowed: stripe_webhook - Missing Stripe-Signature header",
    details={"operation": "stripe_webhook", "reason": "Missing Stripe-Signature header"},
)

WEBHOOK_INVALID_SIG_EXAMPLE = _err(
    status=422,
    code="invalid_format",
    category="validation",
    message="Stripe webhook signature verification failed",
)

# ---------------------------------------------------------------------------
# Per-endpoint response dictionaries
# ---------------------------------------------------------------------------

_422 = {
    422: {
        "description": "Validation Error",
        "content": {"application/json": {"example": INVALID_UUID_EXAMPLE}},
    }
}
_500 = {
    500: {
        "description": "Internal Server Error",
        "content": {"application/json": {"example": DATABASE_ERROR_EXAMPLE}},
    }
}

CREATE_ORDER_RESPONSES: dict = {
    400: {
        "description": "Business rule violation: catalogue item has no valid price",
        "content": {"application/json": {"example": ITEM_NO_PRICE_EXAMPLE}},
    },
    404: {
        "description": "Requested SKU not found in the item catalogue",
        "content": {"application/json": {"example": ITEM_NOT_FOUND_EXAMPLE}},
    },
    **_422,
    **_500,
}

GET_ORDER_RESPONSES: dict = {
    403: {
        "description": "Forbidden – order belongs to another customer",
        "content": {"application/json": {"example": ORDER_ACCESS_DENIED_EXAMPLE}},
    },
    404: {
        "description": "Order not found",
        "content": {"application/json": {"example": ORDER_NOT_FOUND_EXAMPLE}},
    },
    **_422,
    **_500,
}

CANCEL_ORDER_RESPONSES: dict = {
    400: {
        "description": "Order is not in DRAFT status",
        "content": {"application/json": {"example": ORDER_NOT_DRAFT_EXAMPLE}},
    },
    403: {
        "description": "Forbidden – order belongs to another customer",
        "content": {"application/json": {"example": ORDER_ACCESS_DENIED_EXAMPLE}},
    },
    404: {
        "description": "Order not found",
        "content": {"application/json": {"example": ORDER_NOT_FOUND_EXAMPLE}},
    },
    **_422,
    **_500,
}

CHECKOUT_ORDER_RESPONSES: dict = {
    400: {
        "description": (
            "Business rule violation: order is not in DRAFT status, "
            "or insufficient stock for a line item"
        ),
        "content": {
            "application/json": {
                "examples": {
                    "invalid_status": {
                        "summary": "Order not in DRAFT status",
                        "value": ORDER_CHECKOUT_CONFLICT_EXAMPLE,
                    },
                    "insufficient_stock": {
                        "summary": "Insufficient stock",
                        "value": ORDER_INSUFFICIENT_STOCK_EXAMPLE,
                    },
                }
            }
        },
    },
    403: {
        "description": "Forbidden – order belongs to another customer",
        "content": {"application/json": {"example": ORDER_ACCESS_DENIED_EXAMPLE}},
    },
    404: {
        "description": "Order not found",
        "content": {"application/json": {"example": ORDER_NOT_FOUND_EXAMPLE}},
    },
    502: {
        "description": "Payment provider error – PSP API call failed",
        "content": {"application/json": {"example": PSP_ERROR_EXAMPLE}},
    },
    **_422,
    **_500,
}

STRIPE_WEBHOOK_RESPONSES: dict = {
    400: {
        "description": "Missing Stripe-Signature header",
        "content": {"application/json": {"example": WEBHOOK_MISSING_SIG_EXAMPLE}},
    },
    422: {
        "description": "Invalid or expired Stripe HMAC signature",
        "content": {"application/json": {"example": WEBHOOK_INVALID_SIG_EXAMPLE}},
    },
    **_500,
}
