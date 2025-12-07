# Response Models Module

Standardized API response models for FastAPI applications following SOLID principles.

## Overview

The Response Models module provides type-safe, consistent response structures with support for success, error, and paginated responses. It integrates seamlessly with the Exception module and provides optional logging capabilities.

## Architecture

### Components

```
responses/
├── base.py           # BaseResponse - Common fields for all responses
├── success.py        # Success response models with generics
├── error.py          # Error responses with exception integration
├── pagination.py     # Pagination models (page-based & cursor-based)
├── factory.py        # Helper functions for quick response creation
└── __init__.py       # Public API exports
```

### Design Principles

1. **Type Safety**: Uses TypeVar for generic type parameters
2. **SOLID**: Single Responsibility, Dependency Inversion
3. **Framework Agnostic**: Can be used outside FastAPI
4. **Optional Integration**: Logger and Config are optional dependencies
5. **Pydantic v2**: Uses ConfigDict and modern patterns

## Core Models

### BaseResponse

Base class providing common fields for all responses:

```python
from app.shared.responses import BaseResponse

response = BaseResponse(
    success=True,
    message="Operation completed",
    request_id="req-123",
    metadata={"version": "1.0"}
)
```

**Fields:**
- `success`: Optional[bool] - Indicates if operation succeeded
- `message`: Optional[str] - Human-readable message
- `timestamp`: datetime - Auto-generated UTC timestamp
- `request_id`: Optional[str] - For request tracing
- `metadata`: Optional[Dict[str, Any]] - Additional data

### SuccessResponse[T]

Generic success response with optional typed data:

```python
from app.shared.responses import SuccessResponse

# With data
response = SuccessResponse[User](
    success=True,
    data=user,
    message="User retrieved successfully"
)

# Without data
response = SuccessResponse(
    success=True,
    message="Operation completed"
)
```

### DataResponse[T]

Success response requiring data (not optional):

```python
from app.shared.responses import DataResponse

response = DataResponse[Product](
    data=product,
    message="Product found"
)
```

### MessageResponse

Simple success response without data:

```python
from app.shared.responses import MessageResponse

response = MessageResponse(
    success=True,
    message="Item deleted successfully"
)
```

## Error Responses

### ErrorResponse

Standardized error response with HTTP status codes:

```python
from app.shared.responses import ErrorResponse

response = ErrorResponse(
    success=False,
    message="User not found",
    status_code=404,
    error_code="USER_NOT_FOUND",
    error_category="NOT_FOUND",
    details={"user_id": "123"}
)
```

**Fields:**
- `status_code`: int (400-599) - HTTP status code
- `error_code`: str - Machine-readable error code
- `error_category`: str - Error category
- `details`: Optional[Dict] - Additional error context

### Exception Integration

Convert AppException to ErrorResponse automatically:

```python
from app.shared.exceptions import NotFoundError
from app.shared.responses import ErrorResponse

try:
    user = get_user(user_id)
except NotFoundError as e:
    # Automatic status code mapping
    response = ErrorResponse.from_exception(e, request_id="req-123")
    # status_code=404, error_code="RESOURCE_NOT_FOUND", etc.
```

**Status Code Mapping:**
- `NOT_FOUND` → 404
- `VALIDATION` → 422
- `AUTHENTICATION` → 401
- `AUTHORIZATION` → 403
- `BUSINESS_RULE` → 400
- `DATABASE` → 500
- `EXTERNAL_SERVICE` → 502
- `INTERNAL` → 500

### ValidationErrorResponse

Specialized for validation errors with field-level details:

```python
from app.shared.responses import ValidationErrorResponse

response = ValidationErrorResponse(
    message="Validation failed",
    validation_errors=[
        {"field": "email", "message": "Invalid format"},
        {"field": "age", "message": "Must be at least 18"}
    ]
)
```

## Pagination

### Page-Based Pagination

Perfect for webshops and list views with numbered pages:

```python
from app.shared.responses import PaginatedResponse, PageInfo

response = PaginatedResponse[Product](
    success=True,
    items=[product1, product2, product3],
    page_info=PageInfo(
        page=1,
        size=20,
        total=100,
        pages=5
    ),
    message="Products retrieved successfully"
)
```

**PageInfo Fields:**
- `page`: int - Current page (1-indexed)
- `size`: int - Items per page
- `total`: int - Total items across all pages
- `pages`: int - Total number of pages

### Cursor-Based Pagination

For infinite scrolling or real-time data:

```python
from app.shared.responses import CursorPaginatedResponse, CursorInfo

response = CursorPaginatedResponse[Post](
    success=True,
    items=[post1, post2],
    cursor_info=CursorInfo(
        cursor="abc123",
        has_next=True,
        has_previous=False,
        count=2
    )
)
```

## Factory Functions

Quick helper functions for common response patterns:

### Success Responses

```python
from app.shared.responses import success, data_response, message_response

# Generic success with optional data
return success(data={"id": 1}, message="Created")

# Success with required data
return data_response(data=user, message="User found")

# Simple message only
return message_response("Operation completed")
```

### Error Responses

```python
from app.shared.responses import error, error_from_exception, validation_error

# Manual error
return error(
    message="Not found",
    status_code=404,
    error_code="NOT_FOUND",
    error_category="NOT_FOUND"
)

# From exception
try:
    ...
except AppException as e:
    return error_from_exception(e, request_id="req-123")

# Validation error
return validation_error(
    message="Invalid input",
    validation_errors=[{"field": "email", "message": "Required"}]
)
```

### Pagination

```python
from app.shared.responses import paginated, cursor_paginated

# Page-based (auto-calculates total pages)
return paginated(
    items=products,
    page=1,
    size=20,
    total=100
)

# Cursor-based
return cursor_paginated(
    items=posts,
    cursor="abc123",
    has_next=True
)
```

### Convenience Aliases

```python
from app.shared.responses import ok, created, accepted, not_found

# HTTP 200 OK
return ok(data=user)

# HTTP 201 Created
return created(data=new_user)

# HTTP 404 Not Found
return not_found(message="User not found", ...)
```

## FastAPI Integration

### Basic Endpoint

```python
from fastapi import APIRouter, HTTPException
from app.shared.responses import success, error_from_exception
from app.shared.exceptions import NotFoundError

router = APIRouter()

@router.get("/users/{user_id}")
async def get_user(user_id: str):
    try:
        user = await db.get_user(user_id)
        return success(data=user, message="User retrieved")
    except NotFoundError as e:
        return error_from_exception(e)
```

### With Response Models

```python
from fastapi import APIRouter
from app.shared.responses import SuccessResponse, ErrorResponse

@router.get(
    "/users/{user_id}",
    response_model=SuccessResponse[User],
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse}
    }
)
async def get_user(user_id: str):
    ...
```

### Paginated Endpoint

```python
from fastapi import APIRouter, Query
from app.shared.responses import paginated

@router.get("/products")
async def list_products(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100)
):
    items = await db.get_products(page=page, size=size)
    total = await db.count_products()
    
    return paginated(
        items=items,
        page=page,
        size=size,
        total=total,
        message="Products retrieved successfully"
    )
```

## Logger Integration

The module optionally integrates with the Logger module for debugging:

```python
# In error.py and factory.py
try:
    from app.shared.logger import get_logger
    _logger = get_logger(__name__)
except ImportError:
    _logger = None

# Used for debug logging in development
if _logger:
    _logger.debug(
        f"Creating ErrorResponse from {exception.__class__.__name__}",
        extra={"error_code": exception.error_code.value}
    )
```

**When logs are generated:**
- Exception to response conversion (DEBUG level)
- Only in development/debug mode (checks `_settings.is_development`)
- Includes request_id for tracing

## Config Integration

Optional integration with Config module for environment-aware behavior:

```python
try:
    from app.shared.config import get_settings
    _settings = get_settings()
except ImportError:
    _settings = None

# Conditional logging based on environment
if _settings and (_settings.is_development or _settings.debug):
    _logger.debug("Converting exception to ErrorResponse")
```

## Best Practices

### 1. Use Type Parameters

```python
# ✅ Good - Type safe
response = SuccessResponse[User](data=user)

# ❌ Bad - No type safety
response = SuccessResponse(data=user)
```

### 2. Use Factory Functions

```python
# ✅ Good - Concise
return success(data=user)

# ❌ Bad - Verbose
return SuccessResponse[User](success=True, data=user)
```

### 3. Include Request IDs

```python
# ✅ Good - Traceable
return error_from_exception(e, request_id=request.headers.get("X-Request-ID"))

# ❌ Bad - No tracing
return error_from_exception(e)
```

### 4. Add Context to Errors

```python
# ✅ Good - Helpful details
return error(
    message="User not found",
    details={"user_id": user_id, "searched_by": "email"}
)

# ❌ Bad - No context
return error(message="Not found")
```

### 5. Use Appropriate Status Codes

```python
# ✅ Good - Let exception integration handle it
return error_from_exception(e)

# ❌ Bad - Manual mapping can be wrong
return error(..., status_code=500)  # Should be 404?
```

## Testing

### Testing Success Responses

```python
def test_success_response():
    response = success(data={"id": 1}, message="Success")
    
    assert response.success is True
    assert response.data == {"id": 1}
    assert response.message == "Success"
    assert isinstance(response.timestamp, datetime)
```

### Testing Error Responses

```python
def test_error_from_exception():
    exception = NotFoundError(
        message="User not found",
        context={"user_id": "123"}
    )
    
    response = ErrorResponse.from_exception(exception)
    
    assert response.success is False
    assert response.status_code == 404
    assert response.error_code == "resource_not_found"
    assert response.details["user_id"] == "123"
```

### Testing Pagination

```python
def test_paginated_response():
    items = [{"id": i} for i in range(1, 21)]
    response = paginated(items=items, page=1, size=20, total=100)
    
    assert len(response.items) == 20
    assert response.page_info.page == 1
    assert response.page_info.pages == 5  # Auto-calculated
```

## Migration Guide

### From Plain Dicts

```python
# Before
return {
    "success": True,
    "data": user,
    "message": "User found"
}

# After
return success(data=user, message="User found")
```

### From HTTPException

```python
# Before
from fastapi import HTTPException

if not user:
    raise HTTPException(status_code=404, detail="User not found")

# After
from app.shared.exceptions import NotFoundError
from app.shared.responses import error_from_exception

if not user:
    raise NotFoundError(message="User not found", context={"user_id": user_id})
# In exception handler:
return error_from_exception(e)
```

## Common Patterns

### CRUD Operations

```python
# Create (201)
async def create_user(data: UserCreate):
    user = await db.create_user(data)
    return created(data=user, message="User created")

# Read (200)
async def get_user(user_id: str):
    user = await db.get_user(user_id)
    return ok(data=user)

# Update (200)
async def update_user(user_id: str, data: UserUpdate):
    user = await db.update_user(user_id, data)
    return success(data=user, message="User updated")

# Delete (200)
async def delete_user(user_id: str):
    await db.delete_user(user_id)
    return message_response("User deleted successfully")
```

### Validation with Pydantic

```python
from pydantic import ValidationError
from app.shared.responses import validation_error

try:
    user = UserCreate(**data)
except ValidationError as e:
    validation_errors = [
        {
            "field": err["loc"][0],
            "message": err["msg"],
            "type": err["type"]
        }
        for err in e.errors()
    ]
    return validation_error(
        message="Invalid input",
        validation_errors=validation_errors
    )
```

## Advanced Usage

### Custom Metadata

```python
return success(
    data=user,
    metadata={
        "version": "1.0",
        "cache_hit": True,
        "execution_time_ms": 45
    }
)
```

### Request Tracing

```python
from fastapi import Request

async def get_user(request: Request, user_id: str):
    request_id = request.headers.get("X-Request-ID")
    
    try:
        user = await db.get_user(user_id)
        return success(data=user, request_id=request_id)
    except Exception as e:
        return error_from_exception(e, request_id=request_id)
```

### Streaming Pagination

```python
async def list_items_stream(cursor: str = None):
    items, next_cursor, has_more = await db.get_items_cursor(cursor)
    
    return cursor_paginated(
        items=items,
        cursor=next_cursor or cursor,
        has_next=has_more,
        has_previous=cursor is not None
    )
```

## Troubleshooting

### Type Hints Not Working

```python
# ❌ Problem
response = SuccessResponse(data=user)  # Type[T] not inferred

# ✅ Solution
response = SuccessResponse[User](data=user)
```

### Logger Not Available

The module gracefully handles missing dependencies:

```python
# Logger is optional - no error if not available
try:
    from app.shared.logger import get_logger
    _logger = get_logger(__name__)
except ImportError:
    _logger = None  # Module still works
```

### Timestamp Issues

```python
# ✅ Uses datetime.now(UTC) - not deprecated
from datetime import datetime, UTC

timestamp: datetime = Field(
    default_factory=lambda: datetime.now(UTC)
)
```

## Performance Considerations

1. **Response Serialization**: Pydantic v2 is very fast
2. **Logger Overhead**: Only logs in debug/development
3. **Factory Functions**: No performance penalty, just convenience
4. **Type Checking**: Happens at static analysis, not runtime

## See Also

- [Exception Module](./exceptions.md) - Exception system integration
- [Logger Module](./logger.md) - Logging integration
- [Config Module](./config.md) - Configuration integration
- [Testing Guide](./testing.md) - Testing strategies
