"""
Item CRUD Router

FastAPI router for item CRUD operations.
Provides endpoints for creating, reading, updating, and deleting items.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.admin.dependencies import require_admin
from app.shared.config import get_settings
from app.shared.database.session import get_session_dependency
from app.shared.exceptions import entity_not_found
from app.shared.responses import PaginatedResponse, PageInfo
from ..models import ItemCreate, ItemStatus, ItemUpdate
from ..responses import ItemResponse
from ..responses.item_docs import (
    CREATE_ITEM_RESPONSES,
    GET_ITEM_RESPONSES,
    LIST_ITEMS_RESPONSES,
    GET_ITEM_BY_SKU_RESPONSES,
    UPDATE_ITEM_RESPONSES,
    DELETE_ITEM_RESPONSES,
)
from ..services import get_item_repository
from ..functions.item_images import (
    assert_within_size_limit,
    detect_image_format,
    image_key,
    mime_type,
    public_image_url,
)
from ..functions import (
    db_to_response,
    check_duplicate_field,
    validate_update_conflicts,
    prepare_item_update_data,
)
from app.shared.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()


@router.post(
    "/",
    response_model=ItemResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new item",
    description="Create a new item in the store with all required information.",
    responses=CREATE_ITEM_RESPONSES,
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
        ItemResponse: Created item with UUID and timestamps

    Raises:
        ValidationError (422): If SKU or slug already exists
        RequestValidationError (422): If input data is invalid (wrong types, missing fields, constraint violations)
        DatabaseError (500): If database operation fails
    """
    repo = get_item_repository(session)

    # Check for duplicate SKU and slug using validation function
    await check_duplicate_field(repo, "sku", item.sku)
    await check_duplicate_field(repo, "slug", item.slug)

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
    # Commit before responding. get_session_dependency also commits, but its
    # exit code runs after the response is sent, so a client reading the row
    # straight back can otherwise get a 404 (issue #26).
    await session.commit()
    logger.info("Item created", extra={"uuid": str(created.uuid), "sku": created.sku})
    return db_to_response(created)


@router.get(
    "/{item_uuid}",
    response_model=ItemResponse,
    summary="Get item by UUID",
    description="Retrieve a single item by its UUID.",
    responses=GET_ITEM_RESPONSES,
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
        ItemResponse: Item details

    Raises:
        NotFoundError (404): If item with given UUID does not exist
        RequestValidationError (422): If UUID format is invalid
        DatabaseError (500): If database operation fails
    """
    repo = get_item_repository(session)
    logger.debug("Fetching item", extra={"uuid": str(item_uuid)})
    item = await repo.get(item_uuid)

    if not item:
        raise entity_not_found("Item", item_uuid)

    return db_to_response(item)


@router.get(
    "/",
    response_model=PaginatedResponse[ItemResponse],
    summary="List items",
    description="List items with pagination and optional filtering by status.",
    responses=LIST_ITEMS_RESPONSES,
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
) -> PaginatedResponse[ItemResponse]:
    """
    List items with pagination.

    Args:
        skip: Number of items to skip (must be >= 0)
        limit: Maximum items to return (1-100)
        status_filter: Optional status filter ('draft', 'active', or 'archived')
        session: Database session

    Returns:
        PaginatedResponse[ItemResponse]: Paginated list of items with metadata

    Raises:
        RequestValidationError (422): If skip < 0, limit out of range, or invalid status
        DatabaseError (500): If database operation fails
    """
    repo = get_item_repository(session)
    logger.debug(
        "Listing items",
        extra={
            "skip": skip,
            "limit": limit,
            "status": status_filter.value if status_filter else None,
        },
    )

    # Apply filters
    filters = {}
    if status_filter:
        filters["status"] = status_filter.value

    items = await repo.filter(skip=skip, limit=limit, **filters)
    total = await repo.count(**filters)

    # Calculate pagination metadata
    total_pages = (total + limit - 1) // limit if total > 0 else 0
    page = (skip // limit) + 1

    return PaginatedResponse[ItemResponse](
        success=True,
        items=[db_to_response(item) for item in items],
        page_info=PageInfo(
            page=page,
            size=limit,
            total=total,
            pages=total_pages,
        ),
        message="Items retrieved successfully",
    )


@router.get(
    "/by-sku/{sku}",
    response_model=ItemResponse,
    summary="Get item by SKU",
    description="Retrieve a single item by its SKU (Stock Keeping Unit).",
    responses=GET_ITEM_BY_SKU_RESPONSES,
)
async def get_item_by_sku(
    sku: str,
    session: AsyncSession = Depends(get_session_dependency),
) -> ItemResponse:
    """
    Get item by SKU.

    Args:
        sku: Item SKU (Stock Keeping Unit)
        session: Database session

    Returns:
        ItemResponse: Item details

    Raises:
        NotFoundError (404): If item with given SKU does not exist
        DatabaseError (500): If database operation fails
    """
    repo = get_item_repository(session)
    logger.debug("Fetching item by SKU", extra={"sku": sku})
    item = await repo.get_by(sku=sku)

    if not item:
        raise entity_not_found("Item", sku)

    return db_to_response(item)


@router.patch(
    "/{item_uuid}",
    response_model=ItemResponse,
    summary="Update item",
    description="Update an existing item. Only provided fields will be updated.",
    responses=UPDATE_ITEM_RESPONSES,
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
        item_update: Fields to update (only provided fields will be updated)
        session: Database session

    Returns:
        ItemResponse: Updated item

    Raises:
        NotFoundError (404): If item with given UUID does not exist
        ValidationError (422): If updated SKU or slug conflicts with another item
        RequestValidationError (422): If UUID format or input data is invalid
        DatabaseError (500): If database operation fails
    """
    repo = get_item_repository(session)
    item = await repo.get(item_uuid)

    if not item:
        raise entity_not_found("Item", item_uuid)

    # Get update data, excluding unset fields
    update_data = item_update.model_dump(exclude_unset=True)

    # Validate for conflicts (SKU and slug)
    await validate_update_conflicts(repo, item, update_data, item_uuid)

    # Convert enums and nested models to database format
    update_data = prepare_item_update_data(update_data)

    # Update item
    updated = await repo.update(item_uuid, **update_data)
    # Commit before responding. get_session_dependency also commits, but its
    # exit code runs after the response is sent, so a client reading the row
    # straight back can otherwise get a 404 (issue #26).
    await session.commit()
    logger.info("Item updated", extra={"uuid": str(item_uuid)})
    return db_to_response(updated)


@router.delete(
    "/{item_uuid}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete item",
    description="Permanently delete an item from the store.",
    responses=DELETE_ITEM_RESPONSES,
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
        NotFoundError (404): If item with given UUID does not exist
        RequestValidationError (422): If UUID format is invalid
        DatabaseError (500): If database operation fails
    """
    repo = get_item_repository(session)
    item = await repo.get(item_uuid)

    if not item:
        raise entity_not_found("Item", item_uuid)

    await repo.delete(item_uuid)
    # Commit before responding. get_session_dependency also commits, but its
    # exit code runs after the response is sent, so a client reading the row
    # straight back can otherwise get a 404 (issue #26).
    await session.commit()
    logger.info("Item deleted", extra={"uuid": str(item_uuid)})


# ---------------------------------------------------------------------------
# Product images
# ---------------------------------------------------------------------------


def _storage_adapter():
    """
    Build a storage adapter from application settings.

    Returns:
        Configured MinioStorageAdapter.
    """
    from app.shared.storage.minio_adapter import build_minio_adapter

    settings = get_settings()
    return build_minio_adapter(
        endpoint_url=settings.storage_endpoint_url,
        access_key=settings.storage_access_key,
        secret_key=settings.storage_secret_key,
        region=settings.storage_region,
    )


@router.put(
    "/{item_uuid}/image",
    response_model=ItemResponse,
    summary="Upload the product image (admin)",
    description=(
        "Store the product image in the object store and point the item at it. "
        "Accepts JPEG, PNG, GIF and WebP. One image per item — uploading again "
        "replaces the previous file rather than leaving an orphan behind."
    ),
    dependencies=[Depends(require_admin)],
)
async def upload_item_image(
    item_uuid: UUID,
    file: UploadFile = File(..., description="Image file"),
    session: AsyncSession = Depends(get_session_dependency),
) -> ItemResponse:
    """
    Attach an image to an item.

    Admin-only, unlike the rest of this router: an unauthenticated upload
    endpoint lets anyone fill the object store, and lets them serve chosen
    bytes from our own origin.

    Args:
        item_uuid: Item to attach the image to.
        file:      Uploaded image.
        session:   Database session.

    Returns:
        The updated item, with media.main_image set.

    Raises:
        NotFoundError (404):     If the item does not exist.
        BusinessRuleError (400): If the file is too large or is not an image.
        StorageError (502):      If the object store rejects the upload.
    """
    settings = get_settings()
    repo = get_item_repository(session)

    item = await repo.get(item_uuid)
    if not item:
        raise entity_not_found("Item", item_uuid)

    data = await file.read()
    assert_within_size_limit(data, settings.storage_max_image_bytes)
    # Checked against the bytes rather than the declared Content-Type, which
    # the client controls.
    image_format = detect_image_format(data)

    storage = _storage_adapter()
    bucket = settings.storage_bucket_items
    await storage.ensure_bucket(bucket)
    key = image_key(item_uuid, image_format)
    await storage.upload(
        bucket=bucket, key=key, data=data, content_type=mime_type(image_format)
    )

    media = dict(item.media or {})
    media["main_image"] = public_image_url(item_uuid)
    updated = await repo.update(item_uuid, media=media)
    await session.commit()

    logger.info(
        "Product image stored",
        extra={
            "uuid": str(item_uuid),
            "format": image_format,
            "bytes": len(data),
            "key": key,
        },
    )
    return db_to_response(updated)


@router.get(
    "/{item_uuid}/image",
    summary="Get the product image",
    description=(
        "Return the product image bytes. Public, because the storefront shows "
        "it to shoppers who are not signed in."
    ),
    response_class=Response,
    responses={
        200: {"content": {"image/*": {}}, "description": "The image"},
        404: {"description": "The item has no image"},
    },
)
async def get_item_image(
    item_uuid: UUID,
    session: AsyncSession = Depends(get_session_dependency),
) -> Response:
    """
    Serve an item's image.

    Proxied through the API rather than exposing MinIO, so the object store
    stays private and can be moved without invalidating stored URLs.

    Args:
        item_uuid: Item whose image is wanted.
        session:   Database session.

    Returns:
        The image bytes with its content type.

    Raises:
        NotFoundError (404): If the item or its image does not exist.
    """
    settings = get_settings()
    repo = get_item_repository(session)

    item = await repo.get(item_uuid)
    if not item:
        raise entity_not_found("Item", item_uuid)

    media = item.media or {}
    if not media.get("main_image"):
        raise entity_not_found("Item image", item_uuid)

    storage = _storage_adapter()
    bucket = settings.storage_bucket_items

    # The stored URL does not carry the format, so try each extension. Cheap,
    # and it avoids a second column that could drift from the object store.
    for image_format in ("jpeg", "png", "gif", "webp"):
        key = image_key(item_uuid, image_format)
        try:
            data = await storage.download(bucket=bucket, key=key)
        except Exception:
            continue
        return Response(
            content=data,
            media_type=mime_type(image_format),
            headers={"Cache-Control": "public, max-age=60"},
        )

    raise entity_not_found("Item image", item_uuid)
