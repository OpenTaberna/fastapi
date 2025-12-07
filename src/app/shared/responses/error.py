"""
Error Response Models

Response models for error cases, integrated with AppException system.
Maps exceptions to HTTP status codes and standardized error formats.
"""

from typing import TYPE_CHECKING, Optional, Dict, Any
from pydantic import Field, ConfigDict
from .base import BaseResponse

if TYPE_CHECKING:
    from app.shared.exceptions import AppException

# Optional logger import - gracefully handle if not available
try:
    from app.shared.logger import get_logger

    _logger = get_logger(__name__)
except ImportError:
    _logger = None


class ErrorResponse(BaseResponse):
    """
    Standardized error response integrated with AppException.

    This response automatically maps exception details to HTTP-compliant
    error responses with proper status codes and structured error information.

    Examples:
        >>> ErrorResponse(
        ...     success=False,
        ...     message="User not found",
        ...     status_code=404,
        ...     error_code="USER_NOT_FOUND",
        ...     error_category="NOT_FOUND"
        ... )
    """

    success: bool = Field(default=False, description="Always False for error responses")

    status_code: int = Field(
        ...,
        description="HTTP status code (4xx for client errors, 5xx for server errors)",
        ge=400,
        le=599,
    )

    error_code: str = Field(
        ..., description="Machine-readable error code from ErrorCode enum"
    )

    error_category: str = Field(
        ..., description="Error category from ErrorCategory enum"
    )

    details: Optional[Dict[str, Any]] = Field(
        None, description="Additional error context and details"
    )

    @classmethod
    def from_exception(
        cls,
        exception: "AppException",
        request_id: Optional[str] = None,
    ) -> "ErrorResponse":
        """
        Create ErrorResponse from AppException.

        Automatically maps exception attributes to response fields,
        including HTTP status code mapping from error category.

        Args:
            exception: AppException instance to convert
            request_id: Optional request identifier for tracing

        Returns:
            ErrorResponse with all fields populated from exception

        Example:
            >>> try:
            ...     raise NotFoundError("User not found", entity_type="User")
            ... except AppException as e:
            ...     response = ErrorResponse.from_exception(e)
        """
        # Map error category to HTTP status code
        status_code_map = {
            "not_found": 404,
            "validation": 422,
            "authentication": 401,
            "authorization": 403,
            "business_rule": 400,
            "database": 500,
            "external_service": 502,
            "internal": 500,
        }

        status_code = status_code_map.get(exception.category.value, 500)

        # Optional debug logging for response creation
        if _logger:
            _logger.debug(
                f"Creating ErrorResponse from {exception.__class__.__name__}",
                extra={
                    "error_code": exception.error_code.value,
                    "status_code": status_code,
                    "request_id": request_id,
                },
            )

        # Access exception attributes directly
        return cls(
            success=False,
            message=exception.message,
            status_code=status_code,
            error_code=exception.error_code.value,
            error_category=exception.category.value,
            details=exception.context,
            request_id=request_id,
            metadata=None,
        )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": False,
                "message": "User not found",
                "status_code": 404,
                "error_code": "USER_NOT_FOUND",
                "error_category": "NOT_FOUND",
                "details": {"entity_type": "User", "entity_id": "123"},
                "timestamp": "2025-12-07T12:00:00Z",
                "request_id": "req-abc-123",
            }
        }
    )


class ValidationErrorResponse(ErrorResponse):
    """
    Specialized error response for validation errors.

    Includes field-level validation error details in a structured format.
    Useful for form validation and input validation errors.

    Examples:
        >>> ValidationErrorResponse(
        ...     message="Validation failed",
        ...     status_code=422,
        ...     error_code="VALIDATION_ERROR",
        ...     validation_errors=[
        ...         {"field": "email", "message": "Invalid email format"},
        ...         {"field": "age", "message": "Must be at least 18"}
        ...     ]
        ... )
    """

    error_code: str = Field(
        default="VALIDATION_ERROR",
        description="Error code, defaults to VALIDATION_ERROR",
    )

    error_category: str = Field(
        default="VALIDATION", description="Error category, defaults to VALIDATION"
    )

    status_code: int = Field(
        default=422,
        description="HTTP status code, defaults to 422 Unprocessable Entity",
    )

    validation_errors: Optional[list[Dict[str, Any]]] = Field(
        None, description="List of field-level validation errors"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": False,
                "message": "Validation failed",
                "status_code": 422,
                "error_code": "VALIDATION_ERROR",
                "error_category": "VALIDATION",
                "validation_errors": [
                    {
                        "field": "email",
                        "message": "Invalid email format",
                        "type": "value_error",
                    },
                    {
                        "field": "password",
                        "message": "Password must be at least 8 characters",
                        "type": "value_error",
                    },
                ],
                "timestamp": "2025-12-07T12:00:00Z",
            }
        }
    )
