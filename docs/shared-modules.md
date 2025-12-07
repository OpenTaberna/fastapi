# Shared Modules Guide

Guide for using shared modules in feature development.

## Overview

The `app/shared/` directory contains reusable modules that provide common functionality across all features. This guide shows how to use them correctly in your services.

```
app/shared/
├── config/          # Configuration management
├── logger/          # Structured logging
├── exceptions/      # Standardized error handling
└── responses/       # API response models
```

## Quick Start

### Basic Feature Setup

```python
# In your feature: src/app/services/my-feature/routers/items.py
from fastapi import APIRouter, HTTPException
from app.shared.logger import get_logger
from app.shared.config import get_settings
from app.shared.exceptions import NotFoundError, ValidationError
from app.shared.responses import success, error_from_exception, paginated

# Initialize
logger = get_logger(__name__)
settings = get_settings()
router = APIRouter()

@router.get("/items/{item_id}")
async def get_item(item_id: str):
    logger.info("Fetching item", extra={"item_id": item_id})
    
    try:
        item = await fetch_item(item_id)
        return success(data=item, message="Item retrieved")
    except NotFoundError as e:
        return error_from_exception(e)
```

## Configuration Module

### Getting Settings

```python
from app.shared.config import get_settings

settings = get_settings()

# Environment checks
if settings.is_production:
    # Production-only logic
    pass

if settings.is_development:
    # Development helpers
    pass

# Access settings
db_url = settings.database_url
debug_mode = settings.debug
api_name = settings.app_name
```

### Environment-Specific Behavior

```python
from app.shared.config import get_settings

settings = get_settings()

# Cache settings based on environment
if settings.is_production:
    cache_ttl = 3600  # 1 hour
else:
    cache_ttl = 60    # 1 minute for testing

# Debug logging
if settings.debug:
    logger.debug("Detailed debug information")
```

### Secrets Management

```python
from app.shared.config import get_settings

settings = get_settings()

# Secrets are automatically loaded from:
# 1. Docker secrets (/run/secrets/)
# 2. Kubernetes secrets (/var/run/secrets/)
# 3. Environment variables
# 4. .env file

# Safe to use - never logs passwords
database_url = settings.database_url  # From DATABASE_URL or secrets
redis_password = settings.redis_password  # From secrets
```

### Best Practices

```python
# ✅ Good - Singleton pattern, call once per module
from app.shared.config import get_settings
settings = get_settings()

class ItemService:
    def __init__(self):
        self.cache_enabled = settings.cache_enabled
        
# ❌ Bad - Don't call repeatedly
def process_item():
    if get_settings().debug:  # Inefficient
        ...
```

## Logger Module

### Basic Logging

```python
from app.shared.logger import get_logger

logger = get_logger(__name__)

# Different levels
logger.debug("Detailed debug info")
logger.info("General information")
logger.warning("Warning message")
logger.error("Error occurred")
```

### Structured Logging with Context

```python
from app.shared.logger import get_logger

logger = get_logger(__name__)

# Add context with extra
logger.info(
    "User created successfully",
    extra={
        "user_id": user.id,
        "email": user.email,
        "ip_address": request.client.host
    }
)

# In production (LOG_FORMAT=json), outputs:
# {
#   "timestamp": "2025-12-07T12:00:00Z",
#   "level": "INFO",
#   "message": "User created successfully",
#   "user_id": "123",
#   "email": "user@example.com",
#   "ip_address": "192.168.1.1"
# }
```

### Sensitive Data Filtering

```python
from app.shared.logger import get_logger

logger = get_logger(__name__)

# Automatically filters sensitive fields
logger.info(
    "Payment processed",
    extra={
        "user_id": "123",
        "password": "secret123",      # Filtered out!
        "credit_card": "1234-5678",   # Filtered out!
        "ssn": "123-45-6789",         # Filtered out!
        "amount": 99.99               # OK
    }
)

# Output only includes: user_id, amount
# password, credit_card, ssn are automatically removed
```

### Request Context Logging

```python
from app.shared.logger import get_logger, LoggerContext

logger = get_logger(__name__)

@router.post("/orders")
async def create_order(request: Request, data: OrderCreate):
    # Set context for all logs in this request
    with LoggerContext(
        request_id=request.headers.get("X-Request-ID"),
        user_id=current_user.id
    ):
        logger.info("Creating order")  # Includes request_id & user_id
        
        order = await process_order(data)
        
        logger.info("Order created", extra={"order_id": order.id})
        # Also includes request_id & user_id automatically
        
        return success(data=order)
```

### Performance Logging

```python
from app.shared.logger import get_logger

logger = get_logger(__name__)

@router.get("/heavy-operation")
async def heavy_operation():
    import time
    start = time.time()
    
    result = await do_heavy_work()
    
    duration = time.time() - start
    logger.info(
        "Operation completed",
        extra={
            "duration_ms": round(duration * 1000, 2),
            "result_size": len(result)
        }
    )
    
    return success(data=result)
```

### Exception Logging

```python
from app.shared.logger import get_logger
from app.shared.exceptions import DatabaseError

logger = get_logger(__name__)

try:
    result = await database.query(...)
except Exception as e:
    # Log with exception info
    logger.error(
        "Database query failed",
        extra={"query": "SELECT ...", "error": str(e)},
        exc_info=True  # Includes stack trace
    )
    raise DatabaseError(
        message="Query failed",
        context={"query": "SELECT ..."},
        original_exception=e
    )
```

### Best Practices

```python
# ✅ Good - One logger per module
from app.shared.logger import get_logger
logger = get_logger(__name__)  # Uses module name

# ✅ Good - Structured logging
logger.info("Order processed", extra={"order_id": order.id, "amount": 99.99})

# ✅ Good - Use appropriate levels
logger.debug("Entering function")  # Only in debug mode
logger.info("Business event")      # Normal operations
logger.warning("Deprecation")      # Warnings
logger.error("Failed operation")   # Errors

# ❌ Bad - String formatting in message
logger.info(f"Order {order.id} processed")  # Use extra instead

# ❌ Bad - Sensitive data in message
logger.info(f"User password: {password}")  # Use extra, will be filtered

# ❌ Bad - Too much logging
for item in items:
    logger.info(f"Processing {item}")  # Use batch logging
```

## Exception Module

### Raising Exceptions

```python
from app.shared.exceptions import (
    NotFoundError,
    ValidationError,
    DatabaseError,
    AuthenticationError,
    AuthorizationError,
    BusinessRuleError
)

# Not found
async def get_user(user_id: str):
    user = await db.get_user(user_id)
    if not user:
        raise NotFoundError(
            message=f"User {user_id} not found",
            context={"user_id": user_id, "searched_by": "id"}
        )
    return user

# Validation
def create_user(data: dict):
    if not data.get("email"):
        raise ValidationError(
            message="Email is required",
            context={"field": "email", "value": None}
        )

# Database errors
async def save_user(user):
    try:
        await db.save(user)
    except DBConnectionError as e:
        raise DatabaseError(
            message="Failed to save user",
            context={"user_id": user.id},
            original_exception=e
        )
```

### Using Helper Functions

```python
from app.shared.exceptions import (
    entity_not_found,
    missing_field,
    invalid_format,
    database_connection_error,
    token_expired,
    access_denied
)

# Quick exception creation
def get_product(product_id: str):
    product = db.get_product(product_id)
    if not product:
        raise entity_not_found("Product", product_id)
        # Equivalent to:
        # raise NotFoundError(
        #     message="Product not found",
        #     context={"entity_type": "Product", "entity_id": product_id}
        # )

# Validation helpers
def validate_email(email: str):
    if not "@" in email:
        raise invalid_format("email", email, "Must contain @")

# Authorization
def delete_item(item_id: str, user_id: str):
    if not has_permission(user_id, "delete"):
        raise access_denied("delete", "item", user_id)
```

### Exception Context

```python
from app.shared.exceptions import NotFoundError

# Add context for debugging
raise NotFoundError(
    message="Order not found",
    context={
        "order_id": order_id,
        "user_id": current_user.id,
        "search_criteria": {"status": "pending"},
        "timestamp": datetime.utcnow().isoformat()
    }
)

# Context is included in:
# 1. Error response details
# 2. Log messages (automatic)
# 3. Exception.to_dict() output
```

### Automatic Logging

```python
from app.shared.exceptions import NotFoundError, DatabaseError

# Exceptions automatically log based on severity:

# Client errors (4xx) - WARNING level
raise NotFoundError("User not found")  # Logs at WARNING
raise ValidationError("Invalid input")  # Logs at WARNING

# Server errors (5xx) - ERROR level
raise DatabaseError("Connection failed")  # Logs at ERROR
raise InternalError("Unexpected error")   # Logs at ERROR

# Disable auto-logging if needed
raise NotFoundError("User not found", should_auto_log=False)
```

### Best Practices

```python
# ✅ Good - Specific exception types
raise NotFoundError("User not found")

# ✅ Good - Add context
raise ValidationError(
    message="Invalid email",
    context={"field": "email", "value": email}
)

# ✅ Good - Preserve original exception
try:
    await external_api.call()
except RequestException as e:
    raise ExternalServiceError(
        message="API call failed",
        original_exception=e
    )

# ❌ Bad - Generic exceptions
raise Exception("Something went wrong")

# ❌ Bad - No context
raise NotFoundError("Not found")

# ❌ Bad - Swallow exceptions
try:
    ...
except Exception:
    pass  # Don't do this!
```

## Response Module

### Success Responses

```python
from app.shared.responses import success, data_response, message_response

# Simple success
@router.get("/items/{item_id}")
async def get_item(item_id: str):
    item = await db.get_item(item_id)
    return success(data=item, message="Item retrieved")

# Required data
@router.get("/users/{user_id}")
async def get_user(user_id: str):
    user = await db.get_user(user_id)
    return data_response(data=user, message="User found")

# No data, just message
@router.delete("/items/{item_id}")
async def delete_item(item_id: str):
    await db.delete_item(item_id)
    return message_response("Item deleted successfully")
```

### Error Responses

```python
from app.shared.responses import error_from_exception, validation_error
from app.shared.exceptions import NotFoundError, ValidationError

@router.get("/items/{item_id}")
async def get_item(item_id: str):
    try:
        item = await db.get_item(item_id)
        return success(data=item)
    except NotFoundError as e:
        # Automatic status code mapping
        return error_from_exception(e)
        # Returns: status_code=404, error_code="RESOURCE_NOT_FOUND"

# Manual validation errors
@router.post("/items")
async def create_item(data: dict):
    errors = validate_item(data)
    if errors:
        return validation_error(
            message="Validation failed",
            validation_errors=errors
        )
    
    item = await db.create_item(data)
    return success(data=item, message="Item created")
```

### Pagination

```python
from app.shared.responses import paginated

@router.get("/products")
async def list_products(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100)
):
    # Get paginated data
    products = await db.get_products(page=page, size=size)
    total = await db.count_products()
    
    # Auto-calculates total pages
    return paginated(
        items=products,
        page=page,
        size=size,
        total=total,
        message="Products retrieved"
    )
    # Returns:
    # {
    #   "success": true,
    #   "items": [...],
    #   "page_info": {
    #     "page": 1,
    #     "size": 20,
    #     "total": 100,
    #     "pages": 5
    #   }
    # }
```

### Request Tracing

```python
from fastapi import Request
from app.shared.responses import success, error_from_exception

@router.get("/items/{item_id}")
async def get_item(request: Request, item_id: str):
    request_id = request.headers.get("X-Request-ID")
    
    try:
        item = await db.get_item(item_id)
        return success(
            data=item,
            request_id=request_id,
            metadata={"cache_hit": False}
        )
    except Exception as e:
        return error_from_exception(e, request_id=request_id)
```

### Best Practices

```python
# ✅ Good - Use factory functions
return success(data=user)

# ✅ Good - Include request IDs
return success(data=user, request_id=request_id)

# ✅ Good - Let exception integration handle status codes
return error_from_exception(e)

# ❌ Bad - Manual construction
return SuccessResponse[User](success=True, data=user, ...)

# ❌ Bad - Wrong status codes
return error(..., status_code=500)  # Should be 404?

# ❌ Bad - No context
return error(message="Error")
```

## Combining All Modules

### Complete Feature Example

```python
from fastapi import APIRouter, Request, Query
from app.shared.logger import get_logger, LoggerContext
from app.shared.config import get_settings
from app.shared.exceptions import NotFoundError, ValidationError, entity_not_found
from app.shared.responses import (
    success, 
    error_from_exception, 
    paginated,
    validation_error
)

# Initialize
logger = get_logger(__name__)
settings = get_settings()
router = APIRouter()

@router.get("/items/{item_id}")
async def get_item(request: Request, item_id: str):
    """Get single item by ID."""
    request_id = request.headers.get("X-Request-ID")
    
    # Set logging context
    with LoggerContext(request_id=request_id):
        logger.info("Fetching item", extra={"item_id": item_id})
        
        try:
            # Business logic
            item = await db.get_item(item_id)
            
            if not item:
                raise entity_not_found("Item", item_id)
            
            # Cache in production
            if settings.is_production and settings.cache_enabled:
                await cache.set(f"item:{item_id}", item, ttl=300)
            
            logger.info("Item retrieved", extra={"item_id": item_id})
            
            return success(
                data=item,
                message="Item retrieved successfully",
                request_id=request_id
            )
            
        except NotFoundError as e:
            logger.warning("Item not found", extra={"item_id": item_id})
            return error_from_exception(e, request_id=request_id)
            
        except Exception as e:
            logger.error(
                "Unexpected error",
                extra={"item_id": item_id},
                exc_info=True
            )
            raise

@router.get("/items")
async def list_items(
    request: Request,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    category: str = Query(None)
):
    """List items with pagination."""
    request_id = request.headers.get("X-Request-ID")
    
    with LoggerContext(request_id=request_id):
        logger.info(
            "Listing items",
            extra={"page": page, "size": size, "category": category}
        )
        
        try:
            # Get data
            items = await db.get_items(
                page=page,
                size=size,
                category=category
            )
            total = await db.count_items(category=category)
            
            logger.info(
                "Items retrieved",
                extra={"count": len(items), "total": total}
            )
            
            return paginated(
                items=items,
                page=page,
                size=size,
                total=total,
                request_id=request_id,
                message=f"Retrieved {len(items)} items"
            )
            
        except Exception as e:
            logger.error("Failed to list items", exc_info=True)
            raise

@router.post("/items")
async def create_item(request: Request, data: dict):
    """Create new item."""
    request_id = request.headers.get("X-Request-ID")
    
    with LoggerContext(request_id=request_id):
        logger.info("Creating item", extra={"data": data})
        
        try:
            # Validate
            errors = validate_item_data(data)
            if errors:
                logger.warning("Validation failed", extra={"errors": errors})
                return validation_error(
                    message="Validation failed",
                    validation_errors=errors,
                    request_id=request_id
                )
            
            # Create
            item = await db.create_item(data)
            
            logger.info(
                "Item created",
                extra={"item_id": item.id, "category": item.category}
            )
            
            return success(
                data=item,
                message="Item created successfully",
                request_id=request_id,
                metadata={"created_at": item.created_at.isoformat()}
            )
            
        except ValidationError as e:
            return error_from_exception(e, request_id=request_id)
            
        except Exception as e:
            logger.error("Failed to create item", exc_info=True)
            raise
```

### Service Layer Example

```python
from app.shared.logger import get_logger
from app.shared.config import get_settings
from app.shared.exceptions import DatabaseError, entity_not_found

logger = get_logger(__name__)
settings = get_settings()

class ItemService:
    """Business logic for items."""
    
    def __init__(self):
        self.cache_enabled = settings.cache_enabled
        self.cache_ttl = 300 if settings.is_production else 60
    
    async def get_item(self, item_id: str) -> dict:
        """Get item with caching."""
        logger.debug("Getting item", extra={"item_id": item_id})
        
        # Check cache
        if self.cache_enabled:
            cached = await cache.get(f"item:{item_id}")
            if cached:
                logger.debug("Cache hit", extra={"item_id": item_id})
                return cached
        
        # Fetch from database
        try:
            item = await db.get_item(item_id)
        except Exception as e:
            raise DatabaseError(
                message="Failed to fetch item",
                context={"item_id": item_id},
                original_exception=e
            )
        
        if not item:
            raise entity_not_found("Item", item_id)
        
        # Cache result
        if self.cache_enabled:
            await cache.set(f"item:{item_id}", item, ttl=self.cache_ttl)
        
        return item
    
    async def create_item(self, data: dict) -> dict:
        """Create new item."""
        logger.info("Creating item", extra={"category": data.get("category")})
        
        try:
            item = await db.create_item(data)
            
            # Invalidate list cache
            if self.cache_enabled:
                await cache.delete("items:list:*")
            
            logger.info("Item created", extra={"item_id": item.id})
            return item
            
        except Exception as e:
            logger.error("Failed to create item", exc_info=True)
            raise DatabaseError(
                message="Failed to create item",
                context={"data": data},
                original_exception=e
            )
```

## Testing with Shared Modules

### Testing with Config

```python
import pytest
from app.shared.config import get_settings, clear_settings_cache

def test_feature_in_production():
    """Test production behavior."""
    # Setup
    clear_settings_cache()
    settings = get_settings()
    
    # Assume production
    assert settings.is_production
    
    # Test production logic
    result = my_function()
    assert result.cache_enabled is True

def test_feature_in_development():
    """Test development behavior."""
    # Mock development
    with patch.dict(os.environ, {"ENVIRONMENT": "development"}):
        clear_settings_cache()
        settings = get_settings()
        
        assert settings.is_development
        
        # Test debug logic
        result = my_function()
        assert result.debug_mode is True
```

### Testing with Logger

```python
import pytest
from app.shared.logger import get_logger

def test_logging(caplog):
    """Test logging output."""
    logger = get_logger(__name__)
    
    with caplog.at_level("INFO"):
        logger.info("Test message", extra={"key": "value"})
    
    assert "Test message" in caplog.text
    assert "key" in caplog.text
```

### Testing with Exceptions

```python
import pytest
from app.shared.exceptions import NotFoundError

def test_exception_handling():
    """Test exception is raised correctly."""
    with pytest.raises(NotFoundError) as exc_info:
        get_nonexistent_item("invalid-id")
    
    assert "not found" in str(exc_info.value)
    assert exc_info.value.context["item_id"] == "invalid-id"
```

### Testing with Responses

```python
from app.shared.responses import success, error_from_exception
from app.shared.exceptions import NotFoundError

def test_success_response():
    """Test success response format."""
    response = success(data={"id": 1}, message="Found")
    
    assert response.success is True
    assert response.data == {"id": 1}
    assert response.message == "Found"

def test_error_response():
    """Test error response from exception."""
    exc = NotFoundError("Item not found", context={"id": "123"})
    response = error_from_exception(exc)
    
    assert response.success is False
    assert response.status_code == 404
    assert response.error_code == "resource_not_found"
```

## Common Patterns

### Health Check Endpoint

```python
from fastapi import APIRouter
from app.shared.config import get_settings
from app.shared.responses import success

router = APIRouter()
settings = get_settings()

@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return success(
        data={
            "status": "healthy",
            "environment": settings.environment,
            "version": settings.app_version
        },
        message="Service is healthy"
    )
```

### Error Handling Middleware

```python
from fastapi import Request
from app.shared.logger import get_logger
from app.shared.exceptions import AppException
from app.shared.responses import error_from_exception

logger = get_logger(__name__)

@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    """Handle all application exceptions."""
    request_id = request.headers.get("X-Request-ID")
    
    logger.warning(
        f"Application exception: {exc.message}",
        extra={
            "error_code": exc.error_code.value,
            "request_id": request_id,
            "path": request.url.path
        }
    )
    
    return error_from_exception(exc, request_id=request_id)
```

### Request Logging Middleware

```python
from fastapi import Request
from app.shared.logger import get_logger, LoggerContext
import time

logger = get_logger(__name__)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all requests."""
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    start_time = time.time()
    
    with LoggerContext(request_id=request_id):
        logger.info(
            "Request started",
            extra={
                "method": request.method,
                "path": request.url.path,
                "client": request.client.host
            }
        )
        
        response = await call_next(request)
        
        duration = time.time() - start_time
        logger.info(
            "Request completed",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round(duration * 1000, 2)
            }
        )
        
        return response
```

## Troubleshooting

### Logger Not Working

```python
# ✅ Check logger is initialized
from app.shared.logger import get_logger
logger = get_logger(__name__)  # Use __name__

# ✅ Check log level
from app.shared.config import get_settings
settings = get_settings()
print(f"Log level: {settings.log_level}")  # Should be DEBUG/INFO/etc

# ❌ Don't create logger directly
import logging
logger = logging.getLogger()  # Don't do this
```

### Config Not Loading

```python
# ✅ Check environment
from app.shared.config import get_settings
settings = get_settings()
print(f"Environment: {settings.environment}")

# ✅ Check .env file exists
import os
print(f".env exists: {os.path.exists('.env')}")

# ✅ Clear cache if needed
from app.shared.config import clear_settings_cache
clear_settings_cache()
settings = get_settings()  # Reload
```

### Exceptions Not Logging

```python
# ✅ Check auto-logging is enabled (default)
raise NotFoundError("Not found")  # Automatically logs

# ✅ Disable if needed
raise NotFoundError("Not found", should_auto_log=False)

# ✅ Check log level
# WARNING level logs client errors (4xx)
# ERROR level logs server errors (5xx)
```

## Migration Checklist

Moving from direct logging/exceptions to shared modules:

- [ ] Replace `logging.getLogger()` with `get_logger(__name__)`
- [ ] Replace `os.getenv()` with `get_settings().{setting}`
- [ ] Replace `raise HTTPException` with `raise NotFoundError/ValidationError/etc`
- [ ] Replace dict responses with `success()`/`error_from_exception()`
- [ ] Add request_id to responses for tracing
- [ ] Use structured logging with `extra={}` instead of f-strings
- [ ] Add LoggerContext for request-scoped logging
- [ ] Update tests to use shared module helpers

## See Also

- [Config Module](./config.md) - Detailed configuration guide
- [Logger Module](./logger.md) - Advanced logging patterns
- [Exception Module](./exceptions.md) - All exception types
- [Response Module](./responses.md) - All response models
- [Testing Guide](./testing.md) - Testing strategies
