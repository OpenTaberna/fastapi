"""Programmatic OpenAPI error documentation for admin mail endpoints."""

from app.shared.responses import ErrorResponse, ValidationErrorResponse


def _error(status_code: int, error_code: str, category: str, message: str) -> dict:
    """Build an example from the same model returned by exception handlers."""
    return ErrorResponse(
        status_code=status_code,
        error_code=error_code,
        error_category=category,
        message=message,
    ).model_dump(mode="json", exclude_none=True)


def _validation(message: str, location: list[str]) -> dict:
    """Build a representative request-validation example."""
    return ValidationErrorResponse(
        message="Validation failed",
        validation_errors=[{"loc": location, "msg": message, "type": "value_error"}],
    ).model_dump(mode="json", exclude_none=True)


_ACCESS_DENIED = _error(403, "access_denied", "authorization", "Admin access required")
_NOT_FOUND = _error(404, "resource_not_found", "not_found", "Mail resource not found")
_NOT_CONFIGURED = _error(
    422,
    "invalid_input",
    "validation",
    "Mailbox server is not configured",
)
_PROVIDER_FAILURE = _error(
    502,
    "external_service_error",
    "external_service",
    "Could not connect to the mail server",
)
_INTERNAL_FAILURE = _error(
    500, "internal_error", "internal", "An unexpected error occurred"
)
_PROTECTED_FOLDER = _error(
    400,
    "business_rule_violation",
    "business_rule",
    "Protected mail folders cannot be renamed or deleted",
)

_403 = {
    "description": "A valid administrator token from an allowed admin client is required",
    "model": ErrorResponse,
    "content": {"application/json": {"example": _ACCESS_DENIED}},
}
_404 = {
    "description": "The folder, message, or attachment does not exist",
    "model": ErrorResponse,
    "content": {"application/json": {"example": _NOT_FOUND}},
}
_422_CONFIG = {
    "description": "Mailbox configuration is incomplete",
    "model": ErrorResponse,
    "content": {"application/json": {"example": _NOT_CONFIGURED}},
}
_422_REQUEST = {
    "description": "Request validation failed",
    "model": ValidationErrorResponse,
    "content": {
        "application/json": {"example": _validation("Value is invalid", ["body"])}
    },
}
_502 = {
    "description": "The configured IMAP or SMTP provider failed",
    "model": ErrorResponse,
    "content": {"application/json": {"example": _PROVIDER_FAILURE}},
}
_500 = {
    "description": "Unexpected internal server error",
    "model": ErrorResponse,
    "content": {"application/json": {"example": _INTERNAL_FAILURE}},
}
_400_FOLDER = {
    "description": "The requested operation targets a protected or reserved folder",
    "model": ErrorResponse,
    "content": {"application/json": {"example": _PROTECTED_FOLDER}},
}

STATUS_RESPONSES = {403: _403, 500: _500}
FOLDER_RESPONSES = {403: _403, 422: _422_CONFIG, 502: _502, 500: _500}
CREATE_FOLDER_RESPONSES = {
    400: _400_FOLDER,
    403: _403,
    422: _422_REQUEST,
    502: _502,
    500: _500,
}
RENAME_FOLDER_RESPONSES = {
    400: _400_FOLDER,
    403: _403,
    404: _404,
    422: _422_REQUEST,
    502: _502,
    500: _500,
}
DELETE_FOLDER_RESPONSES = {
    400: _400_FOLDER,
    403: _403,
    404: _404,
    422: _422_CONFIG,
    502: _502,
    500: _500,
}
LIST_MESSAGES_RESPONSES = {
    403: _403,
    404: _404,
    422: _422_REQUEST,
    502: _502,
    500: _500,
}
MESSAGE_RESPONSES = {403: _403, 404: _404, 422: _422_CONFIG, 502: _502, 500: _500}
ATTACHMENT_RESPONSES = MESSAGE_RESPONSES
SEND_MESSAGE_RESPONSES = {
    403: _403,
    422: _422_REQUEST,
    502: _502,
    500: _500,
}
MOVE_MESSAGE_RESPONSES = MESSAGE_RESPONSES
UPDATE_FLAGS_RESPONSES = MESSAGE_RESPONSES
DELETE_MESSAGE_RESPONSES = MESSAGE_RESPONSES
