"""
Item CRUD Router

FastAPI router for item CRUD operations.
Provides endpoints for creating, reading, updating, and deleting items.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database.session import get_session_dependency
from ..models import (
    ItemCreate,
    ItemListResponse,
    ItemResponse,
    ItemStatus,
    ItemUpdate,
)
from ..services.database import get_item_repository
from ..functions.transformations import db_to_response


router = APIRouter()


@router.post(
    "/",
    response_model=ItemResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new item",
    description="Create a new item in the store with all required information.",
)
async def create_item(
    item: ItemCreate,
    session: AsyncSession = Depends(get_session_dependency),
) -> ItemResponse:
    """
    Create a new item.

    Args:
        item: Item creation data
        session: Database session

    Returns:
        Created item

    Raises:
        HTTPException 400: If SKU or slug already exists
    """
    repo = get_item_repository(session)

    # Check for duplicate SKU
    if await repo.sku_exists(item.sku):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Item with SKU '{item.sku}' already exists",
        )

    # Check for duplicate slug
    if await repo.slug_exists(item.slug):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Item with slug '{item.slug}' already exists",
        )

    # Convert nested Pydantic models to dicts for JSONB storage
    created = await repo.create(
        sku=item.sku,
        status=item.status.value,
        name=item.name,
        slug=item.slug,
        short_description=item.short_description,
        description=item.description,
        categories=[str(cat) for cat in item.categories],
        brand=item.brand,
        price=item.price.model_dump(),
        media=item.media.model_dump(),
        inventory=item.inventory.model_dump(),
        shipping=item.shipping.model_dump(),
        attributes=item.attributes,
        identifiers=item.identifiers.model_dump(),
        custom=item.custom,
        system=item.system.model_dump(),
    )
    return db_to_response(created)


@router.get(
    "/{item_uuid}",
    response_model=ItemResponse,
    summary="Get item by UUID",
    description="Retrieve a single item by its UUID.",
)
async def get_item(
    item_uuid: UUID,
    session: AsyncSession = Depends(get_session_dependency),
) -> ItemResponse:
    """
    Get item by UUID.

    Args:
        item_uuid: Item UUID
        session: Database session

    Returns:
        Item details

    Raises:
        HTTPException 404: If item not found
    """
    repo = get_item_repository(session)
    item = await repo.get(item_uuid)

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Item with UUID '{item_uuid}' not found",
        )

    return db_to_response(item)


@router.get(
    "/",
    response_model=ItemListResponse,
    summary="List items",
    description="List items with pagination and optional filtering by status.",
)
async def list_items(
    skip: int = Query(0, ge=0, description="Number of items to skip"),
    limit: int = Query(
        50, ge=1, le=100, description="Maximum number of items to return"
    ),
    status_filter: ItemStatus | None = Query(
        None, alias="status", description="Filter by status"
    ),
    session: AsyncSession = Depends(get_session_dependency),
) -> ItemListResponse:
    """
    List items with pagination.

    Args:
        skip: Number of items to skip
        limit: Maximum items to return
        status_filter: Optional status filter
        session: Database session

    Returns:
        Paginated list of items
    """
    repo = get_item_repository(session)

    # Apply filters
    filters = {}
    if status_filter:
        filters["status"] = status_filter.value

    items = await repo.get_all(skip=skip, limit=limit, **filters)
    total = await repo.count(**filters)

    # Calculate pagination
    total_pages = (total + limit - 1) // limit if total > 0 else 0
    page = (skip // limit) + 1

    return ItemListResponse(
        items=[db_to_response(item) for item in items],
        total=total,
        page=page,
        page_size=limit,
        total_pages=total_pages,
    )


@router.get(
    "/by-slug/{slug}",
    response_model=ItemResponse,
    summary="Get item by slug",
    description="Retrieve a single item by its URL-friendly slug.",
)
async def get_item_by_slug(
    slug: str,
    session: AsyncSession = Depends(get_session_dependency),
) -> ItemResponse:
    """
    Get item by slug.

    Args:
        slug: Item slug
        session: Database session

    Returns:
        Item details

    Raises:
        HTTPException 404: If item not found
    """
    repo = get_item_repository(session)
    item = await repo.get_by_slug(slug)

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Item with slug '{slug}' not found",
        )

    return db_to_response(item)


@router.patch(
    "/{item_uuid}",
    response_model=ItemResponse,
    summary="Update item",
    description="Update an existing item. Only provided fields will be updated.",
)
async def update_item(
    item_uuid: UUID,
    item_update: ItemUpdate,
    session: AsyncSession = Depends(get_session_dependency),
) -> ItemResponse:
    """
    Update an existing item.

    Args:
        item_uuid: Item UUID
        item_update: Fields to update
        session: Database session

    Returns:
        Updated item

    Raises:
        HTTPException 404: If item not found
        HTTPException 400: If SKU or slug conflicts
    """
    repo = get_item_repository(session)
    item = await repo.get(item_uuid)

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Item with UUID '{item_uuid}' not found",
        )

    # Get update data, excluding unset fields
    update_data = item_update.model_dump(exclude_unset=True)

    # Check for SKU conflicts
    if "sku" in update_data and update_data["sku"] != item.sku:
        if await repo.sku_exists(update_data["sku"], exclude_uuid=item_uuid):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Item with SKU '{update_data['sku']}' already exists",
            )

    # Check for slug conflicts
    if "slug" in update_data and update_data["slug"] != item.slug:
        if await repo.slug_exists(update_data["slug"], exclude_uuid=item_uuid):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Item with slug '{update_data['slug']}' already exists",
            )

    # Convert enums and nested models to appropriate formats
    for key, value in update_data.items():
        if key == "status" and isinstance(value, ItemStatus):
            update_data[key] = value.value
        elif key == "categories" and value is not None:
            update_data[key] = [str(cat) for cat in value]
        elif hasattr(value, "model_dump"):
            update_data[key] = value.model_dump()

    # Update item
    updated = await repo.update(item_uuid, **update_data)
    return db_to_response(updated)


@router.delete(
    "/{item_uuid}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete item",
    description="Permanently delete an item from the store.",
)
async def delete_item(
    item_uuid: UUID,
    session: AsyncSession = Depends(get_session_dependency),
) -> None:
    """
    Delete an item.

    Args:
        item_uuid: Item UUID
        session: Database session

    Raises:
        HTTPException 404: If item not found
    """
    repo = get_item_repository(session)
    item = await repo.get(item_uuid)

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Item with UUID '{item_uuid}' not found",
        )

    await repo.delete(item_uuid)
