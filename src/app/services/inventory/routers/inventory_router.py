"""
Inventory Router

FastAPI router for inventory management endpoints:

    POST   /admin/inventory              — Create an inventory record for a SKU
    GET    /admin/inventory              — List all inventory items (paginated)
    GET    /admin/inventory/by-sku/{sku} — Get inventory item by SKU
    GET    /admin/inventory/{id}         — Get inventory item by UUID
    PATCH  /admin/inventory/{id}         — Update on_hand stock count
    DELETE /admin/inventory/{id}         — Remove an inventory record

Route order: by-sku is declared BEFORE /{inventory_id} so FastAPI does not
attempt to parse the literal string "by-sku" as a UUID path parameter.

All endpoints require the X-Admin-Key header (dev shim — replaced by
Keycloak role=admin check in production).
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database.session import get_session_dependency
from app.shared.exceptions import access_denied, entity_not_found
from app.shared.logger import get_logger
from app.shared.responses import PaginatedResponse, PageInfo

from ..models import InventoryItemCreate, InventoryItemResponse, InventoryItemUpdate
from ..responses import (
    CREATE_INVENTORY_RESPONSES,
    DELETE_INVENTORY_RESPONSES,
    GET_INVENTORY_BY_SKU_RESPONSES,
    GET_INVENTORY_RESPONSES,
    LIST_INVENTORY_RESPONSES,
    UPDATE_INVENTORY_RESPONSES,
)
from ..services import get_inventory_repository

logger = get_logger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Admin guard
# ---------------------------------------------------------------------------
# TODO: Replace with real Keycloak role=admin dependency once auth is wired up.


async def require_admin(
    x_admin_key: str | None = Header(
        default=None,
        alias="X-Admin-Key",
        description="[Dev-only] Admin access token. Replaced by Keycloak role=admin check in production.",
    ),
) -> None:
    """
    Enforce admin access on every inventory endpoint.

    Development shim: accepts any non-empty X-Admin-Key header value.
    Production TODO: validate a Keycloak JWT with role=admin claim.

    Raises:
        AuthorizationError (403): When the header is absent.
    """
    if x_admin_key is None:
        logger.warning("Admin access attempted without credentials")
        raise access_denied(
            resource="admin/inventory",
            action="access",
            message="Admin access required. Provide X-Admin-Key header (dev) or valid admin JWT (production).",
        )


# ---------------------------------------------------------------------------
# POST /admin/inventory — Create inventory record
# ---------------------------------------------------------------------------


@router.post(
    "/",
    response_model=InventoryItemResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create inventory record (admin)",
    description=(
        "Create a new inventory tracking record for a SKU. "
        "Each SKU may only have one inventory record. "
        "`reserved` always starts at 0 — it is managed automatically by the checkout flow."
    ),
    dependencies=[Depends(require_admin)],
    responses=CREATE_INVENTORY_RESPONSES,
)
async def create_inventory_item(
    payload: InventoryItemCreate,
    session: AsyncSession = Depends(get_session_dependency),
) -> InventoryItemResponse:
    """
    Create a new inventory item record.

    Args:
        payload: InventoryItemCreate with sku and on_hand count.
        session: Database session.

    Returns:
        InventoryItemResponse of the created record.

    Raises:
        ValidationError (422): If a record for this SKU already exists.
        DatabaseError (500):   If a database operation fails.
    """
    repo = get_inventory_repository(session)
    item = await repo.create_inventory_item(sku=payload.sku, on_hand=payload.on_hand)
    await session.commit()
    logger.info(
        "Inventory item created",
        extra={"inventory_id": str(item.id), "sku": item.sku, "on_hand": item.on_hand},
    )
    return InventoryItemResponse.model_validate(item)


# ---------------------------------------------------------------------------
# GET /admin/inventory/by-sku/{sku} — Get by SKU
# NOTE: Must be declared BEFORE /{inventory_id} to avoid UUID parse attempt.
# ---------------------------------------------------------------------------


@router.get(
    "/by-sku/{sku}",
    response_model=InventoryItemResponse,
    summary="Get inventory item by SKU (admin)",
    description="Retrieve the inventory record for a specific SKU.",
    dependencies=[Depends(require_admin)],
    responses=GET_INVENTORY_BY_SKU_RESPONSES,
)
async def get_inventory_by_sku(
    sku: str,
    session: AsyncSession = Depends(get_session_dependency),
) -> InventoryItemResponse:
    """
    Get an inventory item by its SKU.

    Args:
        sku:     SKU string (path parameter).
        session: Database session.

    Returns:
        InventoryItemResponse for the given SKU.

    Raises:
        NotFoundError (404): If no inventory record exists for this SKU.
        DatabaseError (500): If a database operation fails.
    """
    repo = get_inventory_repository(session)
    item = await repo.get_by(sku=sku)
    if not item:
        raise entity_not_found("InventoryItem", sku)

    return InventoryItemResponse.model_validate(item)


# ---------------------------------------------------------------------------
# GET /admin/inventory — List inventory items
# ---------------------------------------------------------------------------


@router.get(
    "/",
    response_model=PaginatedResponse[InventoryItemResponse],
    summary="List inventory items (admin)",
    description=(
        "Return a paginated list of all inventory records. "
        "Use `skip` and `limit` for pagination."
    ),
    dependencies=[Depends(require_admin)],
    responses=LIST_INVENTORY_RESPONSES,
)
async def list_inventory_items(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(
        50, ge=1, le=200, description="Maximum number of records to return"
    ),
    session: AsyncSession = Depends(get_session_dependency),
) -> PaginatedResponse[InventoryItemResponse]:
    """
    Return a paginated list of all inventory items.

    Args:
        skip:    Pagination offset (default 0).
        limit:   Page size (default 50, max 200).
        session: Database session.

    Returns:
        PaginatedResponse[InventoryItemResponse] with page metadata.

    Raises:
        DatabaseError (500): If a database operation fails.
    """
    repo = get_inventory_repository(session)
    items = await repo.filter(skip=skip, limit=limit)
    total = await repo.count()
    total_pages = (total + limit - 1) // limit if total > 0 else 0
    page = (skip // limit) + 1
    logger.debug(
        "Inventory items listed",
        extra={"skip": skip, "limit": limit, "count": len(items)},
    )
    return PaginatedResponse[InventoryItemResponse](
        success=True,
        items=[InventoryItemResponse.model_validate(item) for item in items],
        page_info=PageInfo(page=page, size=limit, total=total, pages=total_pages),
        message="Inventory items retrieved successfully",
    )


# ---------------------------------------------------------------------------
# GET /admin/inventory/{id} — Get by UUID
# ---------------------------------------------------------------------------


@router.get(
    "/{inventory_id}",
    response_model=InventoryItemResponse,
    summary="Get inventory item by UUID (admin)",
    description="Retrieve a single inventory record by its UUID.",
    dependencies=[Depends(require_admin)],
    responses=GET_INVENTORY_RESPONSES,
)
async def get_inventory_item(
    inventory_id: UUID,
    session: AsyncSession = Depends(get_session_dependency),
) -> InventoryItemResponse:
    """
    Get an inventory item by UUID.

    Args:
        inventory_id: UUID of the inventory record (path parameter).
        session:      Database session.

    Returns:
        InventoryItemResponse for the given UUID.

    Raises:
        NotFoundError (404):          If no record exists with that UUID.
        RequestValidationError (422): If the UUID format is invalid.
        DatabaseError (500):          If a database operation fails.
    """
    repo = get_inventory_repository(session)
    item = await repo.get(inventory_id)
    if not item:
        raise entity_not_found("InventoryItem", inventory_id)

    return InventoryItemResponse.model_validate(item)


# ---------------------------------------------------------------------------
# PATCH /admin/inventory/{id} — Update on_hand stock
# ---------------------------------------------------------------------------


@router.patch(
    "/{inventory_id}",
    response_model=InventoryItemResponse,
    summary="Update inventory stock (admin)",
    description=(
        "Update the `on_hand` stock count for an inventory record. "
        "The new `on_hand` value must not be less than `reserved` "
        "(units currently locked by active checkout sessions). "
        "`reserved` cannot be set directly — it is managed by the checkout flow."
    ),
    dependencies=[Depends(require_admin)],
    responses=UPDATE_INVENTORY_RESPONSES,
)
async def update_inventory_item(
    inventory_id: UUID,
    payload: InventoryItemUpdate,
    session: AsyncSession = Depends(get_session_dependency),
) -> InventoryItemResponse:
    """
    Update the on_hand stock count for an inventory item.

    Args:
        inventory_id: UUID of the inventory record (path parameter).
        payload:      InventoryItemUpdate with the new on_hand value.
        session:      Database session.

    Returns:
        Updated InventoryItemResponse.

    Raises:
        NotFoundError (404):          If no record exists with that UUID.
        BusinessRuleError (400):      If new on_hand < current reserved.
        RequestValidationError (422): If UUID format or input data is invalid.
        DatabaseError (500):          If a database operation fails.
    """
    repo = get_inventory_repository(session)
    update_data = payload.model_dump(exclude_unset=True)
    item = await repo.update_stock(inventory_id, update_data)
    if not item:
        raise entity_not_found("InventoryItem", inventory_id)
    await session.commit()
    logger.info(
        "Inventory item updated",
        extra={"inventory_id": str(inventory_id), "update_data": update_data},
    )
    return InventoryItemResponse.model_validate(item)


# ---------------------------------------------------------------------------
# DELETE /admin/inventory/{id} — Remove inventory record
# ---------------------------------------------------------------------------


@router.delete(
    "/{inventory_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete inventory record (admin)",
    description=(
        "Permanently remove an inventory record. "
        "Only safe when the SKU has no active stock reservations "
        "(the DB will reject the delete otherwise)."
    ),
    dependencies=[Depends(require_admin)],
    responses=DELETE_INVENTORY_RESPONSES,
)
async def delete_inventory_item(
    inventory_id: UUID,
    session: AsyncSession = Depends(get_session_dependency),
) -> None:
    """
    Delete an inventory item record.

    Args:
        inventory_id: UUID of the inventory record (path parameter).
        session:      Database session.

    Raises:
        NotFoundError (404):          If no record exists with that UUID.
        RequestValidationError (422): If the UUID format is invalid.
        DatabaseError (500):          If a database operation fails (e.g. active reservations block deletion).
    """
    repo = get_inventory_repository(session)
    deleted = await repo.delete(inventory_id)
    if not deleted:
        raise entity_not_found("InventoryItem", inventory_id)
    await session.commit()
    logger.info("Inventory item deleted", extra={"inventory_id": str(inventory_id)})
