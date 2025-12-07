"""
Exception Enumerations

Defines enumerations for error codes and categories.
"""

from enum import Enum


class ErrorCategory(str, Enum):
    """High-level error categories for classification."""

    NOT_FOUND = "not_found"
    VALIDATION = "validation"
    DATABASE = "database"
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    BUSINESS_RULE = "business_rule"
    EXTERNAL_SERVICE = "external_service"
    INTERNAL = "internal"

    def is_client_error(self) -> bool:
        """Check if error is caused by client (4xx)."""
        return self in (
            ErrorCategory.NOT_FOUND,
            ErrorCategory.VALIDATION,
            ErrorCategory.AUTHENTICATION,
            ErrorCategory.AUTHORIZATION,
            ErrorCategory.BUSINESS_RULE,
        )

    def is_server_error(self) -> bool:
        """Check if error is server-side (5xx)."""
        return self in (
            ErrorCategory.DATABASE,
            ErrorCategory.EXTERNAL_SERVICE,
            ErrorCategory.INTERNAL,
        )


class ErrorCode(str, Enum):
    """Specific error codes for detailed error identification."""

    # Not Found (404)
    RESOURCE_NOT_FOUND = "resource_not_found"
    ENTITY_NOT_FOUND = "entity_not_found"

    # Validation (422)
    INVALID_INPUT = "invalid_input"
    MISSING_FIELD = "missing_field"
    INVALID_FORMAT = "invalid_format"
    CONSTRAINT_VIOLATION = "constraint_violation"
    DUPLICATE_ENTRY = "duplicate_entry"

    # Database (500/503)
    DATABASE_CONNECTION_ERROR = "database_connection_error"
    DATABASE_QUERY_ERROR = "database_query_error"
    DATABASE_INTEGRITY_ERROR = "database_integrity_error"
    DATABASE_TIMEOUT = "database_timeout"

    # Authentication (401)
    INVALID_CREDENTIALS = "invalid_credentials"
    TOKEN_EXPIRED = "token_expired"
    TOKEN_INVALID = "token_invalid"
    AUTHENTICATION_REQUIRED = "authentication_required"

    # Authorization (403)
    INSUFFICIENT_PERMISSIONS = "insufficient_permissions"
    ACCESS_DENIED = "access_denied"
    RESOURCE_FORBIDDEN = "resource_forbidden"

    # Business Rules (400)
    BUSINESS_RULE_VIOLATION = "business_rule_violation"
    INVALID_STATE = "invalid_state"
    OPERATION_NOT_ALLOWED = "operation_not_allowed"

    # External Services (502/503)
    EXTERNAL_SERVICE_ERROR = "external_service_error"
    EXTERNAL_SERVICE_TIMEOUT = "external_service_timeout"
    EXTERNAL_SERVICE_UNAVAILABLE = "external_service_unavailable"

    # Internal (500)
    INTERNAL_ERROR = "internal_error"
    CONFIGURATION_ERROR = "configuration_error"
    UNKNOWN_ERROR = "unknown_error"
