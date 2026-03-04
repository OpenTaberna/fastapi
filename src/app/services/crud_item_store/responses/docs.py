"""
OpenAPI Documentation for Item Store Endpoints

Contains response schemas, examples, and documentation for all item endpoints.
Separates API documentation from business logic to keep routers clean.
"""

from app.shared.responses import (
    ErrorResponse,
    PaginatedResponse,
    ValidationErrorResponse,
)
from ..responses import ItemResponse


# ============================================================================
# Common Error Examples
# ============================================================================

INVALID_UUID_EXAMPLE = {
    "success": False,
    "message": "Validation failed",
    "status_code": 422,
    "error_code": "invalid_input",
    "error_category": "validation",
    "details": {
        "errors": [
            {
                "loc": ["path", "item_uuid"],
                "msg": "Input should be a valid UUID",
                "type": "uuid_parsing",
            }
        ]
    },
}

ITEM_NOT_FOUND_EXAMPLE = {
    "success": False,
    "message": "Item with ID '123e4567-e89b-12d3-a456-426614174000' not found",
    "status_code": 404,
    "error_code": "entity_not_found",
    "error_category": "not_found",
    "details": {
        "entity_type": "Item",
        "entity_id": "123e4567-e89b-12d3-a456-426614174000",
    },
}

DUPLICATE_SKU_EXAMPLE = {
    "success": False,
    "message": "Item with sku='CHAIR-001' already exists",
    "status_code": 422,
    "error_code": "duplicate_entry",
    "error_category": "validation",
    "details": {"entity_type": "Item", "field": "sku", "value": "CHAIR-001"},
}

DUPLICATE_SLUG_EXAMPLE = {
    "success": False,
    "message": "Item with slug='red-chair' already exists",
    "status_code": 422,
    "error_code": "duplicate_entry",
    "error_category": "validation",
    "details": {"entity_type": "Item", "field": "slug", "value": "red-chair"},
}

DATABASE_ERROR_EXAMPLE = {
    "success": False,
    "message": "Database operation failed",
    "status_code": 500,
    "error_code": "database_query_error",
    "error_category": "database",
    "details": {"error_type": "DatabaseError"},
}

INTERNAL_ERROR_EXAMPLE = {
    "success": False,
    "message": "An unexpected error occurred",
    "status_code": 500,
    "error_code": "internal_error",
    "error_category": "internal",
    "details": {"error_type": "ValueError"},
}


# ============================================================================
# Create Item Documentation
# ============================================================================

CREATE_ITEM_RESPONSES = {
    201: {
        "description": "Item created successfully",
        "model": ItemResponse,
    },
    422: {
        "description": "Validation error - duplicate SKU/slug or invalid input data",
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
                        "value": {
                            "success": False,
                            "message": "Validation failed",
                            "status_code": 422,
                            "error_code": "invalid_input",
                            "error_category": "validation",
                            "details": {
                                "errors": [
                                    {
                                        "loc": ["body", "price", "amount"],
                                        "msg": "Input should be greater than or equal to 0",
                                        "type": "greater_than_equal",
                                    }
                                ]
                            },
                        },
                    },
                }
            }
        },
    },
    500: {
        "description": "Internal server error - database or unexpected error",
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
    },
}


# ============================================================================
# Get Item by UUID Documentation
# ============================================================================

GET_ITEM_RESPONSES = {
    200: {
        "description": "Item retrieved successfully",
        "model": ItemResponse,
    },
    404: {
        "description": "Item not found",
        "model": ErrorResponse,
        "content": {"application/json": {"example": ITEM_NOT_FOUND_EXAMPLE}},
    },
    422: {
        "description": "Invalid UUID format",
        "model": ValidationErrorResponse,
        "content": {"application/json": {"example": INVALID_UUID_EXAMPLE}},
    },
    500: {
        "description": "Internal server error - database or unexpected error",
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
    },
}


# ============================================================================
# List Items Documentation
# ============================================================================

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
                        "value": {
                            "success": False,
                            "message": "Validation failed",
                            "status_code": 422,
                            "error_code": "invalid_input",
                            "error_category": "validation",
                            "details": {
                                "errors": [
                                    {
                                        "loc": ["query", "skip"],
                                        "msg": "Input should be greater than or equal to 0",
                                        "type": "greater_than_equal",
                                    }
                                ]
                            },
                        },
                    },
                    "invalid_limit": {
                        "summary": "Limit out of range",
                        "value": {
                            "success": False,
                            "message": "Validation failed",
                            "status_code": 422,
                            "error_code": "invalid_input",
                            "error_category": "validation",
                            "details": {
                                "errors": [
                                    {
                                        "loc": ["query", "limit"],
                                        "msg": "Input should be less than or equal to 100",
                                        "type": "less_than_equal",
                                    }
                                ]
                            },
                        },
                    },
                    "invalid_status": {
                        "summary": "Invalid status value",
                        "value": {
                            "success": False,
                            "message": "Validation failed",
                            "status_code": 422,
                            "error_code": "invalid_input",
                            "error_category": "validation",
                            "details": {
                                "errors": [
                                    {
                                        "loc": ["query", "status"],
                                        "msg": "Input should be 'draft', 'active' or 'archived'",
                                        "type": "enum",
                                    }
                                ]
                            },
                        },
                    },
                }
            }
        },
    },
    500: {
        "description": "Internal server error - database or unexpected error",
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
    },
}


# ============================================================================
# Get Item by SKU Documentation
# ============================================================================

GET_ITEM_BY_SKU_RESPONSES = {
    200: {
        "description": "Item retrieved successfully",
        "model": ItemResponse,
    },
    404: {
        "description": "Item not found",
        "model": ErrorResponse,
        "content": {
            "application/json": {
                "example": {
                    "success": False,
                    "message": "Item with ID 'CHAIR-001' not found",
                    "status_code": 404,
                    "error_code": "entity_not_found",
                    "error_category": "not_found",
                    "details": {"entity_type": "Item", "entity_id": "CHAIR-001"},
                }
            }
        },
    },
    500: {
        "description": "Internal server error - database or unexpected error",
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
    },
}


# ============================================================================
# Update Item Documentation
# ============================================================================

UPDATE_ITEM_RESPONSES = {
    200: {
        "description": "Item updated successfully",
        "model": ItemResponse,
    },
    404: {
        "description": "Item not found",
        "model": ErrorResponse,
        "content": {"application/json": {"example": ITEM_NOT_FOUND_EXAMPLE}},
    },
    422: {
        "description": "Validation error - duplicate SKU/slug, invalid UUID, or invalid input data",
        "model": ValidationErrorResponse,
        "content": {
            "application/json": {
                "examples": {
                    "duplicate_sku": {
                        "summary": "SKU conflicts with another item",
                        "value": {
                            "success": False,
                            "message": "Item with sku='CHAIR-002' already exists",
                            "status_code": 422,
                            "error_code": "duplicate_entry",
                            "error_category": "validation",
                            "details": {
                                "entity_type": "Item",
                                "field": "sku",
                                "value": "CHAIR-002",
                            },
                        },
                    },
                    "duplicate_slug": {
                        "summary": "Slug conflicts with another item",
                        "value": {
                            "success": False,
                            "message": "Item with slug='blue-chair' already exists",
                            "status_code": 422,
                            "error_code": "duplicate_entry",
                            "error_category": "validation",
                            "details": {
                                "entity_type": "Item",
                                "field": "slug",
                                "value": "blue-chair",
                            },
                        },
                    },
                    "invalid_uuid": {
                        "summary": "Invalid UUID format",
                        "value": INVALID_UUID_EXAMPLE,
                    },
                    "invalid_input": {
                        "summary": "Invalid field values",
                        "value": {
                            "success": False,
                            "message": "Validation failed",
                            "status_code": 422,
                            "error_code": "invalid_input",
                            "error_category": "validation",
                            "details": {
                                "errors": [
                                    {
                                        "loc": ["body", "status"],
                                        "msg": "Input should be 'draft', 'active' or 'archived'",
                                        "type": "enum",
                                    }
                                ]
                            },
                        },
                    },
                }
            }
        },
    },
    500: {
        "description": "Internal server error - database or unexpected error",
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
    },
}


# ============================================================================
# Delete Item Documentation
# ============================================================================

DELETE_ITEM_RESPONSES = {
    204: {
        "description": "Item deleted successfully",
    },
    404: {
        "description": "Item not found",
        "model": ErrorResponse,
        "content": {"application/json": {"example": ITEM_NOT_FOUND_EXAMPLE}},
    },
    422: {
        "description": "Invalid UUID format",
        "model": ValidationErrorResponse,
        "content": {"application/json": {"example": INVALID_UUID_EXAMPLE}},
    },
    500: {
        "description": "Internal server error - database or unexpected error",
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
    },
}
