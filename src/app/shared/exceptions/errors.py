"""
Concrete exception classes for common error scenarios.

All exceptions follow the Open/Closed Principle - they extend AppException
without modifying it, and can be easily extended for specific use cases.
"""

from typing import Any, Dict, Optional
from .base import AppException
from .enums import ErrorCategory, ErrorCode


class NotFoundError(AppException):
    """
    Exception raised when a requested resource is not found.

    Examples: Database entity not found, API resource not found, File not found
    HTTP Status Code: 404
    """

    _default_message = "Resource not found"
    _default_code = ErrorCode.RESOURCE_NOT_FOUND
    _category = ErrorCategory.NOT_FOUND

    def __init__(
        self,
        message: str = None,
        error_code: ErrorCode = None,
        context: Optional[Dict[str, Any]] = None,
        original_exception: Optional[Exception] = None,
    ):
        super().__init__(
            message=message or self._default_message,
            error_code=error_code or self._default_code,
            category=self._category,
            context=context,
            original_exception=original_exception,
            should_auto_log=True,
        )


class ValidationError(AppException):
    """
    Exception raised when input validation fails.

    Examples: Invalid field format, Missing required field, Constraint violation
    HTTP Status Code: 422 (Unprocessable Entity)
    """

    _default_message = "Validation failed"
    _default_code = ErrorCode.INVALID_INPUT
    _category = ErrorCategory.VALIDATION

    def __init__(
        self,
        message: str = None,
        error_code: ErrorCode = None,
        context: Optional[Dict[str, Any]] = None,
        original_exception: Optional[Exception] = None,
    ):
        super().__init__(
            message=message or self._default_message,
            error_code=error_code or self._default_code,
            category=self._category,
            context=context,
            original_exception=original_exception,
            should_auto_log=True,
        )


class DatabaseError(AppException):
    """
    Exception raised when database operations fail.

    Examples: Connection errors, Query errors, Integrity constraint violations
    HTTP Status Code: 500 (Internal Server Error) or 503 (Service Unavailable)
    """

    _default_message = "Database operation failed"
    _default_code = ErrorCode.DATABASE_QUERY_ERROR
    _category = ErrorCategory.DATABASE

    def __init__(
        self,
        message: str = None,
        error_code: ErrorCode = None,
        context: Optional[Dict[str, Any]] = None,
        original_exception: Optional[Exception] = None,
    ):
        super().__init__(
            message=message or self._default_message,
            error_code=error_code or self._default_code,
            category=self._category,
            context=context,
            original_exception=original_exception,
            should_auto_log=True,
        )


class AuthenticationError(AppException):
    """
    Exception raised when authentication fails.

    Examples: Invalid credentials, Expired token, Invalid token
    HTTP Status Code: 401 (Unauthorized)
    """

    _default_message = "Authentication failed"
    _default_code = ErrorCode.INVALID_CREDENTIALS
    _category = ErrorCategory.AUTHENTICATION

    def __init__(
        self,
        message: str = None,
        error_code: ErrorCode = None,
        context: Optional[Dict[str, Any]] = None,
        original_exception: Optional[Exception] = None,
    ):
        super().__init__(
            message=message or self._default_message,
            error_code=error_code or self._default_code,
            category=self._category,
            context=context,
            original_exception=original_exception,
            should_auto_log=True,
        )


class AuthorizationError(AppException):
    """
    Exception raised when authorization/permission checks fail.

    Examples: Insufficient permissions, Access denied, Role requirements not met
    HTTP Status Code: 403 (Forbidden)
    """

    _default_message = "Access denied"
    _default_code = ErrorCode.INSUFFICIENT_PERMISSIONS
    _category = ErrorCategory.AUTHORIZATION

    def __init__(
        self,
        message: str = None,
        error_code: ErrorCode = None,
        context: Optional[Dict[str, Any]] = None,
        original_exception: Optional[Exception] = None,
    ):
        super().__init__(
            message=message or self._default_message,
            error_code=error_code or self._default_code,
            category=self._category,
            context=context,
            original_exception=original_exception,
            should_auto_log=True,
        )


class BusinessRuleError(AppException):
    """
    Exception raised when business rules are violated.

    Examples: Invalid state transition, Operation not allowed, Constraint violation
    HTTP Status Code: 400 (Bad Request)
    """

    _default_message = "Business rule violation"
    _default_code = ErrorCode.BUSINESS_RULE_VIOLATION
    _category = ErrorCategory.BUSINESS_RULE

    def __init__(
        self,
        message: str = None,
        error_code: ErrorCode = None,
        context: Optional[Dict[str, Any]] = None,
        original_exception: Optional[Exception] = None,
    ):
        super().__init__(
            message=message or self._default_message,
            error_code=error_code or self._default_code,
            category=self._category,
            context=context,
            original_exception=original_exception,
            should_auto_log=True,
        )


class ExternalServiceError(AppException):
    """
    Exception raised when external service calls fail.

    Examples: Third-party API errors, Service timeout, Service unavailable
    HTTP Status Code: 502 (Bad Gateway) or 503 (Service Unavailable)
    """

    _default_message = "External service error"
    _default_code = ErrorCode.EXTERNAL_SERVICE_ERROR
    _category = ErrorCategory.EXTERNAL_SERVICE

    def __init__(
        self,
        message: str = None,
        error_code: ErrorCode = None,
        context: Optional[Dict[str, Any]] = None,
        original_exception: Optional[Exception] = None,
    ):
        super().__init__(
            message=message or self._default_message,
            error_code=error_code or self._default_code,
            category=self._category,
            context=context,
            original_exception=original_exception,
            should_auto_log=True,
        )


class InternalError(AppException):
    """
    Exception raised for internal/unexpected errors.

    Examples: Configuration errors, Unexpected system errors, Programming errors
    HTTP Status Code: 500 (Internal Server Error)
    """

    _default_message = "Internal error occurred"
    _default_code = ErrorCode.INTERNAL_ERROR
    _category = ErrorCategory.INTERNAL

    def __init__(
        self,
        message: str = None,
        error_code: ErrorCode = None,
        context: Optional[Dict[str, Any]] = None,
        original_exception: Optional[Exception] = None,
    ):
        super().__init__(
            message=message or self._default_message,
            error_code=error_code or self._default_code,
            category=self._category,
            context=context,
            original_exception=original_exception,
            should_auto_log=True,
        )
