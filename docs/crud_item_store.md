# CRUD Item Store Service Documentation

## Overview

The **crud-item-store** service provides CRUD operations for managing store items with self-contained models, business logic, and API endpoints.

## Architecture

```
src/app/services/crud-item-store/
├── __init__.py                # Service entry point & router exports
├── models/
│   ├── __init__.py            # Model exports
│   ├── item.py                # Pydantic data models (ItemBase, ItemCreate, ItemUpdate)
│   └── database.py            # SQLAlchemy ORM model
├── responses/
│   ├── __init__.py            # Response model exports
│   └── items.py               # API response schemas (ItemResponse)
├── routers/
│   ├── __init__.py            # Router exports
│   └── items.py               # CRUD API endpoints
├── services/
│   ├── __init__.py            # Service exports
│   └── database.py            # Database repository layer
└── functions/
    ├── __init__.py            # Function exports
    ├── transformations.py     # Data transformation functions
    └── validation.py          # Validation functions
```

---

## Pydantic Models

### Data Models (`models/item.py`)

#### `ItemBase`
Base schema with all core item fields (shared by Create, Update, Response).

#### `ItemCreate`
Schema for creating new items. All fields from `ItemBase` are required except those with defaults.

#### `ItemUpdate`
Schema for updating items. All fields are optional - only provided fields will be updated.

### Response Models (`responses/items.py`)

#### `ItemResponse`
API response schema including `uuid`, `created_at`, and `updated_at` timestamps. Extends `ItemBase` with database-generated fields.

**Note:** List endpoints use shared `PaginatedResponse[ItemResponse]` with `success`, `items`, `page_info`, `message`, and `timestamp` fields.

### Nested Models

`PriceModel`, `MediaModel`, `InventoryModel`, `ShippingModel`, `WeightModel`, `DimensionsModel`, `IdentifiersModel`, `SystemModel`

### Enums

`ItemStatus`, `StockStatus`, `TaxClass`, `ShippingClass`, `WeightUnit`, `DimensionUnit`

---

## Database Model

### `ItemDB` (SQLAlchemy)

Stored in PostgreSQL with optimized structure:

**Columns** (indexed for queries):
- `uuid`: Primary key (UUID)
- `sku`: Unique stock keeping unit (indexed)
- `status`: Item status (indexed)
- `name`: Display name (indexed)
- `slug`: URL-friendly identifier (unique, indexed)
- `short_description`: Brief text
- `description`: Full text/HTML
- `brand`: Brand name (indexed)

**JSONB Fields** (for complex nested data):
- `categories`: Array of category UUIDs
- `price`: Price information object
- `media`: Media assets object
- `inventory`: Inventory data object
- `shipping`: Shipping information object
- `attributes`: Custom key-value pairs
- `identifiers`: Product codes object
- `custom`: Extensible plugin data
- `system`: System metadata

**Timestamps**: `created_at`, `updated_at` (auto-managed via `TimestampMixin`)

---

## Repository Layer

### `ItemRepository` (`services/database.py`)

Extends `BaseRepository[ItemDB]` with item-specific methods:

#### Basic CRUD (inherited from BaseRepository)
- `create(**fields)`: Create new item
- `get(uuid)`: Get by UUID
- `update(uuid, **fields)`: Update item
- `delete(uuid)`: Delete item
- `get_all(skip, limit, **filters)`: List with pagination
- `count(**filters)`: Count items
- `get_by(**filters)`: Get single item by field(s)

#### Item-Specific Queries
- `get_by_sku(sku)`: Find by SKU
- `get_by_slug(slug)`: Find by URL slug
- `search(name, status, category_uuid, brand, skip, limit)`: Generic search with multiple optional criteria (AND logic)
- `field_exists(field_name, field_value, exclude_uuid)`: Generic field existence check

---

## API Endpoints

Base path: `/v1/items`

- `POST /items/` - Create item (201 Created)
- `GET /items/{uuid}` - Get by UUID (200 OK / 404 Not Found)
- `GET /items/by-slug/{slug}` - Get by slug (200 OK / 404 Not Found)
- `GET /items/?skip=0&limit=50&status=active` - List with pagination (200 OK)
- `PATCH /items/{uuid}` - Update item (200 OK / 404 Not Found)
- `DELETE /items/{uuid}` - Delete item (204 No Content / 404 Not Found)

**Validations:** SKU and slug uniqueness, currency codes (3 chars), non-negative amounts



---

## Integration

### Shared Module Integration

- **Exceptions**: `entity_not_found()`, `duplicate_entry()` → standardized error responses
- **Responses**: `PaginatedResponse[ItemResponse]`, `ErrorResponse` → consistent API format
- **Database**: `get_session_dependency`, `BaseRepository` → session management and base CRUD

### Register in Main App

In `src/app/main.py`:

```python
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from app.chore import lifespan
from app.services.crud_item_store import router as item_store_router
from app.shared.exceptions import AppException
from app.shared.responses import ErrorResponse

app = FastAPI(title="OpenTaberna API", lifespan=lifespan)

# Global exception handler for standardized error responses
@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    error_response = ErrorResponse.from_exception(exc)
    return JSONResponse(
        status_code=error_response.status_code,
        content=error_response.model_dump(mode="json")
    )

# Include the item store router
app.include_router(item_store_router, prefix="/v1")
```

### Create Database Migration

```bash
alembic revision --autogenerate -m "create_items_table"
alembic upgrade head
```

---

## Validation

**Automatic (Pydantic):** SKU/slug uniqueness, currency codes, non-negative amounts, URL formats

**Business Logic (`functions/validation.py`):**
- `check_duplicate_field(repo, field_name, field_value, exclude_uuid)` - Generic uniqueness validation for any model field

---

## Functions Layer

**Transformations (`functions/transformations.py`):**
- `db_to_response(item_db)` - Converts SQLAlchemy models to Pydantic responses

**Validation (`functions/validation.py`):**
- `check_duplicate_field(repo, field_name, value, exclude_uuid)` - Generic uniqueness check



---

## Performance

**Indexes:** `uuid` (PK), `sku` (unique), `slug` (unique), `status`, `name`, `brand`

**Recommended GIN indexes for JSONB:** `price`, `categories`, `attributes`

**Pagination:** Max limit 100, default 50

---

## Error Handling

**Status Codes:** 200 (OK), 201 (Created), 204 (No Content), 404 (Not Found), 422 (Validation), 500 (Server Error)

**Format:** Standardized `ErrorResponse` with `success`, `error` (code, message, category), and `timestamp`

**Helpers:** `entity_not_found()` → 404, `duplicate_entry()` → 422



---

## Summary

**Features:**
- Complete CRUD operations with PostgreSQL JSONB storage
- Type-safe Pydantic models with nested structures
- Repository pattern with generic search and validation
- Shared exception/response system integration
- Pagination, error handling, and proper indexing

**Architecture:**
- `models/` - Data models (Pydantic)
- `responses/` - API responses
- `functions/` - Business logic
- `services/` - Database operations
- `routers/` - HTTP endpoints