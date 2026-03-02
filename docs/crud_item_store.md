# CRUD Item Store Service Documentation

## Overview

The **crud-item-store** service is a complete mini-API for managing store items in an e-commerce system. It follows the OpenTaberna architecture pattern with self-contained models, business logic, and API endpoints.

## Architecture

```
src/app/services/crud-item-store/
├── crud-item-store.py          # Service entry point & router registration
├── models/
│   ├── __init__.py            # Model exports
│   ├── item.py                # Pydantic models for validation
│   └── database.py            # SQLAlchemy ORM model
├── routers/
│   ├── __init__.py            # Router exports
│   └── items.py               # CRUD API endpoints
├── services/
│   ├── __init__.py            # Service exports
│   └── database.py            # Database repository layer
└── functions/
    └── __init__.py            # Business logic functions (to be added)
```

---

## Data Model

### Item Structure

Each item contains comprehensive product information:

```json
{
  "uuid": "0b9e2c50-5e3b-4cc1-9a6a-2b3e9a0b1234",
  "sku": "CHAIR-RED-001",
  "status": "active",
  "name": "Red Wooden Chair",
  "slug": "red-wooden-chair",
  "short_description": "Comfortable red wooden chair",
  "description": "Full HTML/Markdown description...",
  "categories": ["2f61e8db-bb70-4b22-9aa0-4d7fa3b7aa11"],
  "brand": "Acme Furniture",
  "price": {
    "amount": 9999,
    "currency": "EUR",
    "includes_tax": true,
    "original_amount": 12999,
    "tax_class": "standard"
  },
  "media": {
    "main_image": "https://cdn.example.com/chair-main.jpg",
    "gallery": ["https://cdn.example.com/chair-side.jpg"]
  },
  "inventory": {
    "stock_quantity": 25,
    "stock_status": "in_stock",
    "allow_backorder": false
  },
  "shipping": {
    "is_physical": true,
    "weight": {"value": 7.5, "unit": "kg"},
    "dimensions": {
      "width": 45.0,
      "height": 90.0,
      "length": 50.0,
      "unit": "cm"
    },
    "shipping_class": "standard"
  },
  "attributes": {
    "color": "red",
    "material": "wood"
  },
  "identifiers": {
    "barcode": "4006381333931",
    "manufacturer_part_number": "AC-CHAIR-RED-01",
    "country_of_origin": "DE"
  },
  "custom": {},
  "system": {
    "log_table": "uuid_reference"
  },
  "created_at": "2026-03-02T10:00:00Z",
  "updated_at": "2026-03-02T10:00:00Z"
}
```

---

## Pydantic Models

### Core Models

#### `ItemCreate`
Schema for creating new items. All fields from `ItemBase` are required except those with defaults.

#### `ItemUpdate`
Schema for updating items. All fields are optional - only provided fields will be updated.

#### `ItemResponse`
Response schema including `uuid`, `created_at`, and `updated_at` timestamps.

#### `ItemListResponse`
Paginated list response with metadata:
- `items`: List of items
- `total`: Total item count
- `page`: Current page number
- `page_size`: Items per page
- `total_pages`: Total number of pages

### Nested Models

- **`PriceModel`**: Price information with currency, tax, and discounts
- **`MediaModel`**: Main image and gallery images
- **`InventoryModel`**: Stock quantity, status, and backorder settings
- **`ShippingModel`**: Physical shipping details (weight, dimensions, class)
- **`WeightModel`**: Weight value and unit (kg, lb, g)
- **`DimensionsModel`**: Width, height, length, and unit (cm, m, in, ft)
- **`IdentifiersModel`**: Barcode, MPN, country of origin
- **`SystemModel`**: System-level metadata

### Enums

- **`ItemStatus`**: `draft`, `active`, `archived`
- **`StockStatus`**: `in_stock`, `out_of_stock`, `preorder`, `backorder`
- **`TaxClass`**: `standard`, `reduced`, `none`
- **`ShippingClass`**: `standard`, `bulky`, `letter`
- **`WeightUnit`**: `kg`, `lb`, `g`
- **`DimensionUnit`**: `cm`, `m`, `in`, `ft`

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

**Timestamps** (via `TimestampMixin`):
- `created_at`: Auto-set on creation
- `updated_at`: Auto-updated on changes

### Why JSONB?

PostgreSQL JSONB provides:
- Efficient storage of nested structures
- Indexable with GIN indexes
- Queryable with JSON operators
- Schema flexibility for custom fields

---

## Repository Layer

### `ItemRepository`

Extends `BaseRepository[ItemDB]` with item-specific methods:

#### Basic CRUD
- `create(item)`: Create new item
- `get(uuid)`: Get by UUID
- `update(item, **fields)`: Update item
- `delete(item)`: Delete item
- `get_all(skip, limit, **filters)`: List with pagination
- `count(**filters)`: Count items

#### Item-Specific Queries
- `get_by_sku(sku)`: Find by SKU
- `get_by_slug(slug)`: Find by URL slug
- `get_by_status(status, skip, limit)`: Filter by status
- `get_by_category(uuid, skip, limit)`: Filter by category
- `search_by_name(query, limit)`: Case-insensitive name search

#### Validation
- `sku_exists(sku, exclude_uuid)`: Check SKU uniqueness
- `slug_exists(slug, exclude_uuid)`: Check slug uniqueness

---

## API Endpoints

Base path: `/api/v1/items`

### Create Item
```http
POST /api/v1/items/
Content-Type: application/json

{
  "sku": "CHAIR-RED-001",
  "name": "Red Wooden Chair",
  "slug": "red-wooden-chair",
  "status": "draft",
  "price": {
    "amount": 9999,
    "currency": "EUR"
  }
}
```

**Response:** `201 Created` with full item data

**Validations:**
- SKU must be unique
- Slug must be unique
- Currency code validated (3 chars, uppercase)
- Amounts must be non-negative

### Get Item by UUID
```http
GET /api/v1/items/{uuid}
```

**Response:** `200 OK` with item data  
**Error:** `404 Not Found` if item doesn't exist

### Get Item by Slug
```http
GET /api/v1/items/by-slug/{slug}
```

**Response:** `200 OK` with item data  
**Error:** `404 Not Found` if slug doesn't exist

### List Items
```http
GET /api/v1/items/?skip=0&limit=50&status=active
```

**Query Parameters:**
- `skip`: Offset for pagination (default: 0)
- `limit`: Max items to return (1-100, default: 50)
- `status`: Filter by status (optional)

**Response:** `200 OK` with paginated list
```json
{
  "items": [...],
  "total": 150,
  "page": 1,
  "page_size": 50,
  "total_pages": 3
}
```

### Update Item
```http
PATCH /api/v1/items/{uuid}
Content-Type: application/json

{
  "name": "Updated Name",
  "price": {
    "amount": 8999,
    "currency": "EUR"
  }
}
```

**Response:** `200 OK` with updated item  
**Validations:**
- SKU uniqueness (if changed)
- Slug uniqueness (if changed)

**Note:** Only provided fields are updated (partial update)

### Delete Item
```http
DELETE /api/v1/items/{uuid}
```

**Response:** `204 No Content`  
**Error:** `404 Not Found` if item doesn't exist

---

## Usage Examples

### Creating an Item

```python
from app.services.crud_item_store.models import ItemCreate, PriceModel

item_data = ItemCreate(
    sku="CHAIR-RED-001",
    name="Red Wooden Chair",
    slug="red-wooden-chair",
    status=ItemStatus.ACTIVE,
    short_description="Comfortable dining chair",
    price=PriceModel(
        amount=9999,
        currency="EUR",
        includes_tax=True
    ),
    brand="Acme Furniture"
)

# Via API
response = await client.post("/api/v1/items/", json=item_data.model_dump())
```

### Querying Items

```python
from app.services.crud_item_store.services.database import ItemRepository

async def get_active_items(session: AsyncSession):
    repo = ItemRepository(session)
    
    # Get by SKU
    item = await repo.get_by_sku("CHAIR-RED-001")
    
    # Search by name
    results = await repo.search_by_name("chair")
    
    # Get by category
    items = await repo.get_by_category(category_uuid)
    
    return items
```

### Using in FastAPI

```python
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.shared.database.session import get_session
from app.services.crud_item_store.services.database import ItemRepository

@router.get("/my-custom-endpoint")
async def custom_endpoint(session: AsyncSession = Depends(get_session)):
    repo = ItemRepository(session)
    items = await repo.get_by_status("active")
    return items
```

---

## Integration

### 1. Register in Main App

In `src/app/main.py`:

```python
from fastapi import FastAPI
from app.services.crud_item_store import crud_item_store

app = FastAPI(title="OpenTaberna API")

# Include the item store router
app.include_router(crud_item_store.router, prefix="/api/v1")
```

### 2. Create Database Migration

```bash
# Generate migration
alembic revision --autogenerate -m "create_items_table"

# Apply migration
alembic upgrade head
```

### 3. Add Indexes (Optional)

For better JSONB query performance, add GIN indexes in migration:

```python
# In migration file
def upgrade():
    op.execute("""
        CREATE INDEX idx_items_price ON items USING GIN (price);
        CREATE INDEX idx_items_categories ON items USING GIN (categories);
        CREATE INDEX idx_items_attributes ON items USING GIN (attributes);
    """)
```

---

## Validation Rules

### Automatic Validations

- **SKU**: Unique, 1-100 characters
- **Slug**: Unique, lowercase, URL-friendly
- **Currency**: 3-character ISO code (uppercase)
- **Country Code**: 2-character ISO code (uppercase)
- **Amounts**: Non-negative integers
- **Dimensions/Weight**: Positive values
- **Email/URL formats**: Validated by Pydantic

### Business Rules (To Implement)

Consider adding in `functions/` directory:

- Stock validation (prevent negative inventory)
- Price change limits (max discount percentage)
- Status transitions (draft → active → archived)
- Category validation (check category exists)
- SKU format enforcement (pattern matching)

---

## Testing

### Unit Tests (To Be Created)

```python
# tests/test_crud_item_store.py

async def test_create_item(session):
    repo = ItemRepository(session)
    item_data = ItemDB(
        sku="TEST-001",
        name="Test Item",
        slug="test-item",
        price={"amount": 1000, "currency": "EUR"}
    )
    created = await repo.create(item_data)
    assert created.uuid is not None
    assert created.sku == "TEST-001"

async def test_sku_uniqueness(session):
    repo = ItemRepository(session)
    # Create first item
    await repo.create(ItemDB(sku="DUP-001", ...))
    
    # Verify duplicate check
    assert await repo.sku_exists("DUP-001") is True
```

### Integration Tests

```python
async def test_create_item_endpoint(client):
    response = await client.post("/api/v1/items/", json={
        "sku": "CHAIR-001",
        "name": "Chair",
        "slug": "chair",
        "price": {"amount": 5000, "currency": "EUR"}
    })
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "CHAIR-001"
```

---

## Extension Points

### Adding Custom Functions

Create business logic in `functions/`:

```python
# functions/validate_item.py

async def validate_item_business_rules(item: ItemCreate) -> None:
    """Custom validation logic."""
    if item.price.amount < 100:
        raise ValueError("Minimum price is €1.00")
    
    if item.status == ItemStatus.ACTIVE and not item.media.main_image:
        raise ValueError("Active items require a main image")
```

### Adding Custom Endpoints

Extend the router in `routers/items.py`:

```python
@router.post("/bulk-create")
async def bulk_create_items(items: list[ItemCreate], ...):
    """Create multiple items at once."""
    # Implementation
```

### Plugin System

Use the `custom` field for plugin data:

```python
item.custom = {
    "seo_plugin": {"meta_title": "...", "meta_description": "..."},
    "reviews_plugin": {"average_rating": 4.5}
}
```

---

## Performance Considerations

### Database Indexes

Current indexes on:
- `uuid` (primary key)
- `sku` (unique)
- `slug` (unique)
- `status`
- `name`
- `brand`

**Recommended GIN indexes for JSONB:**
```sql
CREATE INDEX idx_items_price ON items USING GIN (price);
CREATE INDEX idx_items_categories ON items USING GIN (categories);
```

### Query Optimization

```python
# Good: Specific filters
items = await repo.get_all(limit=20, status="active")

# Better: Use specific methods
item = await repo.get_by_slug("product-slug")  # Uses unique index

# Good: JSONB queries (with GIN index)
SELECT * FROM items WHERE categories @> '["uuid"]'::jsonb;
```

### Pagination

Always use pagination for lists:
```python
# Default: 50 items max
await repo.get_all(skip=0, limit=50)

# API enforces max limit of 100
```

---

## Error Handling

The service uses standard HTTP status codes:

- **200 OK**: Successful GET/PATCH
- **201 Created**: Successful POST
- **204 No Content**: Successful DELETE
- **400 Bad Request**: Validation errors, duplicate SKU/slug
- **404 Not Found**: Item doesn't exist
- **422 Unprocessable Entity**: Pydantic validation errors
- **500 Internal Server Error**: Database or server errors

Example error response:
```json
{
  "detail": "Item with SKU 'CHAIR-001' already exists"
}
```

---

## Future Enhancements

### Planned Features

1. **Full-text Search**: PostgreSQL FTS or Elasticsearch integration
2. **Bulk Operations**: Create/update/delete multiple items
3. **Version History**: Track item changes over time
4. **Soft Delete**: Archive instead of hard delete
5. **Stock Alerts**: Low inventory notifications
6. **Price History**: Track price changes
7. **Image Processing**: Automatic resize/optimization
8. **Category Management**: Separate category endpoints
9. **Advanced Filtering**: Complex queries (price ranges, multi-category)
10. **Export/Import**: CSV/JSON bulk operations

### Scalability

For high-traffic scenarios:
- Add Redis caching for frequently accessed items
- Implement read replicas for GET operations
- Use background tasks for image processing
- Add rate limiting on endpoints
- Implement database connection pooling

---

## Dependencies

All dependencies are in `pyproject.toml`:

- **FastAPI**: Web framework
- **Pydantic**: Data validation
- **SQLAlchemy**: ORM with async support
- **asyncpg**: PostgreSQL driver
- **Alembic**: Database migrations
- **PostgreSQL**: Database (with JSONB support)

---

## Summary

The crud-item-store service provides:

✅ **Complete CRUD operations** for store items  
✅ **Rich data model** with nested structures  
✅ **Type-safe** Pydantic validation  
✅ **Efficient storage** with PostgreSQL JSONB  
✅ **Extensible architecture** following SOLID principles  
✅ **RESTful API** with proper HTTP semantics  
✅ **Repository pattern** for database abstraction  
✅ **Ready for production** with proper indexing and validation

The service is self-contained, testable, and ready to be integrated into the main FastAPI application.
