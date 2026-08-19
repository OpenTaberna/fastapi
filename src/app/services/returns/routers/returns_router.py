"""
Returns Router (Customer) — Phase 4.4

FastAPI router for customer-facing return requests:

    POST /orders/{id}/returns — Customer files a return request for a SHIPPED order

Business rules:
- Only orders in SHIPPED or REFUNDED status may have a return filed.
- One return per order (UNIQUE constraint enforced here before hitting the DB).
- customer_id is injected from the request header (dev shim, same as orders router).
"""

from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.orders.models.orders_models import OrderStatus
from app.services.orders.services.orders_db_service import get_order_repository
from app.shared.database.session import get_session_dependency
from app.shared.exceptions import (
    access_denied,
    entity_not_found,
    operation_not_allowed,
)
from app.shared.logger import get_logger

from ..models import CreateReturnRequest, ReturnResponse
from ..responses import CREATE_RETURN_RESPONSES
from ..services import get_return_repository

logger = get_logger(__name__)

router = APIRouter()

# Statuses that allow a return to be filed
_RETURNABLE_STATUSES = frozenset(
    {OrderStatus.SHIPPED.value, OrderStatus.REFUNDED.value}
)


# ---------------------------------------------------------------------------
# Helper: resolve customer_id from header (dev shim, matches orders_router)
# ---------------------------------------------------------------------------


async def _get_customer_id(
    x_customer_id: UUID | None = Header(
        default=None,
        alias="X-Customer-ID",
        description="[Dev-only] Customer UUID. Replaced by Keycloak token in production.",
    ),
) -> UUID:
    """
    Return the authenticated customer's UUID.

    Development shim: reads from ``X-Customer-ID`` header.
    Production: inject from validated Keycloak JWT.

    Args:
        x_customer_id: Optional UUID from the dev header.

    Returns:
        Customer UUID — generated if the header is absent.
    """
    if x_customer_id is None:
        return uuid4()
    return x_customer_id


# ---------------------------------------------------------------------------
# POST /orders/{id}/returns — File a return request
# ---------------------------------------------------------------------------


@router.post(
    "/{order_id}/returns",
    response_model=ReturnResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Request a return",
    description=(
        "File a return request (RMA) for a **SHIPPED** order. "
        "A return may only be requested once per order — subsequent calls "
        "return a 400 if a return already exists. "
        "The request is reviewed and approved or rejected by admin staff."
    ),
    responses=CREATE_RETURN_RESPONSES,
    tags=["Orders"],
)
async def create_return(
    order_id: UUID,
    payload: CreateReturnRequest,
    customer_id: UUID = Depends(_get_customer_id),
    session: AsyncSession = Depends(get_session_dependency),
) -> ReturnResponse:
    """
    File a return request for a shipped order.

    Steps:
    1. Load the order and verify it is SHIPPED (or REFUNDED).
    2. Verify the order belongs to the requesting customer.
    3. Guard against a duplicate return (one return per order).
    4. Create the ReturnDB row with status=REQUESTED.

    Args:
        order_id:    UUID of the order to return (path parameter).
        payload:     CreateReturnRequest with the return reason.
        customer_id: UUID of the authenticated customer.
        session:     Database session.

    Returns:
        ReturnResponse with status=REQUESTED.

    Raises:
        NotFoundError (404):     If the order does not exist or is soft-deleted.
        BusinessRuleError (400): If the order is not SHIPPED, or a return
                                 already exists for this order.
    """
    order_repo = get_order_repository(session)
    return_repo = get_return_repository(session)

    order = await order_repo.get(order_id)
    if not order or order.deleted_at is not None:
        raise entity_not_found("Order", order_id)

    _assert_order_returnable(order, order_id)
    _assert_order_owned_by_customer(order, customer_id, order_id)

    existing = await return_repo.get_by_order_id(order_id)
    if existing is not None:
        raise operation_not_allowed(
            operation="create_return",
            reason=f"A return request already exists for order '{order_id}'",
        )

    return_record = await return_repo.create(
        order_id=order_id,
        customer_id=customer_id,
        reason=payload.reason,
    )
    # Commit before returning. get_session_dependency also commits, but only
    # after the response has been sent, so a client that reads the return
    # straight back can otherwise get a 404 (see issue #26).
    await session.commit()

    logger.info(
        "Return request filed",
        extra={
            "return_id": str(return_record.id),
            "order_id": str(order_id),
            "customer_id": str(customer_id),
        },
    )
    return ReturnResponse.model_validate(return_record)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _assert_order_returnable(order, order_id: UUID) -> None:
    """
    Raise BusinessRuleError if the order is not in a returnable status.

    Args:
        order:    OrderDB instance to check.
        order_id: UUID used in the error context.

    Raises:
        BusinessRuleError (400): If the order status is not SHIPPED.
    """
    if order.status not in _RETURNABLE_STATUSES:
        raise operation_not_allowed(
            operation="create_return",
            reason=(
                f"Order '{order_id}' is in status '{order.status}' — "
                "returns may only be filed for SHIPPED orders"
            ),
        )


def _assert_order_owned_by_customer(order, customer_id: UUID, order_id: UUID) -> None:
    """
    Raise AuthorizationError if the order belongs to a different customer.

    Args:
        order:       OrderDB instance to check ownership of.
        customer_id: UUID of the requesting customer.
        order_id:    UUID used in the error context.

    Raises:
        AuthorizationError (403): If the order.customer_id != customer_id.
    """
    if order.customer_id != customer_id:
        raise access_denied(
            resource=f"order '{order_id}'",
            action="file a return for",
        )
