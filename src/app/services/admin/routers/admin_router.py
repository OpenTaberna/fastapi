"""
Admin Router

FastAPI router for admin order management endpoints (Phase 2):

    GET    /admin/orders                    — Paginated order list with optional status filter
    GET    /admin/orders/pick-list          — Aggregated pick list over all PAID orders
    GET    /admin/orders/{id}               — Full order detail with customer, payment, shipment
    PATCH  /admin/orders/{id}/status        — Manual status override with audit log
    GET    /admin/orders/{id}/packing-slip  — Printable HTML packing slip
    POST   /admin/orders/{id}/shipments     — Create shipment → order READY_TO_SHIP
    POST   /admin/orders/{id}/ship          — Mark order SHIPPED + send tracking email

Route order matters: pick-list is declared BEFORE {id} so FastAPI does not
attempt to parse the literal string "pick-list" as a UUID path parameter.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, status
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.orders.models.orders_models import OrderStatus
from app.services.orders.services.orders_db_service import get_order_item_repository
from app.shared.config import get_settings
from app.shared.config.settings import Settings
from app.shared.database.session import get_session_dependency
from app.shared.exceptions import entity_not_found
from app.shared.logger import get_logger

from ..dependencies import require_admin
from ..functions import (
    OrderContext,
    build_pick_list,
    create_shipment,
    db_to_admin_order_detail_response,
    db_to_order_response,
    fetch_order_context,
    mark_order_shipped,
    render_packing_slip,
    render_pick_list_html,
    send_tracking_email,
)
from ..models import (
    AdminCreateShipmentRequest,
    AdminOrderDetailResponse,
    AdminOrderListResponse,
    AdminStatusOverrideRequest,
    PickListResponse,
)
from ..responses import (
    CREATE_SHIPMENT_RESPONSES,
    GET_ORDER_DETAIL_RESPONSES,
    LIST_ORDERS_RESPONSES,
    PACKING_SLIP_RESPONSES,
    PICK_LIST_RESPONSES,
    SHIP_ORDER_RESPONSES,
    STATUS_OVERRIDE_RESPONSES,
)
from ..services import get_admin_order_repository

logger = get_logger(__name__)

router = APIRouter()

# Maximum number of PAID orders included in a single pick-list render.
# Adjust upward if the warehouse processes batches larger than this.
_PICK_LIST_MAX_ORDERS = 10_000


# ---------------------------------------------------------------------------
# GET /admin/orders — Paginated order list
# ---------------------------------------------------------------------------


@router.get(
    "/",
    response_model=AdminOrderListResponse,
    summary="List all orders (admin)",
    description=(
        "Return a paginated list of all orders across all customers. "
        "Optionally filter by `status`. Soft-deleted orders are excluded."
    ),
    dependencies=[Depends(require_admin)],
    responses=LIST_ORDERS_RESPONSES,
)
async def list_orders(
    status: OrderStatus | None = None,
    skip: int = 0,
    limit: int = 50,
    session: AsyncSession = Depends(get_session_dependency),
) -> AdminOrderListResponse:
    """
    Return a paginated, optionally status-filtered list of all orders.

    Args:
        status:  Optional OrderStatus filter.
        skip:    Pagination offset (default 0).
        limit:   Page size (default 50).
        session: Database session.

    Returns:
        AdminOrderListResponse with orders, total count, skip, and limit.
    """
    repo = get_admin_order_repository(session)

    orders = await repo.list_orders(status=status, skip=skip, limit=limit)
    total = await repo.count_orders(status=status)

    logger.info(
        "Admin listed orders",
        extra={
            "status": status.value if status else None,
            "total": total,
            "skip": skip,
            "limit": limit,
        },
    )
    return AdminOrderListResponse(
        orders=[db_to_order_response(o) for o in orders],
        total=total,
        skip=skip,
        limit=limit,
    )


# ---------------------------------------------------------------------------
# GET /admin/orders/pick-list — Aggregated pick list
# NOTE: Must be declared BEFORE /{order_id} to avoid UUID parse attempt.
# ---------------------------------------------------------------------------


@router.get(
    "/pick-list",
    response_class=HTMLResponse,
    summary="Batch pick list (admin)",
    description=(
        "Generate a printable HTML pick list aggregating all line items "
        "across every **PAID** order. Use this for batch warehouse picking "
        "before creating individual shipments."
    ),
    dependencies=[Depends(require_admin)],
    responses=PICK_LIST_RESPONSES,
)
async def get_pick_list(
    session: AsyncSession = Depends(get_session_dependency),
) -> HTMLResponse:
    """
    Render an HTML pick list over all currently PAID orders.

    Fetches all PAID orders and their items in two queries, aggregates by
    SKU, then renders the result as a printable HTML page.

    Args:
        session: Database session.

    Returns:
        HTMLResponse containing a printable pick list page.
    """
    repo = get_admin_order_repository(session)
    item_repo = get_order_item_repository(session)

    paid_orders = await repo.list_orders(
        status=OrderStatus.PAID, skip=0, limit=_PICK_LIST_MAX_ORDERS
    )
    order_ids = [o.id for o in paid_orders]
    all_items = await item_repo.get_by_order_ids(order_ids)

    pick_list: PickListResponse = build_pick_list(paid_orders, all_items)
    html = render_pick_list_html(pick_list)

    logger.info(
        "Pick list generated",
        extra={"order_count": len(paid_orders), "sku_count": len(pick_list.items)},
    )
    return HTMLResponse(content=html)


# ---------------------------------------------------------------------------
# GET /admin/orders/{id} — Full order detail
# ---------------------------------------------------------------------------


@router.get(
    "/{order_id}",
    response_model=AdminOrderDetailResponse,
    summary="Get order detail (admin)",
    description=(
        "Return the full order detail including customer, default shipping "
        "address, payment, and shipment records."
    ),
    dependencies=[Depends(require_admin)],
    responses=GET_ORDER_DETAIL_RESPONSES,
)
async def get_order_detail(
    order_id: UUID,
    session: AsyncSession = Depends(get_session_dependency),
) -> AdminOrderDetailResponse:
    """
    Fetch a single order with all its related entities for admin display.

    Args:
        order_id: UUID of the order to retrieve.
        session:  Database session.

    Returns:
        AdminOrderDetailResponse with nested customer, payment, shipment.

    Raises:
        NotFoundError (404): If the order does not exist or is soft-deleted.
    """
    ctx: OrderContext = await fetch_order_context(order_id, session)
    if not ctx.order or ctx.order.deleted_at is not None:
        raise entity_not_found("Order", order_id)

    logger.debug("Admin order detail fetched", extra={"order_id": str(order_id)})
    return db_to_admin_order_detail_response(
        ctx.order,
        ctx.items,
        ctx.customer,
        ctx.shipping_address,
        ctx.payment,
        ctx.shipment,
    )


# ---------------------------------------------------------------------------
# PATCH /admin/orders/{id}/status — Manual status override
# ---------------------------------------------------------------------------


@router.patch(
    "/{order_id}/status",
    response_model=AdminOrderDetailResponse,
    summary="Override order status (admin)",
    description=(
        "Manually set an order to any valid status. "
        "A `reason` field is required and is written to the structured "
        "application log as an audit trail entry."
    ),
    dependencies=[Depends(require_admin)],
    responses=STATUS_OVERRIDE_RESPONSES,
)
async def override_order_status(
    order_id: UUID,
    payload: AdminStatusOverrideRequest,
    session: AsyncSession = Depends(get_session_dependency),
) -> AdminOrderDetailResponse:
    """
    Override an order's status and write an audit log entry.

    Unlike the structured shipment transitions, this endpoint permits
    any target status so admins can correct edge-case states. The reason
    string is mandatory and is logged with order_id for auditability.

    Args:
        order_id: UUID of the order to update.
        payload:  AdminStatusOverrideRequest with new status and reason.
        session:  Database session.

    Returns:
        Updated AdminOrderDetailResponse.

    Raises:
        NotFoundError (404): If the order does not exist or is soft-deleted.
    """
    ctx: OrderContext = await fetch_order_context(order_id, session)
    if not ctx.order or ctx.order.deleted_at is not None:
        raise entity_not_found("Order", order_id)

    previous_status = ctx.order.status

    order_repo = get_admin_order_repository(session)
    updated_order = await order_repo.update(order_id, status=payload.status.value)

    logger.info(
        "Admin status override",
        extra={
            "order_id": str(order_id),
            "previous_status": previous_status,
            "new_status": payload.status.value,
            "reason": payload.reason,
        },
    )
    return db_to_admin_order_detail_response(
        updated_order,
        ctx.items,
        ctx.customer,
        ctx.shipping_address,
        ctx.payment,
        ctx.shipment,
    )


# ---------------------------------------------------------------------------
# GET /admin/orders/{id}/packing-slip — Printable HTML packing slip
# ---------------------------------------------------------------------------


@router.get(
    "/{order_id}/packing-slip",
    response_class=HTMLResponse,
    summary="Packing slip (admin)",
    description=(
        "Return a printable HTML packing slip for a single order. "
        "Open in browser and use Ctrl+P / Cmd+P to print."
    ),
    dependencies=[Depends(require_admin)],
    responses=PACKING_SLIP_RESPONSES,
)
async def get_packing_slip(
    order_id: UUID,
    session: AsyncSession = Depends(get_session_dependency),
) -> HTMLResponse:
    """
    Render an HTML packing slip for a specific order.

    Args:
        order_id: UUID of the order to render the slip for.
        session:  Database session.

    Returns:
        HTMLResponse with a printable packing slip.

    Raises:
        NotFoundError (404): If the order does not exist or is soft-deleted.
    """
    ctx: OrderContext = await fetch_order_context(order_id, session)
    if not ctx.order or ctx.order.deleted_at is not None:
        raise entity_not_found("Order", order_id)

    html = render_packing_slip(
        ctx.order, ctx.items, ctx.customer, ctx.shipping_address, ctx.shipment
    )
    logger.debug("Packing slip rendered", extra={"order_id": str(order_id)})
    return HTMLResponse(content=html)


# ---------------------------------------------------------------------------
# POST /admin/orders/{id}/shipments — Create shipment → READY_TO_SHIP
# ---------------------------------------------------------------------------


@router.post(
    "/{order_id}/shipments",
    response_model=AdminOrderDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create shipment (admin)",
    description=(
        "Create a shipment record for a **PAID** order and advance it to "
        "**READY_TO_SHIP**. Provide `tracking_number` for manual carriers. "
        "For DHL, leave it empty — the label job (Phase 3) will fill it in."
    ),
    dependencies=[Depends(require_admin)],
    responses=CREATE_SHIPMENT_RESPONSES,
)
async def create_order_shipment(
    order_id: UUID,
    payload: AdminCreateShipmentRequest,
    session: AsyncSession = Depends(get_session_dependency),
) -> AdminOrderDetailResponse:
    """
    Attach a shipment to a PAID order and advance it to READY_TO_SHIP.

    Args:
        order_id: UUID of the order to ship.
        payload:  AdminCreateShipmentRequest with carrier and optional tracking_number.
        session:  Database session.

    Returns:
        AdminOrderDetailResponse with updated status and new shipment.

    Raises:
        NotFoundError (404):     If the order does not exist or is soft-deleted.
        BusinessRuleError (400): If the order is not PAID, or already has a shipment.
    """
    updated_order, _ = await create_shipment(
        order_id=order_id,
        carrier=payload.carrier,
        tracking_number=payload.tracking_number,
        session=session,
    )

    ctx: OrderContext = await fetch_order_context(order_id, session)

    logger.info(
        "Shipment created via admin",
        extra={"order_id": str(order_id)},
    )
    return db_to_admin_order_detail_response(
        updated_order,
        ctx.items,
        ctx.customer,
        ctx.shipping_address,
        ctx.payment,
        ctx.shipment,
    )


# ---------------------------------------------------------------------------
# POST /admin/orders/{id}/ship — Mark SHIPPED + send tracking email
# ---------------------------------------------------------------------------


@router.post(
    "/{order_id}/ship",
    response_model=AdminOrderDetailResponse,
    summary="Mark order as shipped (admin)",
    description=(
        "Advance a **READY_TO_SHIP** order to **SHIPPED** and send a "
        "tracking notification e-mail to the customer. "
        "Requires a shipment record with a tracking number to be present."
    ),
    dependencies=[Depends(require_admin)],
    responses=SHIP_ORDER_RESPONSES,
)
async def ship_order(
    order_id: UUID,
    session: AsyncSession = Depends(get_session_dependency),
    settings: Settings = Depends(get_settings),
) -> AdminOrderDetailResponse:
    """
    Mark a READY_TO_SHIP order as SHIPPED and send the tracking email.

    Steps:
    1. Advance the order status to SHIPPED via mark_order_shipped.
    2. Load the full order context (customer, shipment, etc.).
    3. Send the tracking email (SMTP failure is logged, not re-raised).
    4. Build and return the full AdminOrderDetailResponse.

    Args:
        order_id: UUID of the order to mark as shipped.
        session:  Database session.
        settings: Application settings (SMTP config for email).

    Returns:
        AdminOrderDetailResponse with status=SHIPPED.

    Raises:
        NotFoundError (404):     If the order does not exist or is soft-deleted.
        BusinessRuleError (400): If the order is not in READY_TO_SHIP status.
    """
    updated_order = await mark_order_shipped(order_id=order_id, session=session)
    ctx: OrderContext = await fetch_order_context(order_id, session)

    if ctx.customer:
        await send_tracking_email(
            to_email=ctx.customer.email,
            customer_name=f"{ctx.customer.first_name} {ctx.customer.last_name}",
            order_id=order_id,
            tracking_number=ctx.shipment.tracking_number if ctx.shipment else None,
            carrier=ctx.shipment.carrier if ctx.shipment else "manual",
            settings=settings,
        )

    logger.info(
        "Order shipped via admin",
        extra={
            "order_id": str(order_id),
            "has_tracking": bool(ctx.shipment and ctx.shipment.tracking_number),
        },
    )
    return db_to_admin_order_detail_response(
        updated_order,
        ctx.items,
        ctx.customer,
        ctx.shipping_address,
        ctx.payment,
        ctx.shipment,
    )
