"""
Tests for Response Models Module

Comprehensive test suite for all response models and factory functions.
Tests type safety, validation, serialization, and integration with exceptions.
"""

import pytest
from datetime import datetime
from typing import Dict, Any
from pydantic import ValidationError

# Import response models
from app.shared.responses import (
    BaseResponse,
    SuccessResponse,
    DataResponse,
    MessageResponse,
    ErrorResponse,
    ValidationErrorResponse,
    PaginatedResponse,
    PageInfo,
    CursorPaginatedResponse,
    CursorInfo,
)

# Import factory helpers
from app.shared.responses import (
    success,
    data_response,
    message_response,
    error,
    error_from_exception,
    validation_error,
    paginated,
    cursor_paginated,
)

# Import exceptions for testing integration
from app.shared.exceptions import (
    NotFoundError,
    DatabaseError,
)


# ============================================================================
# Test BaseResponse
# ============================================================================


def test_base_response_minimal():
    """Test BaseResponse with minimal fields."""
    response = BaseResponse()

    assert response.success is None
    assert response.message is None
    assert isinstance(response.timestamp, datetime)
    assert response.request_id is None
    assert response.metadata is None


def test_base_response_all_fields():
    """Test BaseResponse with all fields."""
    metadata = {"user_id": "123", "ip": "192.168.1.1"}
    response = BaseResponse(
        success=True,
        message="Test message",
        request_id="req-abc-123",
        metadata=metadata,
    )

    assert response.success is True
    assert response.message == "Test message"
    assert isinstance(response.timestamp, datetime)
    assert response.request_id == "req-abc-123"
    assert response.metadata == metadata


def test_base_response_serialization():
    """Test BaseResponse JSON serialization."""
    response = BaseResponse(success=True, message="Test")
    data = response.model_dump()

    assert "success" in data
    assert "message" in data
    assert "timestamp" in data
    assert data["success"] is True
    assert data["message"] == "Test"


# ============================================================================
# Test SuccessResponse
# ============================================================================


def test_success_response_without_data():
    """Test SuccessResponse without data."""
    response = SuccessResponse[Dict[str, Any]](
        success=True, message="Operation completed"
    )

    assert response.success is True
    assert response.message == "Operation completed"
    assert response.data is None


def test_success_response_with_data():
    """Test SuccessResponse with data."""
    data = {"id": 1, "name": "John"}
    response = SuccessResponse[Dict[str, Any]](
        success=True, data=data, message="User found"
    )

    assert response.success is True
    assert response.data == data
    assert response.message == "User found"


def test_success_response_type_safety():
    """Test SuccessResponse generic type parameter."""
    # Test with dict
    dict_response = SuccessResponse[Dict[str, int]](data={"count": 5})
    assert dict_response.data == {"count": 5}

    # Test with list
    list_response = SuccessResponse[list[str]](data=["a", "b", "c"])
    assert list_response.data == ["a", "b", "c"]


# ============================================================================
# Test DataResponse
# ============================================================================


def test_data_response_requires_data():
    """Test DataResponse requires data field."""
    with pytest.raises(ValidationError):
        DataResponse[Dict[str, Any]](success=True, message="Test")


def test_data_response_with_data():
    """Test DataResponse with required data."""
    data = {"id": 1, "value": "test"}
    response = DataResponse[Dict[str, Any]](
        success=True, data=data, message="Data retrieved"
    )

    assert response.success is True
    assert response.data == data
    assert response.message == "Data retrieved"


# ============================================================================
# Test MessageResponse
# ============================================================================


def test_message_response():
    """Test MessageResponse simple structure."""
    response = MessageResponse(success=True, message="Operation completed")

    assert response.success is True
    assert response.message == "Operation completed"


def test_message_response_defaults():
    """Test MessageResponse default values."""
    response = MessageResponse()

    assert response.success is True
    assert isinstance(response.timestamp, datetime)


# ============================================================================
# Test ErrorResponse
# ============================================================================


def test_error_response_required_fields():
    """Test ErrorResponse requires all error fields."""
    response = ErrorResponse(
        success=False,
        message="Error occurred",
        status_code=404,
        error_code="NOT_FOUND",
        error_category="NOT_FOUND",
    )

    assert response.success is False
    assert response.status_code == 404
    assert response.error_code == "NOT_FOUND"
    assert response.error_category == "NOT_FOUND"


def test_error_response_with_details():
    """Test ErrorResponse with additional details."""
    details = {"entity_type": "User", "entity_id": "123"}
    response = ErrorResponse(
        success=False,
        message="User not found",
        status_code=404,
        error_code="USER_NOT_FOUND",
        error_category="NOT_FOUND",
        details=details,
    )

    assert response.details == details


def test_error_response_status_code_validation():
    """Test ErrorResponse validates status code range."""
    with pytest.raises(ValidationError):
        ErrorResponse(
            success=False,
            message="Error",
            status_code=200,  # Invalid, must be 400+
            error_code="ERROR",
            error_category="ERROR",
        )


def test_error_response_from_exception():
    """Test ErrorResponse.from_exception() conversion."""
    exception = NotFoundError(
        message="User not found", context={"entity_type": "User", "entity_id": "123"}
    )

    response = ErrorResponse.from_exception(exception, request_id="req-123")

    assert response.success is False
    assert response.message == "User not found"
    assert response.status_code == 404
    assert response.error_code == "resource_not_found"
    assert response.error_category == "not_found"
    assert response.request_id == "req-123"
    assert "entity_type" in response.details


# ============================================================================
# Test ValidationErrorResponse
# ============================================================================


def test_validation_error_response_defaults():
    """Test ValidationErrorResponse default values."""
    response = ValidationErrorResponse()

    assert response.success is False
    assert response.status_code == 422
    assert response.error_code == "VALIDATION_ERROR"
    assert response.error_category == "VALIDATION"


def test_validation_error_response_with_errors():
    """Test ValidationErrorResponse with field errors."""
    validation_errors = [
        {"field": "email", "message": "Invalid format"},
        {"field": "age", "message": "Must be at least 18"},
    ]

    response = ValidationErrorResponse(
        message="Validation failed", validation_errors=validation_errors
    )

    assert response.validation_errors == validation_errors
    assert len(response.validation_errors) == 2


# ============================================================================
# Test PageInfo
# ============================================================================


def test_page_info_creation():
    """Test PageInfo creation with all fields."""
    page_info = PageInfo(page=1, size=20, total=100, pages=5)

    assert page_info.page == 1
    assert page_info.size == 20
    assert page_info.total == 100
    assert page_info.pages == 5


def test_page_info_validation():
    """Test PageInfo field validation."""
    # Page must be >= 1
    with pytest.raises(ValidationError):
        PageInfo(page=0, size=20, total=100, pages=5)

    # Size must be >= 1
    with pytest.raises(ValidationError):
        PageInfo(page=1, size=0, total=100, pages=5)

    # Total can be 0
    page_info = PageInfo(page=1, size=20, total=0, pages=0)
    assert page_info.total == 0


# ============================================================================
# Test PaginatedResponse
# ============================================================================


def test_paginated_response():
    """Test PaginatedResponse with items and page info."""
    items = [{"id": 1}, {"id": 2}, {"id": 3}]
    page_info = PageInfo(page=1, size=3, total=10, pages=4)

    response = PaginatedResponse[Dict[str, int]](
        success=True, items=items, page_info=page_info, message="Items retrieved"
    )

    assert response.success is True
    assert response.items == items
    assert response.page_info.page == 1
    assert response.page_info.total == 10
    assert response.message == "Items retrieved"


def test_paginated_response_empty():
    """Test PaginatedResponse with empty items."""
    page_info = PageInfo(page=1, size=20, total=0, pages=0)

    response = PaginatedResponse[Dict[str, Any]](
        success=True, items=[], page_info=page_info
    )

    assert response.items == []
    assert response.page_info.total == 0


# ============================================================================
# Test CursorInfo
# ============================================================================


def test_cursor_info_creation():
    """Test CursorInfo creation."""
    cursor_info = CursorInfo(
        cursor="abc123", has_next=True, has_previous=False, count=20
    )

    assert cursor_info.cursor == "abc123"
    assert cursor_info.has_next is True
    assert cursor_info.has_previous is False
    assert cursor_info.count == 20


# ============================================================================
# Test CursorPaginatedResponse
# ============================================================================


def test_cursor_paginated_response():
    """Test CursorPaginatedResponse with items and cursor info."""
    items = [{"id": 1}, {"id": 2}]
    cursor_info = CursorInfo(
        cursor="abc123", has_next=True, has_previous=False, count=2
    )

    response = CursorPaginatedResponse[Dict[str, int]](
        success=True, items=items, cursor_info=cursor_info
    )

    assert response.items == items
    assert response.cursor_info.cursor == "abc123"
    assert response.cursor_info.has_next is True


# ============================================================================
# Test Factory: success()
# ============================================================================


def test_factory_success_with_data():
    """Test success() factory function with data."""
    data = {"id": 1, "name": "Test"}
    response = success(data=data, message="Success")

    assert isinstance(response, SuccessResponse)
    assert response.success is True
    assert response.data == data
    assert response.message == "Success"


def test_factory_success_without_data():
    """Test success() factory function without data."""
    response = success(message="Completed")

    assert isinstance(response, SuccessResponse)
    assert response.success is True
    assert response.data is None
    assert response.message == "Completed"


# ============================================================================
# Test Factory: data_response()
# ============================================================================


def test_factory_data_response():
    """Test data_response() factory function."""
    data = {"key": "value"}
    response = data_response(data=data, message="Found")

    assert isinstance(response, DataResponse)
    assert response.success is True
    assert response.data == data


# ============================================================================
# Test Factory: message_response()
# ============================================================================


def test_factory_message_response():
    """Test message_response() factory function."""
    response = message_response("Operation completed")

    assert isinstance(response, MessageResponse)
    assert response.success is True
    assert response.message == "Operation completed"


# ============================================================================
# Test Factory: error()
# ============================================================================


def test_factory_error():
    """Test error() factory function."""
    response = error(
        message="Not found",
        status_code=404,
        error_code="NOT_FOUND",
        error_category="NOT_FOUND",
    )

    assert isinstance(response, ErrorResponse)
    assert response.success is False
    assert response.status_code == 404
    assert response.error_code == "NOT_FOUND"


def test_factory_error_with_details():
    """Test error() factory with details."""
    details = {"field": "email"}
    response = error(
        message="Invalid email",
        status_code=400,
        error_code="INVALID_EMAIL",
        error_category="VALIDATION",
        details=details,
    )

    assert response.details == details


# ============================================================================
# Test Factory: error_from_exception()
# ============================================================================


def test_factory_error_from_exception():
    """Test error_from_exception() factory function."""
    exception = DatabaseError(
        message="Connection failed", context={"operation": "SELECT", "table": "users"}
    )

    response = error_from_exception(exception, request_id="req-123")

    assert isinstance(response, ErrorResponse)
    assert response.success is False
    assert response.message == "Connection failed"
    assert response.status_code == 500
    assert response.request_id == "req-123"


# ============================================================================
# Test Factory: validation_error()
# ============================================================================


def test_factory_validation_error():
    """Test validation_error() factory function."""
    validation_errors = [{"field": "email", "message": "Invalid format"}]

    response = validation_error(
        message="Validation failed", validation_errors=validation_errors
    )

    assert isinstance(response, ValidationErrorResponse)
    assert response.success is False
    assert response.status_code == 422
    assert response.validation_errors == validation_errors


# ============================================================================
# Test Factory: paginated()
# ============================================================================


def test_factory_paginated():
    """Test paginated() factory function."""
    items = [{"id": i} for i in range(1, 21)]
    response = paginated(
        items=items, page=1, size=20, total=100, message="Products retrieved"
    )

    assert isinstance(response, PaginatedResponse)
    assert response.success is True
    assert len(response.items) == 20
    assert response.page_info.page == 1
    assert response.page_info.size == 20
    assert response.page_info.total == 100
    assert response.page_info.pages == 5  # 100 / 20


def test_factory_paginated_calculates_pages():
    """Test paginated() calculates pages correctly."""
    # 47 items, 10 per page = 5 pages
    response = paginated(items=[], page=1, size=10, total=47)
    assert response.page_info.pages == 5

    # 50 items, 10 per page = 5 pages
    response = paginated(items=[], page=1, size=10, total=50)
    assert response.page_info.pages == 5

    # 0 items = 0 pages
    response = paginated(items=[], page=1, size=10, total=0)
    assert response.page_info.pages == 0


# ============================================================================
# Test Factory: cursor_paginated()
# ============================================================================


def test_factory_cursor_paginated():
    """Test cursor_paginated() factory function."""
    items = [{"id": 1}, {"id": 2}]
    response = cursor_paginated(
        items=items, cursor="abc123", has_next=True, has_previous=False
    )

    assert isinstance(response, CursorPaginatedResponse)
    assert response.success is True
    assert response.items == items
    assert response.cursor_info.cursor == "abc123"
    assert response.cursor_info.has_next is True
    assert response.cursor_info.count == 2  # Auto-calculated


# ============================================================================
# Test Factory Aliases
# ============================================================================


def test_factory_aliases():
    """Test factory function aliases."""
    from app.shared.responses import ok, created, accepted

    # ok is alias for success
    response = ok(data={"test": "data"})
    assert isinstance(response, SuccessResponse)

    # created is alias for success
    response = created(data={"id": 1})
    assert isinstance(response, SuccessResponse)

    # accepted is alias for success
    response = accepted(message="Processing")
    assert isinstance(response, SuccessResponse)
