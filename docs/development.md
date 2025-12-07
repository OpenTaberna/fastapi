# Development Guide

## Overview

This guide provides practical workflows and best practices for developing features in the OpenTaberna FastAPI project.

## Table of Contents

- [Adding a New Feature](#adding-a-new-feature)
- [Code Quality](#code-quality)
- [Code Review Checklist](#code-review-checklist)
- [Best Practices](#best-practices)
- [Common Patterns](#common-patterns)

---

## Adding a New Feature

### Step-by-Step Workflow

1. **Create service directory:**
   ```bash
   mkdir -p src/app/services/my-feature/{routers,models,functions,services}
   touch src/app/services/my-feature/my-feature.py
   ```

2. **Define models** in `models/`:
   ```python
   # models/thing.py
   from pydantic import BaseModel, Field
   
   class ThingCreate(BaseModel):
       """Schema for creating a thing."""
       name: str = Field(..., min_length=1)
       description: str | None = None
   
   class ThingResponse(BaseModel):
       """Schema for thing responses."""
       id: str
       name: str
       description: str | None
       created_at: datetime
   ```

3. **Write business logic** in `functions/`:
   ```python
   # functions/create_thing.py
   from ..models.thing import ThingCreate, ThingResponse
   from app.shared.logger import get_logger
   
   logger = get_logger(__name__)
   
   async def create_thing_logic(thing: ThingCreate) -> ThingResponse:
       """
       Business logic for creating a thing.
       
       Args:
           thing: Thing data to create
           
       Returns:
           Created thing with ID
       """
       # Validate business rules
       if not thing.name:
           raise ValueError("Name is required")
       
       # Call service layer
       created = await save_thing(thing)
       
       logger.info("Thing created", thing_id=created.id)
       
       return created
   ```

4. **Add database operations** in `services/`:
   ```python
   # services/database.py
   from sqlalchemy import select
   from app.shared.database import get_session
   from ..models.thing import ThingCreate, ThingDB
   
   async def save_thing(thing: ThingCreate) -> ThingDB:
       """Save thing to database."""
       async with get_session() as session:
           db_thing = ThingDB(**thing.dict())
           session.add(db_thing)
           await session.commit()
           await session.refresh(db_thing)
           return db_thing
   ```

5. **Create router** in `routers/`:
   ```python
   # routers/things.py
   from fastapi import APIRouter, HTTPException, status
   from ..models.thing import ThingCreate, ThingResponse
   from ..functions.create_thing import create_thing_logic
   
   router = APIRouter()
   
   @router.post("/", response_model=ThingResponse, status_code=status.HTTP_201_CREATED)
   async def create_thing(thing: ThingCreate):
       """Create a new thing."""
       try:
           return await create_thing_logic(thing)
       except ValueError as e:
           raise HTTPException(status_code=400, detail=str(e))
   ```

6. **Register in entry point:**
   ```python
   # my-feature.py
   """
   My Feature Service
   
   Entry point for the my-feature module.
   """
   
   from fastapi import APIRouter
   from .routers import things
   
   router = APIRouter(prefix="/my-feature", tags=["My Feature"])
   router.include_router(things.router)
   
   __all__ = ["router"]
   ```

7. **Include in main app:**
   ```python
   # main.py
   from fastapi import FastAPI
   from app.services.my_feature import my_feature
   
   app = FastAPI(title="OpenTaberna API")
   
   app.include_router(my_feature.router, prefix="/api/v1")
   ```

8. **Write tests:**
   ```python
   # tests/test_my_feature.py
   from app.services.my_feature.functions.create_thing import create_thing_logic
   from app.services.my_feature.models.thing import ThingCreate
   
   def test_create_thing():
       """Test thing creation logic."""
       thing = ThingCreate(name="Test Thing")
       result = await create_thing_logic(thing)
       
       assert result.name == "Test Thing"
       assert result.id is not None
   ```

---

## Code Quality

### Running Ruff

```bash
# Format code (Black-compatible)
ruff format src/ tests/

# Check for issues
ruff check src/ tests/

# Check and auto-fix
ruff check --fix src/ tests/

# Combined (recommended before commit)
ruff format && ruff check --fix src/ && ruff check --fix tests/
```

### Pre-commit Hook

Add to `.git/hooks/pre-commit`:

```bash
#!/bin/bash
echo "Running code quality checks..."

ruff format && ruff check --fix src/ && ruff check --fix tests/
if [ $? -ne 0 ]; then
    echo "❌ Ruff checks failed!"
    exit 1
fi

echo "Running tests..."
pytest
if [ $? -ne 0 ]; then
    echo "❌ Tests failed!"
    exit 1
fi

echo "✅ All checks passed!"
```

Make it executable:
```bash
chmod +x .git/hooks/pre-commit
```

### Ruff Configuration

In `pyproject.toml`:

```toml
[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = [
    "E",   # pycodestyle errors
    "W",   # pycodestyle warnings
    "F",   # pyflakes
    "I",   # isort
    "N",   # pep8-naming
]
ignore = []

[tool.ruff.format]
quote-style = "double"
indent-style = "space"
```

---

## Code Review Checklist

Before submitting a pull request, verify:

### Architecture
- [ ] Follows SOLID principles
- [ ] Code is in the correct service directory
- [ ] Entry point file exports router correctly
- [ ] Service is self-contained (no cross-service imports)

### Code Organization
- [ ] Routers only handle HTTP concerns
- [ ] Business logic is in `functions/`
- [ ] Database operations are in `services/`
- [ ] Models use Pydantic validation
- [ ] Clear separation of concerns

### Code Quality
- [ ] All functions have docstrings
- [ ] Type hints are present
- [ ] No hardcoded values (use config)
- [ ] Proper error handling
- [ ] Logging for important actions
- [ ] Ruff passes without errors

### Testing
- [ ] Tests cover all code paths
- [ ] Tests are independent
- [ ] Tests use fixtures appropriately
- [ ] Mock external dependencies
- [ ] All tests pass

### Documentation
- [ ] README updated if needed
- [ ] API endpoints documented
- [ ] Complex logic has comments
- [ ] Breaking changes noted

---

## Best Practices

### 1. Keep Services Independent

Services should not directly import from each other:

```python
# ❌ Bad - Direct dependency
from app.services.user_management.functions.get_user import get_user

# ✅ Good - Through shared interface
from app.shared.interfaces import UserService
user_service = UserService()
user = await user_service.get_user(id)
```

### 2. Use Dependency Injection

```python
from typing import Protocol

class ItemRepository(Protocol):
    async def save(self, item): ...
    async def get(self, id: str): ...

async def create_item(
    item: ItemCreate,
    repo: ItemRepository  # Injected, easy to mock
):
    """Create item using injected repository."""
    return await repo.save(item)
```

### 3. Configuration Over Code

```python
# ❌ Bad - Hardcoded
DATABASE_URL = "postgresql://localhost/db"
MAX_PRICE = 10000

# ✅ Good - From environment
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str
    max_item_price: float = 10000.0
    
    class Config:
        env_file = ".env"

settings = Settings()
```

### 4. Fail Fast with Validation

```python
from pydantic import BaseModel, Field, validator

class Item(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    price: float = Field(..., gt=0)
    
    @validator('price')
    def price_must_be_reasonable(cls, v):
        if v > 10000:
            raise ValueError('Price exceeds maximum')
        return v
```

### 5. Comprehensive Error Handling

```python
from fastapi import HTTPException, status

@router.post("/items")
async def create_item(item: ItemCreate):
    """Create item with proper error handling."""
    try:
        return await create_item_logic(item)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except DatabaseError as e:
        logger.error("Database error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )
```

### 6. Document with Examples

```python
async def create_item(item: ItemCreate) -> ItemResponse:
    """
    Create a new item in the store.
    
    Args:
        item: Item data with name, price, and category
        
    Returns:
        Created item with generated ID and timestamp
        
    Raises:
        ValueError: If price exceeds maximum (10,000)
        
    Example:
        >>> item = ItemCreate(name="Chair", price=99.99, category="furniture")
        >>> result = await create_item(item)
        >>> result.id
        "item-123"
    """
    if item.price > 10000:
        raise ValueError("Price exceeds maximum")
    
    return await save_item(item)
```

### 7. Use Structured Logging

```python
from app.shared.logger import get_logger, LogContext

logger = get_logger(__name__)

async def process_order(order_id: str):
    """Process order with contextual logging."""
    with LogContext(order_id=order_id):
        logger.info("Processing order started")
        
        try:
            result = await process(order_id)
            logger.info("Order processed successfully", amount=result.total)
            return result
        except Exception as e:
            logger.error("Order processing failed", error=str(e))
            raise
```

### 8. Type Hints Everywhere

```python
from typing import List, Optional

# ✅ Good - Clear types
async def get_items(
    category: str,
    limit: int = 10,
    offset: int = 0
) -> List[ItemResponse]:
    """Get items with proper type hints."""
    return await fetch_items(category, limit, offset)

# ❌ Bad - No type information
async def get_items(category, limit=10, offset=0):
    return await fetch_items(category, limit, offset)
```

---

## Common Patterns

### Pagination

```python
from pydantic import BaseModel
from typing import Generic, TypeVar, List

T = TypeVar('T')

class PaginatedResponse(BaseModel, Generic[T]):
    items: List[T]
    total: int
    page: int
    page_size: int
    has_next: bool

@router.get("/items", response_model=PaginatedResponse[ItemResponse])
async def list_items(page: int = 1, page_size: int = 20):
    """List items with pagination."""
    items, total = await get_items_paginated(page, page_size)
    
    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        has_next=(page * page_size) < total
    )
```

### Filtering

```python
from typing import Optional

class ItemFilters(BaseModel):
    category: Optional[str] = None
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    search: Optional[str] = None

@router.get("/items")
async def list_items(filters: ItemFilters = Depends()):
    """List items with filters."""
    return await get_items_filtered(filters)
```

### Background Tasks

```python
from fastapi import BackgroundTasks

def send_email(email: str, message: str):
    """Send email in background."""
    # Email sending logic
    pass

@router.post("/items")
async def create_item(
    item: ItemCreate,
    background_tasks: BackgroundTasks
):
    """Create item and send notification."""
    created = await create_item_logic(item)
    
    background_tasks.add_task(
        send_email,
        "admin@example.com",
        f"New item created: {created.name}"
    )
    
    return created
```

### Caching

```python
from functools import lru_cache
from datetime import datetime, timedelta

# In-memory cache
@lru_cache(maxsize=128)
async def get_categories() -> List[Category]:
    """Get categories with caching."""
    return await fetch_categories_from_db()

# Redis cache
async def get_item_cached(item_id: str) -> Optional[Item]:
    """Get item with Redis cache."""
    # Try cache first
    cached = await redis.get(f"item:{item_id}")
    if cached:
        return Item.parse_raw(cached)
    
    # Fetch from database
    item = await get_item_from_db(item_id)
    
    # Cache for 1 hour
    await redis.setex(
        f"item:{item_id}",
        3600,
        item.json()
    )
    
    return item
```

---

## Quick Reference

### Common Commands

```bash
# Code quality
ruff format && ruff check --fix src/ && ruff check --fix tests/

# Testing
pytest                    # Run all tests
pytest -v                 # Verbose
pytest -k "test_name"     # Run specific test

# Development
uvicorn app.main:app --reload  # Run server with auto-reload
```

### File Structure Template

```
my-feature/
├── my-feature.py         # Entry point
├── routers/
│   └── things.py         # Endpoints
├── models/
│   └── thing.py          # Pydantic models
├── functions/
│   └── create_thing.py   # Business logic
└── services/
    └── database.py       # External services
```

### Import Pattern

```python
# In routers
from ..models.thing import ThingCreate
from ..functions.create_thing import create_thing_logic

# In functions
from ..models.thing import ThingCreate
from ..services.database import save_thing
from app.shared.logger import get_logger

# In services
from sqlalchemy import select
from app.shared.database import get_session
```

That's it! Follow these patterns and your code will be consistent, maintainable, and scalable.
