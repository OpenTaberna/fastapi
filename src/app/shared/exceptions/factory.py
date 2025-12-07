"""
Factory functions and helpers for exception handling.

Provides convenient helper functions for common exception scenarios.
"""

from typing import Any, Dict, Optional
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
from .enums import ErrorCode


# ============================================================================
# Entity Not Found Helpers
# ============================================================================


def entity_not_found(
    entity_type: str,
    entity_id: Any,
    message: Optional[str] = None,
) -> NotFoundError:
    """
    Create NotFoundError for a specific entity.

    Args:
        entity_type: Type of entity (e.g., "User", "Item", "Order")
        entity_id: ID of the entity that was not found
        message: Optional custom message

    Returns:
        NotFoundError with appropriate context

    Example:
        >>> raise entity_not_found("User", user_id=123)
    """
    default_message = f"{entity_type} with ID '{entity_id}' not found"
    return NotFoundError(
        message=message or default_message,
        error_code=ErrorCode.ENTITY_NOT_FOUND,
        context={
            "entity_type": entity_type,
            "entity_id": str(entity_id),
        },
    )


# ============================================================================
# Validation Helpers
# ============================================================================


def missing_field(field_name: str, message: Optional[str] = None) -> ValidationError:
    """
    Create ValidationError for a missing required field.

    Args:
        field_name: Name of the missing field
        message: Optional custom message

    Returns:
        ValidationError with appropriate context

    Example:
        >>> raise missing_field("email")
    """
    default_message = f"Required field '{field_name}' is missing"
    return ValidationError(
        message=message or default_message,
        error_code=ErrorCode.MISSING_FIELD,
        context={"field": field_name},
    )


def invalid_format(
    field_name: str,
    expected_format: str,
    message: Optional[str] = None,
) -> ValidationError:
    """
    Create ValidationError for invalid field format.

    Args:
        field_name: Name of the field with invalid format
        expected_format: Description of expected format
        message: Optional custom message

    Returns:
        ValidationError with appropriate context

    Example:
        >>> raise invalid_format("email", "valid email address")
    """
    default_message = (
        f"Field '{field_name}' has invalid format. Expected: {expected_format}"
    )
    return ValidationError(
        message=message or default_message,
        error_code=ErrorCode.INVALID_FORMAT,
        context={
            "field": field_name,
            "expected_format": expected_format,
        },
    )


def duplicate_entry(
    entity_type: str,
    field_name: str,
    field_value: Any,
    message: Optional[str] = None,
) -> ValidationError:
    """
    Create ValidationError for duplicate entry.

    Args:
        entity_type: Type of entity (e.g., "User", "Item")
        field_name: Field that has duplicate value
        field_value: The duplicate value
        message: Optional custom message

    Returns:
        ValidationError with appropriate context

    Example:
        >>> raise duplicate_entry("User", "email", "test@example.com")
    """
    default_message = f"{entity_type} with {field_name}='{field_value}' already exists"
    return ValidationError(
        message=message or default_message,
        error_code=ErrorCode.DUPLICATE_ENTRY,
        context={
            "entity_type": entity_type,
            "field": field_name,
            "value": str(field_value),
        },
    )


def constraint_violation(
    constraint: str,
    details: Optional[str] = None,
    message: Optional[str] = None,
) -> ValidationError:
    """Create ValidationError for constraint violation."""
    details_str = f" - {details}" if details else ""
    default_message = f"Constraint violation: {constraint}{details_str}"

    context: Dict[str, Any] = {"constraint": constraint}
    if details:
        context["details"] = details

    return ValidationError(
        message=message or default_message,
        error_code=ErrorCode.CONSTRAINT_VIOLATION,
        context=context,
    )


# ============================================================================
# Database Helpers
# ============================================================================


def database_connection_error(
    details: Optional[str] = None,
    original_exception: Optional[Exception] = None,
) -> DatabaseError:
    """Create DatabaseError for connection failures."""
    message = (
        f"Database connection failed: {details}"
        if details
        else "Database connection failed"
    )
    return DatabaseError(
        message=message,
        error_code=ErrorCode.DATABASE_CONNECTION_ERROR,
        context={"details": details} if details else None,
        original_exception=original_exception,
    )


def database_integrity_error(
    details: Optional[str] = None,
    original_exception: Optional[Exception] = None,
) -> DatabaseError:
    """Create DatabaseError for integrity constraint violations."""
    message = (
        f"Database integrity error: {details}"
        if details
        else "Database integrity error"
    )
    return DatabaseError(
        message=message,
        error_code=ErrorCode.DATABASE_INTEGRITY_ERROR,
        context={"details": details} if details else None,
        original_exception=original_exception,
    )


# ============================================================================
# Authentication Helpers
# ============================================================================


def token_expired(message: Optional[str] = None) -> AuthenticationError:
    """Create AuthenticationError for expired tokens."""
    return AuthenticationError(
        message=message or "Authentication token has expired",
        error_code=ErrorCode.TOKEN_EXPIRED,
    )


def invalid_token(message: Optional[str] = None) -> AuthenticationError:
    """Create AuthenticationError for invalid tokens."""
    return AuthenticationError(
        message=message or "Invalid authentication token",
        error_code=ErrorCode.TOKEN_INVALID,
    )


def authentication_required(message: Optional[str] = None) -> AuthenticationError:
    """Create AuthenticationError for missing authentication."""
    return AuthenticationError(
        message=message or "Authentication required",
        error_code=ErrorCode.AUTHENTICATION_REQUIRED,
    )


# ============================================================================
# Authorization Helpers
# ============================================================================


def access_denied(
    resource: Optional[str] = None,
    action: Optional[str] = None,
    message: Optional[str] = None,
) -> AuthorizationError:
    """Create AuthorizationError for access denial."""
    if not message:
        message = (
            f"Access denied: cannot {action} {resource}"
            if (resource and action)
            else "Access denied"
        )

    context = {k: v for k, v in {"resource": resource, "action": action}.items() if v}
    return AuthorizationError(
        message=message,
        error_code=ErrorCode.ACCESS_DENIED,
        context=context or None,
    )


def insufficient_permissions(
    required_role: Optional[str] = None,
    message: Optional[str] = None,
) -> AuthorizationError:
    """Create AuthorizationError for insufficient permissions."""
    default_message = (
        f"Insufficient permissions: {required_role} role required"
        if required_role
        else "Insufficient permissions"
    )
    return AuthorizationError(
        message=message or default_message,
        error_code=ErrorCode.INSUFFICIENT_PERMISSIONS,
        context={"required_role": required_role} if required_role else None,
    )


# ============================================================================
# Business Rule Helpers
# ============================================================================


def invalid_state(
    current_state: str,
    expected_state: Optional[str] = None,
    message: Optional[str] = None,
) -> BusinessRuleError:
    """
    Create BusinessRuleError for invalid state.

    Args:
        current_state: Current state
        expected_state: Expected state (optional)
        message: Optional custom message

    Returns:
        BusinessRuleError with appropriate context

    Example:
        >>> raise invalid_state("cancelled", "active")
    """
    if not message:
        message = f"Invalid state: {current_state}"
        if expected_state:
            message += f". Expected: {expected_state}"

    context: Dict[str, str] = {"current_state": current_state}
    if expected_state:
        context["expected_state"] = expected_state

    return BusinessRuleError(
        message=message,
        error_code=ErrorCode.INVALID_STATE,
        context=context,
    )


def operation_not_allowed(
    operation: str,
    reason: Optional[str] = None,
    message: Optional[str] = None,
) -> BusinessRuleError:
    """Create BusinessRuleError for disallowed operation."""
    reason_str = f" - {reason}" if reason else ""
    default_message = f"Operation not allowed: {operation}{reason_str}"

    context: Dict[str, str] = {"operation": operation}
    if reason:
        context["reason"] = reason

    return BusinessRuleError(
        message=message or default_message,
        error_code=ErrorCode.OPERATION_NOT_ALLOWED,
        context=context,
    )


# ============================================================================
# External Service Helpers
# ============================================================================


def external_service_unavailable(
    service_name: str,
    message: Optional[str] = None,
    original_exception: Optional[Exception] = None,
) -> ExternalServiceError:
    """
    Create ExternalServiceError for service unavailability.

    Args:
        service_name: Name of the external service
        message: Optional custom message
        original_exception: Original exception

    Returns:
        ExternalServiceError with appropriate context

    Example:
        >>> raise external_service_unavailable("PaymentAPI")
    """
    default_message = f"External service unavailable: {service_name}"
    return ExternalServiceError(
        message=message or default_message,
        error_code=ErrorCode.EXTERNAL_SERVICE_UNAVAILABLE,
        context={"service_name": service_name},
        original_exception=original_exception,
    )


def external_service_timeout(
    service_name: str,
    timeout_seconds: Optional[float] = None,
    message: Optional[str] = None,
) -> ExternalServiceError:
    """Create ExternalServiceError for service timeout."""
    timeout_str = f" (timeout: {timeout_seconds}s)" if timeout_seconds else ""
    default_message = f"External service timeout: {service_name}{timeout_str}"

    context = {"service_name": service_name}
    if timeout_seconds:
        context["timeout_seconds"] = timeout_seconds

    return ExternalServiceError(
        message=message or default_message,
        error_code=ErrorCode.EXTERNAL_SERVICE_TIMEOUT,
        context=context,
    )


# ============================================================================
# Internal Error Helpers
# ============================================================================


def configuration_error(
    config_key: str,
    details: Optional[str] = None,
    message: Optional[str] = None,
) -> InternalError:
    """Create InternalError for configuration issues."""
    details_str = f" - {details}" if details else ""
    default_message = f"Configuration error: {config_key}{details_str}"

    context: Dict[str, str] = {"config_key": config_key}
    if details:
        context["details"] = details

    return InternalError(
        message=message or default_message,
        error_code=ErrorCode.CONFIGURATION_ERROR,
        context=context,
    )
