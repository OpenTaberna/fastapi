"""
OpenAPI Documentation for Customers Endpoints

All error examples are built programmatically from actual response model
instances so they can never drift from the real API output.
"""

from app.shared.responses import ErrorResponse, ValidationErrorResponse


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
    ).model_dump(mode="json")


def _validation_err(message: str, errors: list[dict]) -> dict:
    """Build a validation error example dict."""
    return ValidationErrorResponse(
        message=message,
        validation_errors=errors,
    ).model_dump(mode="json")


# ---------------------------------------------------------------------------
# Shared error examples
# ---------------------------------------------------------------------------

INVALID_UUID_EXAMPLE = _validation_err(
    message="Validation failed",
    errors=[
        {
            "loc": ["path", "address_id"],
            "msg": "Input should be a valid UUID",
            "type": "uuid_parsing",
        }
    ],
)

# Missing required X-Keycloak-User-ID header — applies to ALL endpoints.
# Produced by FastAPI's RequestValidationError handler → ValidationErrorResponse shape.
MISSING_HEADER_EXAMPLE = _validation_err(
    message="Validation failed",
    errors=[
        {
            "loc": ["header", "X-Keycloak-User-ID"],
            "msg": "Field required",
            "type": "missing",
        }
    ],
)

# Body validation error — 422 for PATCH /me and POST /me/addresses (no UUID path param).
# Produced by FastAPI's RequestValidationError handler → ValidationErrorResponse shape.
BODY_VALIDATION_EXAMPLE = _validation_err(
    message="Validation failed",
    errors=[
        {
            "loc": ["body", "email"],
            "msg": "value is not a valid email address",
            "type": "value_error.email",
        }
    ],
)

# Missing creation header — 422 for GET /me when profile does not exist yet.
# Produced by raise missing_field(...) → AppException handler → plain ErrorResponse shape
# (error_code: "missing_field", details: {"field": "..."}) — NOT ValidationErrorResponse.
MISSING_CREATION_FIELD_EXAMPLE = _err(
    status=422,
    code="missing_field",
    category="validation",
    message="Required field 'X-Customer-Email' is missing",
    details={"field": "X-Customer-Email"},
)

ADDRESS_NOT_FOUND_EXAMPLE = _err(
    status=404,
    code="entity_not_found",
    category="not_found",
    message="Address with ID '123e4567-e89b-12d3-a456-426614174000' not found",
    details={
        "entity_type": "Address",
        "entity_id": "123e4567-e89b-12d3-a456-426614174000",
    },
)

CUSTOMER_NOT_FOUND_EXAMPLE = _err(
    status=404,
    code="entity_not_found",
    category="not_found",
    message="Customer with ID 'dev-user-001' not found",
    details={
        "entity_type": "Customer",
        "entity_id": "dev-user-001",
    },
)

ADDRESS_ACCESS_DENIED_EXAMPLE = _err(
    status=403,
    code="access_denied",
    category="authorization",
    message="Address '123e4567-e89b-12d3-a456-426614174000' does not belong to this customer",
    details={"resource": "Address"},
)

DATABASE_ERROR_EXAMPLE = _err(
    status=500,
    code="database_query_error",
    category="database",
    message="Database operation failed",
    details={"error_type": "DatabaseError"},
)

# ---------------------------------------------------------------------------
# Shared response blocks
# ---------------------------------------------------------------------------

_500 = {
    500: {
        "description": "Internal Server Error",
        "content": {"application/json": {"example": DATABASE_ERROR_EXAMPLE}},
    }
}


def _422_examples(*named: tuple[str, str, dict]) -> dict:
    """
    Build a 422 response block with named examples.

    Each entry is a (key, summary, example_dict) tuple.
    """
    return {
        422: {
            "description": "Validation Error",
            "content": {
                "application/json": {
                    "examples": {
                        key: {"summary": summary, "value": value}
                        for key, summary, value in named
                    }
                }
            },
        }
    }


# ---------------------------------------------------------------------------
# GET /me
# ---------------------------------------------------------------------------

GET_PROFILE_RESPONSES: dict = {
    200: {"description": "Customer profile (auto-created on first call)"},
    **_422_examples(
        ("missing_keycloak_id", "X-Keycloak-User-ID header missing", MISSING_HEADER_EXAMPLE),
        ("missing_creation_field", "Creation headers absent for new profile", MISSING_CREATION_FIELD_EXAMPLE),
    ),
    **_500,
}

# ---------------------------------------------------------------------------
# PATCH /me
# ---------------------------------------------------------------------------

UPDATE_PROFILE_RESPONSES: dict = {
    200: {"description": "Updated customer profile"},
    404: {
        "description": "Customer profile not found — call GET /me first",
        "content": {"application/json": {"example": CUSTOMER_NOT_FOUND_EXAMPLE}},
    },
    **_422_examples(
        ("missing_keycloak_id", "X-Keycloak-User-ID header missing", MISSING_HEADER_EXAMPLE),
        ("invalid_body", "Request body validation error", BODY_VALIDATION_EXAMPLE),
    ),
    **_500,
}

# ---------------------------------------------------------------------------
# GET /me/addresses
# ---------------------------------------------------------------------------

LIST_ADDRESSES_RESPONSES: dict = {
    200: {
        "description": "List of addresses for the authenticated customer (may be empty)"
    },
    404: {
        "description": "Customer profile not found — call GET /me first",
        "content": {"application/json": {"example": CUSTOMER_NOT_FOUND_EXAMPLE}},
    },
    **_422_examples(
        ("missing_keycloak_id", "X-Keycloak-User-ID header missing", MISSING_HEADER_EXAMPLE),
    ),
    **_500,
}

# ---------------------------------------------------------------------------
# POST /me/addresses
# ---------------------------------------------------------------------------

CREATE_ADDRESS_RESPONSES: dict = {
    201: {"description": "Address created successfully"},
    404: {
        "description": "Customer profile not found — call GET /me first",
        "content": {"application/json": {"example": CUSTOMER_NOT_FOUND_EXAMPLE}},
    },
    **_422_examples(
        ("missing_keycloak_id", "X-Keycloak-User-ID header missing", MISSING_HEADER_EXAMPLE),
        ("invalid_body", "Request body validation error", BODY_VALIDATION_EXAMPLE),
    ),
    **_500,
}

# ---------------------------------------------------------------------------
# PATCH /me/addresses/{id}
# ---------------------------------------------------------------------------

UPDATE_ADDRESS_RESPONSES: dict = {
    200: {"description": "Updated address"},
    403: {
        "description": "Address belongs to a different customer",
        "content": {"application/json": {"example": ADDRESS_ACCESS_DENIED_EXAMPLE}},
    },
    404: {
        "description": "Address or customer profile not found",
        "content": {
            "application/json": {
                "examples": {
                    "address_not_found": {
                        "summary": "Address not found",
                        "value": ADDRESS_NOT_FOUND_EXAMPLE,
                    },
                    "customer_not_found": {
                        "summary": "Customer profile not found",
                        "value": CUSTOMER_NOT_FOUND_EXAMPLE,
                    },
                }
            }
        },
    },
    **_422_examples(
        ("missing_keycloak_id", "X-Keycloak-User-ID header missing", MISSING_HEADER_EXAMPLE),
        ("invalid_uuid", "address_id path parameter is not a valid UUID", INVALID_UUID_EXAMPLE),
    ),
    **_500,
}

# ---------------------------------------------------------------------------
# DELETE /me/addresses/{id}
# ---------------------------------------------------------------------------

DELETE_ADDRESS_RESPONSES: dict = {
    403: {
        "description": "Address belongs to a different customer",
        "content": {"application/json": {"example": ADDRESS_ACCESS_DENIED_EXAMPLE}},
    },
    404: {
        "description": "Address or customer profile not found",
        "content": {
            "application/json": {
                "examples": {
                    "address_not_found": {
                        "summary": "Address not found",
                        "value": ADDRESS_NOT_FOUND_EXAMPLE,
                    },
                    "customer_not_found": {
                        "summary": "Customer profile not found",
                        "value": CUSTOMER_NOT_FOUND_EXAMPLE,
                    },
                }
            }
        },
    },
    **_422_examples(
        ("missing_keycloak_id", "X-Keycloak-User-ID header missing", MISSING_HEADER_EXAMPLE),
        ("invalid_uuid", "address_id path parameter is not a valid UUID", INVALID_UUID_EXAMPLE),
    ),
    **_500,
}
