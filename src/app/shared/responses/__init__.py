"""
Response Models Module

Standardized API response models for FastAPI applications.
Provides type-safe, consistent response structures with support for
success, error, and paginated responses.

This module follows SOLID principles and is framework-agnostic,
making it suitable for use in any Python API project.

Usage:
    from app.shared.responses import success, error, paginated
    from app.shared.responses import SuccessResponse, ErrorResponse

    # Simple success response
    return success(data={"id": 1}, message="User created")

    # Error response from exception
    try:
        ...
    except AppException as e:
        return error_from_exception(e)

    # Paginated response
    return paginated(items=products, page=1, size=20, total=100)
"""

# Base response
from .base import BaseResponse

# Success responses
from .success import (
    SuccessResponse,
    DataResponse,
    MessageResponse,
)

# Error responses
from .error import (
    ErrorResponse,
    ValidationErrorResponse,
)

# Pagination responses
from .pagination import (
    PaginatedResponse,
    PageInfo,
    CursorPaginatedResponse,
    CursorInfo,
)

# Factory helpers
from .factory import (
    success,
    data_response,
    message_response,
    error,
    error_from_exception,
    validation_error,
    paginated,
    cursor_paginated,
    # Aliases
    ok,
    created,
    accepted,
    no_content,
    bad_request,
    not_found,
    conflict,
    internal_error,
)

__all__ = [
    # Base
    "BaseResponse",
    # Success
    "SuccessResponse",
    "DataResponse",
    "MessageResponse",
    # Error
    "ErrorResponse",
    "ValidationErrorResponse",
    # Pagination
    "PaginatedResponse",
    "PageInfo",
    "CursorPaginatedResponse",
    "CursorInfo",
    # Factory helpers
    "success",
    "data_response",
    "message_response",
    "error",
    "error_from_exception",
    "validation_error",
    "paginated",
    "cursor_paginated",
    # Aliases
    "ok",
    "created",
    "accepted",
    "no_content",
    "bad_request",
    "not_found",
    "conflict",
    "internal_error",
]
