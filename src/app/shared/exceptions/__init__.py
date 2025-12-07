"""
Exception Module for OpenTaberna.

A production-ready exception handling system built following SOLID principles.

Quick Start:
    from app.shared.exceptions import (
        NotFoundError,
        ValidationError,
        entity_not_found,
        missing_field,
    )

    # Raise a simple exception
    raise NotFoundError("User not found")

    # Use helper functions for common cases
    raise entity_not_found("User", user_id=123)
    raise missing_field("email")

Architecture:
    - enums: Error codes and categories
    - interfaces: Abstract base classes (SOLID interfaces)
    - base: Base AppException class with auto-logging
    - errors: Concrete exception classes
    - factory: Helper functions for common scenarios

Features:
    - Automatic logging with appropriate log levels
    - Rich context for debugging (field names, IDs, etc.)
    - Framework-agnostic (no FastAPI dependencies)
    - Easy HTTP translation in routers
    - SOLID principles throughout
    - Fully type-safe

Error Categories:
    - NOT_FOUND (404): Resource or entity not found
    - VALIDATION (422): Input validation failures
    - DATABASE (500/503): Database operation errors
    - AUTHENTICATION (401): Authentication failures
    - AUTHORIZATION (403): Permission/access errors
    - BUSINESS_RULE (400): Business logic violations
    - EXTERNAL_SERVICE (502/503): External API errors
    - INTERNAL (500): Internal/configuration errors
"""

# Main exception classes
from .errors import (
    NotFoundError,
    ValidationError,
    DatabaseError,
    AuthenticationError,
    AuthorizationError,
    BusinessRuleError,
    ExternalServiceError,
    InternalError,
)

# Base classes and interfaces (for custom exceptions)
from .base import AppException
from .interfaces import IAppException, IExceptionHandler

# Enums
from .enums import ErrorCode, ErrorCategory

# Helper functions (most commonly used)
from .factory import (
    # Not Found helpers
    entity_not_found,
    # Validation helpers
    missing_field,
    invalid_format,
    duplicate_entry,
    constraint_violation,
    # Database helpers
    database_connection_error,
    database_integrity_error,
    # Authentication helpers
    token_expired,
    invalid_token,
    authentication_required,
    # Authorization helpers
    access_denied,
    insufficient_permissions,
    # Business rule helpers
    invalid_state,
    operation_not_allowed,
    # External service helpers
    external_service_unavailable,
    external_service_timeout,
    # Internal error helpers
    configuration_error,
)


__all__ = [
    # Main exception classes
    "AppException",
    "NotFoundError",
    "ValidationError",
    "DatabaseError",
    "AuthenticationError",
    "AuthorizationError",
    "BusinessRuleError",
    "ExternalServiceError",
    "InternalError",
    # Interfaces
    "IAppException",
    "IExceptionHandler",
    # Enums
    "ErrorCode",
    "ErrorCategory",
    # Helper functions - Not Found
    "entity_not_found",
    # Helper functions - Validation
    "missing_field",
    "invalid_format",
    "duplicate_entry",
    "constraint_violation",
    # Helper functions - Database
    "database_connection_error",
    "database_integrity_error",
    # Helper functions - Authentication
    "token_expired",
    "invalid_token",
    "authentication_required",
    # Helper functions - Authorization
    "access_denied",
    "insufficient_permissions",
    # Helper functions - Business Rules
    "invalid_state",
    "operation_not_allowed",
    # Helper functions - External Services
    "external_service_unavailable",
    "external_service_timeout",
    # Helper functions - Internal
    "configuration_error",
]
