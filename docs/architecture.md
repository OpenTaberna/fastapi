# Architecture Documentation

## Overview

The OpenTaberna FastAPI project follows a **modular, scalable architecture** designed for long-term maintainability and growth. This document outlines the architectural design principles and code structure.

## Table of Contents

- [Project Structure](#project-structure)
- [Service Architecture](#service-architecture)
- [Why This Architecture](#why-this-architecture)

---

## Design Principles

The project is built on four core principles:


### 1. SOLID Principles

All code follows SOLID principles for maintainable, extensible design:

- **S**ingle Responsibility Principle - Each module has one reason to change
- **O**pen/Closed Principle - Open for extension, closed for modification
- **L**iskov Substitution Principle - Components are interchangeable through interfaces
- **I**nterface Segregation Principle - Focused, minimal interfaces
- **D**ependency Inversion Principle - Depend on abstractions, not concretions

**Example:** The logger module demonstrates all SOLID principles with separate files for interfaces, implementations, and configuration.

### 2. Maintainable Components

Every shared component is designed to be **self-contained and reusable**:

- **Logger** - Production-ready logging with structured output
- **Exceptions** - Centralized error handling
- **Authentication** - Keycloak integration
- **Database** - Connection and session management
- **Validation** - Input validation helpers

**Goal:** Write once, use everywhere, never touch again.

### 3. Modular Service Structure

The API uses a **"mini-API" pattern** where each feature is a self-contained module:

```
services/
├── crud-item-store/           # Feature: Item Store CRUD
│   ├── crud-item-store.py    # Entry point (imports & registers)
│   ├── functions/            # Business logic
│   ├── models/               # Data models
│   ├── routers/              # API endpoints
│   └── services/             # External integrations
│
└── user-management/          # Feature: User Management
    ├── user-management.py    # Entry point
    ├── functions/
    ├── models/
    ├── routers/
    └── services/
```

**Benefits:**
- Each feature can be developed independently
- Easy to onboard new developers to specific features
- Simple to test in isolation
- Clear ownership and responsibility
- Can scale to hundreds of features without complexity

### 4. Everything is Testable

**100% test coverage is the goal.** All code must be designed with testing in mind:

- Pure functions where possible
- Dependency injection for external services
- Clear interfaces for mocking
- Isolated test environments

Tests live in `tests/` and mirror the `src/` structure.

---

## Project Structure

```
fastapi_opentaberna/
├── src/
│   └── app/
│       ├── main.py              # FastAPI application entry point
│       │
│       ├── shared/              # Shared utilities & infrastructure
│       │   ├── logger/          # Logging system
│       │   ├── exceptions.py    # Custom exceptions
│       │   ├── database.py      # Database connections
│       │   └── validators.py    # Input validation
│       │
│       ├── authorize/           # Authentication & Authorization
│       │   └── keycloak.py      # Keycloak integration
│       │
│       └── services/            # Feature modules ("mini-APIs")
│           ├── crud-item-store/
│           ├── user-management/
│           └── order-processing/
│
├── tests/                       # Test suite
│   ├── test_logger_module.py
│   ├── test_item_service.py
│   └── integration/
│
├── docs/                        # Documentation
├── conftest.py                  # Pytest configuration
├── pyproject.toml              # Project dependencies
└── README.md
```

### Core Components

#### `main.py` - Application Entry Point

The main FastAPI application that:
- Initializes the FastAPI app
- Registers middleware
- Includes routers from services
- Configures CORS, logging, etc.

```python
from fastapi import FastAPI
from app.services.crud_item_store import crud_item_store

app = FastAPI(title="OpenTaberna API")

# Include service routers
app.include_router(crud_item_store.router, prefix="/api/v1")
```

#### `shared/` - Shared Infrastructure

Reusable components used across all services:

- **`logger/`** - Structured logging system
- **`exceptions.py`** - Custom exception classes
- **`database.py`** - Database connection management
- **`validators.py`** - Common validation functions
- **`utils.py`** - Utility functions

**Rule:** Shared modules should be framework-agnostic and testable in isolation.

#### `authorize/` - Authentication Module

Handles authentication and authorization:

- **`keycloak.py`** - Keycloak integration
- Token validation
- Role-based access control
- User session management

#### `services/` - Feature Modules

Each service is a **self-contained mini-API** with its own:
- Routes
- Models
- Business logic
- External service integrations

---

## Service Architecture

Each service follows a consistent structure for predictability and maintainability.

### Service Structure

```
services/crud-item-store/
├── crud-item-store.py       # Entry point & router registration
│
├── routers/                 # API endpoints
│   ├── __init__.py
│   ├── items.py            # GET, POST /items
│   └── categories.py       # GET, POST /categories
│
├── models/                  # Data models & schemas
│   ├── __init__.py
│   ├── item.py             # Pydantic models
│   └── category.py
│
├── functions/               # Business logic
│   ├── __init__.py
│   ├── create_item.py      # Pure business logic
│   ├── update_item.py
│   └── validate_item.py
│
└── services/                # External integrations
    ├── __init__.py
    ├── database.py         # Database queries
    ├── cache.py            # Redis cache
    └── storage.py          # File storage
```

### Entry Point Pattern

The main service file (`crud-item-store.py`) acts as the entry point:

```python
"""
CRUD Item Store Service

Entry point for the item store feature. This file imports and registers
all routers for this service.
"""

from fastapi import APIRouter
from .routers import items, categories

# Create service router
router = APIRouter(prefix="/items", tags=["Items"])

# Include sub-routers
router.include_router(items.router)
router.include_router(categories.router)

__all__ = ["router"]
```

### Layer Responsibilities

#### 1. Routers (`routers/`)

**Purpose:** HTTP request/response handling

```python
from fastapi import APIRouter, Depends
from ..models.item import ItemCreate, ItemResponse
from ..functions.create_item import create_item_logic

router = APIRouter()

@router.post("/", response_model=ItemResponse)
async def create_item(item: ItemCreate):
    """Create a new item."""
    return await create_item_logic(item)
```

**Rules:**
- Thin layer - only handle HTTP concerns
- Validate input with Pydantic models
- Call functions for business logic
- Return proper status codes
- No business logic here

#### 2. Models (`models/`)

**Purpose:** Data structure definitions

```python
from pydantic import BaseModel, Field
from typing import Optional

class ItemCreate(BaseModel):
    """Schema for creating an item."""
    name: str = Field(..., min_length=1, max_length=100)
    price: float = Field(..., gt=0)
    category: str

class ItemResponse(BaseModel):
    """Schema for item responses."""
    id: str
    name: str
    price: float
    category: str
    created_at: datetime
```

**Rules:**
- Use Pydantic for validation
- Separate create/update/response models
- Include field validation rules
- Add docstrings

#### 3. Functions (`functions/`)

**Purpose:** Business logic

```python
from ..models.item import ItemCreate, ItemResponse
from ..services.database import save_item
from app.shared.logger import get_logger

logger = get_logger(__name__)

async def create_item_logic(item: ItemCreate) -> ItemResponse:
    """
    Business logic for creating an item.
    
    Args:
        item: Item data to create
        
    Returns:
        Created item with ID
        
    Raises:
        ValueError: If item validation fails
    """
    # Validate business rules
    if item.price > 10000:
        raise ValueError("Price exceeds maximum")
    
    # Save to database
    created = await save_item(item)
    
    logger.info("Item created", item_id=created.id)
    
    return created
```

**Rules:**
- Pure business logic only
- No HTTP concerns (no status codes, no FastAPI dependencies)
- Testable in isolation
- Raise domain exceptions, not HTTP exceptions
- Log important actions

#### 4. Services (`services/`)

**Purpose:** External system integration

```python
from sqlalchemy import select
from app.shared.database import get_session
from ..models.item import ItemCreate, ItemDB

async def save_item(item: ItemCreate) -> ItemDB:
    """
    Save item to database.
    
    Args:
        item: Item to save
        
    Returns:
        Saved item with generated ID
    """
    async with get_session() as session:
        db_item = ItemDB(**item.dict())
        session.add(db_item)
        await session.commit()
        await session.refresh(db_item)
        return db_item
```

**Rules:**
- Handle external system communication
- Database queries, API calls, file I/O
- Return domain models, not ORM objects
- Handle connection errors gracefully
- Use dependency injection for testability

### Data Flow

```
Request → Router → Function → Service → Database
                      ↓
                  Validation
                      ↓
                Business Logic
                      ↓
Response ← Router ← Result ← Service
```

---

## Why This Architecture?

### Scalability

- Add new features without affecting existing ones
- Each service can be developed by different teams
- Clear boundaries prevent merge conflicts
- Can scale to hundreds of services

### Maintainability

- Easy to find code (consistent structure)
- Changes are localized to specific services
- Shared components are tested once, used everywhere
- New developers onboard quickly

### Testability

- Business logic separated from framework code
- Dependencies can be mocked easily
- Each layer can be tested independently
- Fast test execution

### Team Productivity

- Multiple developers can work in parallel
- Clear ownership of features
- Predictable code organization
- Less time spent searching for code

---

## Summary

The OpenTaberna FastAPI architecture is designed for **long-term success**:

1. **Ruff** ensures code quality automatically
2. **SOLID principles** make code maintainable
3. **Shared components** are built once, used everywhere
4. **Service structure** keeps features isolated and scalable
5. **Testing** is mandatory and built into the workflow

Follow these principles, and the API will scale from 10 to 1000 endpoints without losing maintainability.

**Next Steps:**
- Read [Development Guide](./development.md) for practical workflows
- Read [Logger Documentation](./logger.md) for logging system details
- Read [Testing Guide](./testing.md) for testing practices
