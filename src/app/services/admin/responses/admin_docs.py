"""
OpenAPI Documentation for Admin Endpoints

All error examples are built programmatically from actual ErrorResponse /
ValidationErrorResponse instances so they can never drift from the real API
output — the same approach used in services/orders/responses/order_docs.py.
"""

from app.shared.responses import ErrorResponse, ValidationErrorResponse


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _err(
    status: int,
    code: str,
    category: str,
    message: str,
    details: dict | None = None,
) -> dict:
    """
    Build a serialised error example from a real ErrorResponse instance.

    Args:
        status:   HTTP status code.
        code:     Machine-readable error code string.
        category: Error category string.
        message:  Human-readable error message.
        details:  Optional extra context dict.

    Returns:
        JSON-serialisable dict matching the ErrorResponse schema.
    """
    return ErrorResponse(
        status_code=status,
        error_code=code,
        error_category=category,
        message=message,
        details=details,
    ).model_dump(mode="json", exclude_none=True)


def _validation_err(message: str, errors: list[dict]) -> dict:
    """
    Build a serialised validation error example from a real ValidationErrorResponse.

    Args:
        message: Top-level validation failure message.
        errors:  List of individual field error dicts (loc, msg, type).

    Returns:
        JSON-serialisable dict matching the ValidationErrorResponse schema.
    """
    return ValidationErrorResponse(
        message=message,
        validation_errors=errors,
    ).model_dump(mode="json", exclude_none=True)


# ---------------------------------------------------------------------------
# Shared error examples
# ---------------------------------------------------------------------------

ADMIN_FORBIDDEN_EXAMPLE = _err(
    status=403,
    code="access_denied",
    category="authorization",
    message="Admin access required. Provide X-Admin-Key header (dev) or valid admin JWT (production).",
    details={"resource": "admin", "action": "access"},
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

INVALID_UUID_EXAMPLE = _validation_err(
    message="Validation failed",
    errors=[
        {
            "loc": ["path", "order_id"],
            "msg": "Input should be a valid UUID",
            "type": "uuid_parsing",
        }
    ],
)

INVALID_STATUS_QUERY_EXAMPLE = _validation_err(
    message="Validation failed",
    errors=[
        {
            "loc": ["query", "status"],
            "msg": "Input should be 'draft', 'pending_payment', 'paid', 'ready_to_ship', 'shipped' or 'cancelled'",
            "type": "enum",
        }
    ],
)

ORDER_INVALID_TRANSITION_EXAMPLE = _err(
    status=400,
    code="invalid_state",
    category="business_rule",
    message="Order cannot transition from 'draft' to 'ready_to_ship'. "
    "Allowed transitions: ['pending_payment', 'cancelled'].",
    details={"current_state": "draft"},
)

DUPLICATE_SHIPMENT_EXAMPLE = _err(
    status=400,
    code="business_rule_violation",
    category="business_rule",
    message="A shipment already exists for this order.",
    details={
        "order_id": "123e4567-e89b-12d3-a456-426614174000",
        "shipment_id": "987fcdeb-51a2-43f7-8765-012345678901",
    },
)

SHIP_INVALID_STATE_EXAMPLE = _err(
    status=400,
    code="invalid_state",
    category="business_rule",
    message="Order cannot transition from 'paid' to 'shipped'. "
    "Allowed transitions: ['ready_to_ship'].",
    details={"current_state": "paid"},
)

STATUS_OVERRIDE_VALIDATION_EXAMPLE = _validation_err(
    message="Validation failed",
    errors=[
        {
            "loc": ["body", "reason"],
            "msg": "Field required",
            "type": "missing",
        }
    ],
)

DATABASE_ERROR_EXAMPLE = _err(
    status=500,
    code="database_query_error",
    category="database",
    message="Database operation failed",
    details={"error_type": "DatabaseError"},
)


# ---------------------------------------------------------------------------
# Reusable response blocks
# ---------------------------------------------------------------------------

_403 = {
    403: {
        "description": "Forbidden — admin authentication required",
        "content": {"application/json": {"example": ADMIN_FORBIDDEN_EXAMPLE}},
    }
}
_404 = {
    404: {
        "description": "Order not found or soft-deleted",
        "content": {"application/json": {"example": ORDER_NOT_FOUND_EXAMPLE}},
    }
}
_422_uuid = {
    422: {
        "description": "Validation Error — malformed UUID path parameter",
        "content": {"application/json": {"example": INVALID_UUID_EXAMPLE}},
    }
}
_500 = {
    500: {
        "description": "Internal Server Error",
        "content": {"application/json": {"example": DATABASE_ERROR_EXAMPLE}},
    }
}


# ---------------------------------------------------------------------------
# Per-endpoint response dictionaries
# ---------------------------------------------------------------------------

LIST_ORDERS_RESPONSES: dict = {
    403: _403[403],
    422: {
        "description": "Validation Error — invalid `status` query parameter",
        "content": {"application/json": {"example": INVALID_STATUS_QUERY_EXAMPLE}},
    },
    **_500,
}

PICK_LIST_RESPONSES: dict = {
    **_403,
    **_500,
}

GET_ORDER_DETAIL_RESPONSES: dict = {
    **_403,
    **_404,
    **_422_uuid,
    **_500,
}

STATUS_OVERRIDE_RESPONSES: dict = {
    **_403,
    **_404,
    422: {
        "description": "Validation Error — missing `reason` or invalid `status` value",
        "content": {
            "application/json": {"example": STATUS_OVERRIDE_VALIDATION_EXAMPLE}
        },
    },
    **_500,
}

PACKING_SLIP_RESPONSES: dict = {
    **_403,
    **_404,
    **_422_uuid,
    **_500,
}

CREATE_SHIPMENT_RESPONSES: dict = {
    400: {
        "description": (
            "Business rule violation — order is not in PAID status, "
            "or a shipment already exists for this order"
        ),
        "content": {
            "application/json": {
                "examples": {
                    "invalid_transition": {
                        "summary": "Order is not in PAID status",
                        "value": ORDER_INVALID_TRANSITION_EXAMPLE,
                    },
                    "duplicate_shipment": {
                        "summary": "Shipment already exists",
                        "value": DUPLICATE_SHIPMENT_EXAMPLE,
                    },
                }
            }
        },
    },
    **_403,
    **_404,
    **_422_uuid,
    **_500,
}

SHIP_ORDER_RESPONSES: dict = {
    400: {
        "description": "Business rule violation — order is not in READY_TO_SHIP status",
        "content": {"application/json": {"example": SHIP_INVALID_STATE_EXAMPLE}},
    },
    **_403,
    **_404,
    **_422_uuid,
    **_500,
}
