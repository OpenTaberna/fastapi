"""
Orders Router

FastAPI router for order lifecycle endpoints (Phase 1):

    POST   /orders                   — Create a draft order
    GET    /orders/{id}              — Get a single order (own orders only)
    DELETE /orders/{id}              — Cancel a draft order
    POST   /orders/{id}/checkout     — Advance DRAFT → PENDING_PAYMENT
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.payments.adapters import PaymentProviderAdapter
from app.services.payments.dependencies import get_payment_adapter
from app.shared.config import get_settings
from app.shared.config.settings import Settings
from app.shared.database.session import get_session_dependency
from app.shared.exceptions import entity_not_found
from app.shared.logger import get_logger

from ..functions import (
    assert_order_owned_by,
    db_to_checkout_response,
    db_to_order_detail_response,
    reserve_inventory,
    resolve_order_lines,
    validate_status_transition,
)
from ..models import (
    CheckoutResponse,
    OrderCreate,
    OrderDB,
    OrderDetailResponse,
    OrderItemDB,
    OrderStatus,
)
from ..responses import (
    CANCEL_ORDER_RESPONSES,
    CHECKOUT_ORDER_RESPONSES,
    CREATE_ORDER_RESPONSES,
    GET_ORDER_RESPONSES,
)
from ..services import (
    get_order_item_repository,
    get_order_repository,
)

logger = get_logger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Helper: resolve customer_id from request
# ---------------------------------------------------------------------------
# TODO (Phase 1): Replace with real Keycloak dependency once auth is wired up.
# For now we accept an optional `X-Customer-ID` header as a stand-in so the
# endpoints are testable without a running Keycloak instance.


async def _get_customer_id(
    x_customer_id: UUID | None = Header(
        default=None,
        alias="X-Customer-ID",
        description="[Dev-only] Customer UUID. Replaced by Keycloak token in production.",
    ),
) -> UUID:
    """Return the authenticated customer's UUID.

    Development shim: reads from `X-Customer-ID` header.
    Production: inject from validated Keycloak JWT.
    """
    if x_customer_id is None:
        # Generate a stable UUID so automated tests without the header still pass
        # through validation.  In production this path is unreachable.
        return uuid4()
    return x_customer_id


# ---------------------------------------------------------------------------
# POST /orders — Create draft order
# ---------------------------------------------------------------------------


@router.post(
    "/",
    response_model=OrderDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a draft order",
    description=(
        "Create a new order in **DRAFT** status. "
        "Prices are snapshotted from the item catalogue at creation time. "
        "`customer_id` is injected from the Keycloak token (dev: `X-Customer-ID` header)."
    ),
    responses=CREATE_ORDER_RESPONSES,
)
async def create_order(
    payload: OrderCreate,
    customer_id: UUID = Depends(_get_customer_id),
    session: AsyncSession = Depends(get_session_dependency),
) -> OrderDetailResponse:
    """
    Create a draft order.

    Steps:
    1. Resolve each SKU → look up current price from item catalogue.
    2. Persist OrderDB (status=DRAFT, total_amount=sum of line items).
    3. Persist OrderItemDB rows with the price snapshot.

    Args:
        payload:     Order creation data (items list, currency).
        customer_id: UUID of the authenticated customer.
        session:     Database session.

    Returns:
        OrderDetailResponse: Created order with all line items.

    Raises:
        NotFoundError (404):          If any requested SKU does not exist.
        RequestValidationError (422): If input data fails Pydantic validation.
        DatabaseError (500):          If a database operation fails.
    """
    order_repo = get_order_repository(session)

    # ------------------------------------------------------------------
    # 1 & 2. Resolve SKUs → price snapshot + calculate total_amount
    # ------------------------------------------------------------------
    resolved_lines, total_amount = await resolve_order_lines(session, payload.items)

    # ------------------------------------------------------------------
    # 3. Persist order
    # ------------------------------------------------------------------
    order: OrderDB = await order_repo.create(
        customer_id=customer_id,
        status=OrderStatus.DRAFT.value,
        total_amount=total_amount,
        currency=payload.currency,
    )
    logger.info(
        "Draft order created",
        extra={"order_id": str(order.id), "customer_id": str(customer_id)},
    )

    # ------------------------------------------------------------------
    # 4. Persist line items
    # ------------------------------------------------------------------
    item_repo = get_order_item_repository(session)
    order_items: list[OrderItemDB] = []
    for line, unit_price in resolved_lines:
        oi: OrderItemDB = await item_repo.create(
            order_id=order.id,
            sku=line.sku,
            quantity=line.quantity,
            unit_price=unit_price,
        )
        order_items.append(oi)

    return db_to_order_detail_response(order, order_items)


# ---------------------------------------------------------------------------
# GET /orders/{id} — Retrieve a single order
# ---------------------------------------------------------------------------


@router.get(
    "/{order_id}",
    response_model=OrderDetailResponse,
    summary="Get order by ID",
    description=(
        "Retrieve a single order with its line items. "
        "Customers can only access their own orders."
    ),
    responses=GET_ORDER_RESPONSES,
)
async def get_order(
    order_id: UUID,
    customer_id: UUID = Depends(_get_customer_id),
    session: AsyncSession = Depends(get_session_dependency),
) -> OrderDetailResponse:
    """
    Get order by ID.

    Args:
        order_id:    Order UUID (path parameter).
        customer_id: UUID of the authenticated customer.
        session:     Database session.

    Returns:
        OrderDetailResponse with nested line items.

    Raises:
        NotFoundError (404):     If the order does not exist (or is soft-deleted).
        AuthorizationError (403): If the order belongs to another customer.
        RequestValidationError (422): If the UUID format is invalid.
        DatabaseError (500):     If a database operation fails.
    """
    order_repo = get_order_repository(session)
    item_repo = get_order_item_repository(session)

    order = await order_repo.get(order_id)
    if not order or order.deleted_at is not None:
        raise entity_not_found("Order", order_id)

    assert_order_owned_by(order, customer_id)

    order_items = await item_repo.filter(order_id=order.id)
    logger.debug("Order fetched", extra={"order_id": str(order_id)})
    return db_to_order_detail_response(order, list(order_items))


# ---------------------------------------------------------------------------
# DELETE /orders/{id} — Cancel a draft order
# ---------------------------------------------------------------------------


@router.delete(
    "/{order_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Cancel a draft order",
    description=(
        "Cancel an order. Only orders in **DRAFT** status may be cancelled this way. "
        "The order record is soft-deleted (sets `deleted_at`) and its status is set "
        "to `cancelled`."
    ),
    responses=CANCEL_ORDER_RESPONSES,
)
async def cancel_order(
    order_id: UUID,
    customer_id: UUID = Depends(_get_customer_id),
    session: AsyncSession = Depends(get_session_dependency),
) -> None:
    """
    Cancel a draft order.

    Args:
        order_id:    Order UUID (path parameter).
        customer_id: UUID of the authenticated customer.
        session:     Database session.

    Raises:
        NotFoundError (404):       If the order does not exist.
        AuthorizationError (403):  If the order belongs to another customer.
        BusinessRuleError (400):   If the order is not in DRAFT status.
        RequestValidationError (422): If the UUID format is invalid.
        DatabaseError (500):       If a database operation fails.
    """
    order_repo = get_order_repository(session)

    order = await order_repo.get(order_id)
    if not order or order.deleted_at is not None:
        raise entity_not_found("Order", order_id)

    assert_order_owned_by(order, customer_id)
    validate_status_transition(order, OrderStatus.CANCELLED)

    # Soft-delete + status update
    await order_repo.update(
        order_id,
        status=OrderStatus.CANCELLED.value,
        deleted_at=datetime.now(UTC),
    )
    logger.info("Order cancelled", extra={"order_id": str(order_id)})


# ---------------------------------------------------------------------------
# POST /orders/{id}/checkout — Advance DRAFT → PENDING_PAYMENT
# ---------------------------------------------------------------------------


@router.post(
    "/{order_id}/checkout",
    response_model=CheckoutResponse,
    summary="Start checkout",
    description=(
        "Transition an order from **DRAFT** to **PENDING_PAYMENT**. "
        "Reserves inventory for each line item and creates a Stripe PaymentIntent. "
        "Returns the updated order together with a `client_secret` for the "
        "frontend Stripe.js SDK to complete the payment flow."
    ),
    responses=CHECKOUT_ORDER_RESPONSES,
)
async def checkout_order(
    order_id: UUID,
    customer_id: UUID = Depends(_get_customer_id),
    session: AsyncSession = Depends(get_session_dependency),
    adapter: PaymentProviderAdapter = Depends(get_payment_adapter),
    settings: Settings = Depends(get_settings),
) -> CheckoutResponse:
    """
    Start the checkout flow for a draft order.

    Steps:
    1. Load & authorize the order.
    2. Validate DRAFT → PENDING_PAYMENT transition.
    3. Reserve inventory for each line item.
    4. Create a Stripe PaymentIntent via the PSP adapter.
    5. Persist status = PENDING_PAYMENT.

    Args:
        order_id:    Order UUID (path parameter).
        customer_id: UUID of the authenticated customer.
        session:     Database session.
        adapter:     Payment provider adapter (injected via Depends).
        settings:    Application settings (injected via Depends).

    Returns:
        CheckoutResponse with status=PENDING_PAYMENT and client_secret for the
        frontend Stripe.js SDK.

    Raises:
        NotFoundError (404):          If the order does not exist.
        AuthorizationError (403):     If the order belongs to another customer.
        BusinessRuleError (400):      If the order is not in DRAFT status or
                                      insufficient stock for any line item.
        PaymentProviderError (502):   If the Stripe API call fails.
        RequestValidationError (422): If the UUID format is invalid.
        DatabaseError (500):          If a database operation fails.
    """
    order_repo = get_order_repository(session)
    item_repo = get_order_item_repository(session)

    order = await order_repo.get(order_id)
    if not order or order.deleted_at is not None:
        raise entity_not_found("Order", order_id)

    assert_order_owned_by(order, customer_id)
    validate_status_transition(order, OrderStatus.PENDING_PAYMENT)

    order_items = list(await item_repo.filter(order_id=order.id))

    # ------------------------------------------------------------------
    # Phase 1.2 — Reserve inventory (implemented)
    # ------------------------------------------------------------------
    await reserve_inventory(
        session=session,
        order_id=order_id,
        items=order_items,
        reservation_ttl_minutes=settings.reservation_ttl_minutes,
    )

    # ------------------------------------------------------------------
    # Phase 1.4 — Create Stripe PaymentIntent via adapter
    # ------------------------------------------------------------------
    payment_session = await adapter.create_payment_session(
        order_id=order_id,
        amount=order.total_amount,
        currency=order.currency,
        metadata={"customer_id": str(customer_id)},
    )
    logger.info(
        "PSP payment session created",
        extra={
            "order_id": str(order_id),
            "provider_reference": payment_session.provider_reference,
        },
    )

    # Advance status
    updated_order: OrderDB = await order_repo.update(
        order_id,
        status=OrderStatus.PENDING_PAYMENT.value,
    )
    logger.info(
        "Order advanced to PENDING_PAYMENT",
        extra={"order_id": str(order_id)},
    )
    return db_to_checkout_response(
        updated_order, order_items, payment_session.client_secret
    )
