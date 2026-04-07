"""
OpenAPI Documentation for Inventory Endpoints

All error examples are built programmatically from the actual response model
instances so they can never drift from the real API output.
"""

from app.shared.responses import ErrorResponse, ValidationErrorResponse

from ..models import InventoryItemResponse


# ---------------------------------------------------------------------------
# Helpers
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
    """Build a validation error example dict from an actual ValidationErrorResponse."""
    return ValidationErrorResponse(
        message=message,
        validation_errors=errors,
    ).model_dump(mode="json", exclude_none=True)


# ---------------------------------------------------------------------------
# Shared examples
# ---------------------------------------------------------------------------

_INVENTORY_ITEM_EXAMPLE = {
    "id": "9f8e7d6c-5b4a-3210-fedc-ba9876543210",
    "sku": "CHAIR-RED-001",
    "on_hand": 100,
    "reserved": 3,
    "created_at": "2026-01-15T10:30:00Z",
    "updated_at": "2026-02-20T14:00:00Z",
}

INVALID_UUID_EXAMPLE = _validation_err(
    message="Validation failed",
    errors=[
        {
            "loc": ["path", "inventory_id"],
            "msg": "Input should be a valid UUID",
            "type": "uuid_parsing",
        }
    ],
)

INVENTORY_NOT_FOUND_EXAMPLE = _err(
    status=404,
    code="entity_not_found",
    category="not_found",
    message="InventoryItem with ID '9f8e7d6c-5b4a-3210-fedc-ba9876543210' not found",
    details={
        "entity_type": "InventoryItem",
        "entity_id": "9f8e7d6c-5b4a-3210-fedc-ba9876543210",
    },
)

DUPLICATE_SKU_EXAMPLE = _err(
    status=422,
    code="duplicate_entry",
    category="validation",
    message="InventoryItem with sku='CHAIR-RED-001' already exists",
    details={
        "entity_type": "InventoryItem",
        "field": "sku",
        "value": "CHAIR-RED-001",
    },
)

ACCESS_DENIED_EXAMPLE = _err(
    status=403,
    code="access_denied",
    category="authorization",
    message="Access denied: admin privileges required",
    details={"reason": "missing or invalid X-Admin-Key header"},
)

CONSTRAINT_VIOLATION_EXAMPLE = _err(
    status=400,
    code="business_rule_violation",
    category="business_rule",
    message="on_hand cannot be less than current reserved quantity (3)",
    details={"field": "on_hand", "constraint": "on_hand >= reserved"},
)

DATABASE_ERROR_EXAMPLE = _err(
    status=500,
    code="database_query_error",
    category="database",
    message="Database operation failed",
    details={"error_type": "DatabaseError"},
)

INTERNAL_ERROR_EXAMPLE = _err(
    status=500,
    code="internal_error",
    category="internal",
    message="An unexpected error occurred",
    details={"error_type": "ValueError"},
)

_INVALID_ON_HAND_EXAMPLE = _validation_err(
    message="Validation failed",
    errors=[
        {
            "loc": ["body", "on_hand"],
            "msg": "Input should be greater than or equal to 0",
            "type": "greater_than_equal",
        }
    ],
)

_INVALID_PAGINATION_EXAMPLE = _validation_err(
    message="Validation failed",
    errors=[
        {
            "loc": ["query", "skip"],
            "msg": "Input should be greater than or equal to 0",
            "type": "greater_than_equal",
        }
    ],
)


# ---------------------------------------------------------------------------
# Shared response blocks
# ---------------------------------------------------------------------------

_403_BLOCK = {
    "description": "Admin privileges required",
    "model": ErrorResponse,
    "content": {"application/json": {"example": ACCESS_DENIED_EXAMPLE}},
}

_500_BLOCK = {
    "description": "Database or internal server error",
    "model": ErrorResponse,
    "content": {
        "application/json": {
            "examples": {
                "database_error": {
                    "summary": "Database error",
                    "value": DATABASE_ERROR_EXAMPLE,
                },
                "internal_error": {
                    "summary": "Unexpected error",
                    "value": INTERNAL_ERROR_EXAMPLE,
                },
            }
        }
    },
}

_404_BLOCK = {
    "description": "Inventory item not found",
    "model": ErrorResponse,
    "content": {"application/json": {"example": INVENTORY_NOT_FOUND_EXAMPLE}},
}

_422_UUID_BLOCK = {
    "description": "Invalid UUID format",
    "model": ValidationErrorResponse,
    "content": {"application/json": {"example": INVALID_UUID_EXAMPLE}},
}


# ---------------------------------------------------------------------------
# Per-endpoint response dicts
# ---------------------------------------------------------------------------

CREATE_INVENTORY_RESPONSES = {
    201: {
        "description": "Inventory item created successfully",
        "model": InventoryItemResponse,
        "content": {"application/json": {"example": _INVENTORY_ITEM_EXAMPLE}},
    },
    403: _403_BLOCK,
    422: {
        "description": "Duplicate SKU or invalid input data",
        "model": ValidationErrorResponse,
        "content": {
            "application/json": {
                "examples": {
                    "duplicate_sku": {
                        "summary": "SKU already tracked",
                        "value": DUPLICATE_SKU_EXAMPLE,
                    },
                    "invalid_input": {
                        "summary": "Invalid on_hand value",
                        "value": _INVALID_ON_HAND_EXAMPLE,
                    },
                }
            }
        },
    },
    500: _500_BLOCK,
}

GET_INVENTORY_RESPONSES = {
    200: {
        "description": "Inventory item retrieved successfully",
        "model": InventoryItemResponse,
        "content": {"application/json": {"example": _INVENTORY_ITEM_EXAMPLE}},
    },
    403: _403_BLOCK,
    404: _404_BLOCK,
    422: _422_UUID_BLOCK,
    500: _500_BLOCK,
}

GET_INVENTORY_BY_SKU_RESPONSES = {
    200: {
        "description": "Inventory item retrieved successfully",
        "model": InventoryItemResponse,
        "content": {"application/json": {"example": _INVENTORY_ITEM_EXAMPLE}},
    },
    403: _403_BLOCK,
    404: {
        "description": "SKU not tracked in inventory",
        "model": ErrorResponse,
        "content": {
            "application/json": {
                "example": _err(
                    status=404,
                    code="entity_not_found",
                    category="not_found",
                    message="InventoryItem with ID 'CHAIR-RED-001' not found",
                    details={
                        "entity_type": "InventoryItem",
                        "entity_id": "CHAIR-RED-001",
                    },
                )
            }
        },
    },
    500: _500_BLOCK,
}

LIST_INVENTORY_RESPONSES = {
    200: {
        "description": "Inventory items retrieved successfully",
        "model": list[InventoryItemResponse],
    },
    403: _403_BLOCK,
    422: {
        "description": "Invalid query parameters",
        "model": ValidationErrorResponse,
        "content": {"application/json": {"example": _INVALID_PAGINATION_EXAMPLE}},
    },
    500: _500_BLOCK,
}

UPDATE_INVENTORY_RESPONSES = {
    200: {
        "description": "Inventory item updated successfully",
        "model": InventoryItemResponse,
        "content": {"application/json": {"example": _INVENTORY_ITEM_EXAMPLE}},
    },
    400: {
        "description": "on_hand would drop below current reserved quantity",
        "model": ErrorResponse,
        "content": {"application/json": {"example": CONSTRAINT_VIOLATION_EXAMPLE}},
    },
    403: _403_BLOCK,
    404: _404_BLOCK,
    422: {
        "description": "Invalid UUID or invalid input data",
        "model": ValidationErrorResponse,
        "content": {
            "application/json": {
                "examples": {
                    "invalid_uuid": {
                        "summary": "UUID format error",
                        "value": INVALID_UUID_EXAMPLE,
                    },
                    "invalid_input": {
                        "summary": "Invalid on_hand value",
                        "value": _INVALID_ON_HAND_EXAMPLE,
                    },
                }
            }
        },
    },
    500: _500_BLOCK,
}

DELETE_INVENTORY_RESPONSES = {
    204: {"description": "Inventory item deleted successfully"},
    403: _403_BLOCK,
    404: _404_BLOCK,
    422: _422_UUID_BLOCK,
    500: _500_BLOCK,
}
