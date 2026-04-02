"""
OpenAPI Documentation for Item Store Endpoints

All error examples are built programmatically from the actual response model
instances so they can never drift from the real API output.
"""

from app.shared.responses import (
    ErrorResponse,
    PaginatedResponse,
    ValidationErrorResponse,
)
from . import ItemResponse
from .items_response_models import _ITEM_EXAMPLE


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
    """Build a validation error example dict from an actual ValidationErrorResponse instance."""
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
            "loc": ["path", "item_uuid"],
            "msg": "Input should be a valid UUID",
            "type": "uuid_parsing",
        }
    ],
)

ITEM_NOT_FOUND_EXAMPLE = _err(
    status=404,
    code="entity_not_found",
    category="not_found",
    message="Item with ID '123e4567-e89b-12d3-a456-426614174000' not found",
    details={
        "entity_type": "Item",
        "entity_id": "123e4567-e89b-12d3-a456-426614174000",
    },
)

DUPLICATE_SKU_EXAMPLE = _err(
    status=422,
    code="duplicate_entry",
    category="validation",
    message="Item with sku='CHAIR-001' already exists",
    details={"entity_type": "Item", "field": "sku", "value": "CHAIR-001"},
)

DUPLICATE_SLUG_EXAMPLE = _err(
    status=422,
    code="duplicate_entry",
    category="validation",
    message="Item with slug='red-chair' already exists",
    details={"entity_type": "Item", "field": "slug", "value": "red-chair"},
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

_INVALID_BODY_EXAMPLE = _validation_err(
    message="Validation failed",
    errors=[
        {
            "loc": ["body", "price", "amount"],
            "msg": "Input should be greater than or equal to 0",
            "type": "greater_than_equal",
        }
    ],
)

_INVALID_PAGINATION_SKIP = _validation_err(
    message="Validation failed",
    errors=[
        {
            "loc": ["query", "skip"],
            "msg": "Input should be greater than or equal to 0",
            "type": "greater_than_equal",
        }
    ],
)

_INVALID_PAGINATION_LIMIT = _validation_err(
    message="Validation failed",
    errors=[
        {
            "loc": ["query", "limit"],
            "msg": "Input should be less than or equal to 100",
            "type": "less_than_equal",
        }
    ],
)

_INVALID_STATUS_PARAM = _validation_err(
    message="Validation failed",
    errors=[
        {
            "loc": ["query", "status"],
            "msg": "Input should be 'draft', 'active' or 'archived'",
            "type": "enum",
        }
    ],
)


# ---------------------------------------------------------------------------
# Shared response blocks (reused across endpoints)
# ---------------------------------------------------------------------------

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
    "description": "Item not found",
    "model": ErrorResponse,
    "content": {"application/json": {"example": ITEM_NOT_FOUND_EXAMPLE}},
}

_422_UUID_BLOCK = {
    "description": "Invalid UUID format",
    "model": ValidationErrorResponse,
    "content": {"application/json": {"example": INVALID_UUID_EXAMPLE}},
}


# ---------------------------------------------------------------------------
# Per-endpoint response dicts
# ---------------------------------------------------------------------------

CREATE_ITEM_RESPONSES = {
    201: {
        "description": "Item created successfully",
        "model": ItemResponse,
        "content": {"application/json": {"example": _ITEM_EXAMPLE}},
    },
    422: {
        "description": "Duplicate SKU/slug or invalid input data",
        "model": ValidationErrorResponse,
        "content": {
            "application/json": {
                "examples": {
                    "duplicate_sku": {
                        "summary": "Duplicate SKU",
                        "value": DUPLICATE_SKU_EXAMPLE,
                    },
                    "duplicate_slug": {
                        "summary": "Duplicate slug",
                        "value": DUPLICATE_SLUG_EXAMPLE,
                    },
                    "invalid_input": {
                        "summary": "Invalid input data",
                        "value": _INVALID_BODY_EXAMPLE,
                    },
                }
            }
        },
    },
    500: _500_BLOCK,
}

GET_ITEM_RESPONSES = {
    200: {
        "description": "Item retrieved successfully",
        "model": ItemResponse,
        "content": {"application/json": {"example": _ITEM_EXAMPLE}},
    },
    404: _404_BLOCK,
    422: _422_UUID_BLOCK,
    500: _500_BLOCK,
}

LIST_ITEMS_RESPONSES = {
    200: {
        "description": "Items retrieved successfully",
        "model": PaginatedResponse[ItemResponse],
    },
    422: {
        "description": "Invalid query parameters",
        "model": ValidationErrorResponse,
        "content": {
            "application/json": {
                "examples": {
                    "invalid_skip": {
                        "summary": "Negative skip value",
                        "value": _INVALID_PAGINATION_SKIP,
                    },
                    "invalid_limit": {
                        "summary": "Limit out of range",
                        "value": _INVALID_PAGINATION_LIMIT,
                    },
                    "invalid_status": {
                        "summary": "Invalid status value",
                        "value": _INVALID_STATUS_PARAM,
                    },
                }
            }
        },
    },
    500: _500_BLOCK,
}

GET_ITEM_BY_SKU_RESPONSES = {
    200: {
        "description": "Item retrieved successfully",
        "model": ItemResponse,
        "content": {"application/json": {"example": _ITEM_EXAMPLE}},
    },
    404: {
        "description": "Item not found",
        "model": ErrorResponse,
        "content": {
            "application/json": {
                "example": _err(
                    status=404,
                    code="entity_not_found",
                    category="not_found",
                    message="Item with ID 'CHAIR-RED-001' not found",
                    details={"entity_type": "Item", "entity_id": "CHAIR-RED-001"},
                )
            }
        },
    },
    500: _500_BLOCK,
}

UPDATE_ITEM_RESPONSES = {
    200: {
        "description": "Item updated successfully",
        "model": ItemResponse,
        "content": {"application/json": {"example": _ITEM_EXAMPLE}},
    },
    404: _404_BLOCK,
    422: {
        "description": "Duplicate SKU/slug, invalid UUID, or invalid input data",
        "model": ValidationErrorResponse,
        "content": {
            "application/json": {
                "examples": {
                    "duplicate_sku": {
                        "summary": "SKU conflicts with another item",
                        "value": DUPLICATE_SKU_EXAMPLE,
                    },
                    "duplicate_slug": {
                        "summary": "Slug conflicts with another item",
                        "value": DUPLICATE_SLUG_EXAMPLE,
                    },
                    "invalid_uuid": {
                        "summary": "Invalid UUID format",
                        "value": INVALID_UUID_EXAMPLE,
                    },
                    "invalid_input": {
                        "summary": "Invalid field values",
                        "value": _INVALID_BODY_EXAMPLE,
                    },
                }
            }
        },
    },
    500: _500_BLOCK,
}

DELETE_ITEM_RESPONSES = {
    204: {"description": "Item deleted successfully"},
    404: _404_BLOCK,
    422: _422_UUID_BLOCK,
    500: _500_BLOCK,
}
