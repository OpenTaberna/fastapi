"""
Response Factory Helpers

Convenience functions for creating standardized API responses quickly.
Reduces boilerplate and ensures consistent response structure.
"""

from typing import TYPE_CHECKING, TypeVar, Optional, Dict, Any, List
from math import ceil

from .success import SuccessResponse, DataResponse, MessageResponse
from .error import ErrorResponse, ValidationErrorResponse
from .pagination import PaginatedResponse, PageInfo, CursorPaginatedResponse, CursorInfo

if TYPE_CHECKING:
    from app.shared.exceptions import AppException

# Optional config and logger imports - gracefully handle if not available
try:
    from app.shared.config import get_settings

    _settings = get_settings()
except ImportError:
    _settings = None

try:
    from app.shared.logger import get_logger

    _logger = get_logger(__name__)
except ImportError:
    _logger = None

# Generic type variable
T = TypeVar("T")


def success(
    data: Optional[T] = None,
    message: Optional[str] = None,
    request_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> SuccessResponse[T]:
    """
    Create a generic success response.

    Args:
        data: Optional response data
        message: Optional success message
        request_id: Optional request identifier
        metadata: Optional additional metadata

    Returns:
        SuccessResponse with provided data

    Examples:
        >>> success(data={"id": 1}, message="User created")
        >>> success(message="Operation completed")
    """
    return SuccessResponse[T](
        success=True,
        data=data,
        message=message,
        request_id=request_id,
        metadata=metadata,
    )


def data_response(
    data: T,
    message: Optional[str] = None,
    request_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> DataResponse[T]:
    """
    Create a success response with required data.

    Args:
        data: Required response data
        message: Optional success message
        request_id: Optional request identifier
        metadata: Optional additional metadata

    Returns:
        DataResponse with provided data

    Examples:
        >>> data_response(data=user, message="User found")
    """
    return DataResponse[T](
        success=True,
        data=data,
        message=message,
        request_id=request_id,
        metadata=metadata,
    )


def message_response(
    message: str,
    request_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> MessageResponse:
    """
    Create a simple message response without data.

    Args:
        message: Success message
        request_id: Optional request identifier
        metadata: Optional additional metadata

    Returns:
        MessageResponse with provided message

    Examples:
        >>> message_response("Item deleted successfully")
        >>> message_response("Email sent", request_id="req-123")
    """
    return MessageResponse(
        success=True, message=message, request_id=request_id, metadata=metadata
    )


def error(
    message: str,
    status_code: int,
    error_code: str,
    error_category: str,
    details: Optional[Dict[str, Any]] = None,
    request_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> ErrorResponse:
    """
    Create an error response.

    Args:
        message: Error message
        status_code: HTTP status code (400-599)
        error_code: Machine-readable error code
        error_category: Error category
        details: Optional error details
        request_id: Optional request identifier
        metadata: Optional additional metadata

    Returns:
        ErrorResponse with provided error information

    Examples:
        >>> error(
        ...     message="User not found",
        ...     status_code=404,
        ...     error_code="USER_NOT_FOUND",
        ...     error_category="NOT_FOUND"
        ... )
    """
    return ErrorResponse(
        success=False,
        message=message,
        status_code=status_code,
        error_code=error_code,
        error_category=error_category,
        details=details,
        request_id=request_id,
        metadata=metadata,
    )


def error_from_exception(
    exception: "AppException",
    request_id: Optional[str] = None,
) -> ErrorResponse:
    """
    Create an error response from an AppException.

    Args:
        exception: AppException instance
        request_id: Optional request identifier

    Returns:
        ErrorResponse populated from exception

    Examples:
        >>> try:
        ...     raise NotFoundError("User not found")
        ... except AppException as e:
        ...     return error_from_exception(e, request_id="req-123")
    """
    if _logger and _settings:
        # Log in development/debug mode only
        if _settings.is_development or _settings.debug:
            _logger.debug(
                f"Converting {exception.__class__.__name__} to ErrorResponse",
                extra={"request_id": request_id},
            )

    return ErrorResponse.from_exception(exception, request_id=request_id)


def validation_error(
    message: str = "Validation failed",
    validation_errors: Optional[List[Dict[str, Any]]] = None,
    details: Optional[Dict[str, Any]] = None,
    request_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> ValidationErrorResponse:
    """
    Create a validation error response.

    Args:
        message: Error message
        validation_errors: List of field-level validation errors
        details: Optional additional error details
        request_id: Optional request identifier
        metadata: Optional additional metadata

    Returns:
        ValidationErrorResponse with validation errors

    Examples:
        >>> validation_error(
        ...     validation_errors=[
        ...         {"field": "email", "message": "Invalid format"}
        ...     ]
        ... )
    """
    return ValidationErrorResponse(
        success=False,
        message=message,
        status_code=422,
        error_code="VALIDATION_ERROR",
        error_category="VALIDATION",
        validation_errors=validation_errors,
        details=details,
        request_id=request_id,
        metadata=metadata,
    )


def paginated(
    items: List[T],
    page: int,
    size: int,
    total: int,
    message: Optional[str] = None,
    request_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> PaginatedResponse[T]:
    """
    Create a paginated response.

    Automatically calculates total pages from total items and page size.

    Args:
        items: List of items for current page
        page: Current page number (1-indexed)
        size: Items per page
        total: Total number of items
        message: Optional success message
        request_id: Optional request identifier
        metadata: Optional additional metadata

    Returns:
        PaginatedResponse with items and page info

    Examples:
        >>> paginated(
        ...     items=[product1, product2],
        ...     page=1,
        ...     size=20,
        ...     total=100
        ... )
    """
    pages = ceil(total / size) if size > 0 else 0

    return PaginatedResponse[T](
        success=True,
        items=items,
        page_info=PageInfo(page=page, size=size, total=total, pages=pages),
        message=message,
        request_id=request_id,
        metadata=metadata,
    )


def cursor_paginated(
    items: List[T],
    cursor: str,
    has_next: bool,
    has_previous: bool = False,
    message: Optional[str] = None,
    request_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> CursorPaginatedResponse[T]:
    """
    Create a cursor-based paginated response.

    Args:
        items: List of items for current cursor
        cursor: Current cursor position
        has_next: Whether more items exist after cursor
        has_previous: Whether items exist before cursor
        message: Optional success message
        request_id: Optional request identifier
        metadata: Optional additional metadata

    Returns:
        CursorPaginatedResponse with items and cursor info

    Examples:
        >>> cursor_paginated(
        ...     items=[post1, post2],
        ...     cursor="abc123",
        ...     has_next=True
        ... )
    """
    return CursorPaginatedResponse[T](
        success=True,
        items=items,
        cursor_info=CursorInfo(
            cursor=cursor,
            has_next=has_next,
            has_previous=has_previous,
            count=len(items),
        ),
        message=message,
        request_id=request_id,
        metadata=metadata,
    )


# Convenience aliases
ok = success  # Alias for HTTP 200 OK
created = success  # Use with 201 status in FastAPI
accepted = success  # Use with 202 status in FastAPI
no_content = message_response  # Use with 204 status in FastAPI

bad_request = error  # Use with status_code=400
not_found = error  # Use with status_code=404
conflict = error  # Use with status_code=409
internal_error = error  # Use with status_code=500
