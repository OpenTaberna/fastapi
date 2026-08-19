"""
Shipment Functions

Business logic for the two admin shipment endpoints:

  - create_shipment  — attach a ShipmentDB to a PAID order → READY_TO_SHIP
  - mark_order_shipped — advance READY_TO_SHIP → SHIPPED

Both functions are async and perform exactly one business operation.
They raise BusinessRuleError / NotFoundError via the shared exception
helpers so the global exception handler converts them to the correct
HTTP status codes automatically.
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.orders.functions.order_validation import validate_status_transition
from app.services.orders.models.orders_db_models import OrderDB
from app.services.orders.models.orders_models import OrderStatus
from app.services.orders.services.orders_db_service import get_order_repository
from app.services.shipments.models.shipments_db_models import ShipmentDB
from app.services.shipments.models.shipments_models import Carrier, ShipmentStatus
from app.services.shipments.services.shipments_db_service import get_shipment_repository
from app.shared.exceptions import BusinessRuleError, entity_not_found
from app.shared.logger import get_logger

logger = get_logger(__name__)


async def create_shipment(
    order_id: UUID,
    carrier: Carrier,
    tracking_number: str | None,
    session: AsyncSession,
) -> tuple[OrderDB, ShipmentDB]:
    """
    Create a shipment record for a PAID order and advance it to READY_TO_SHIP.

    Steps:
    1. Load the order; raise 404 if missing or soft-deleted.
    2. Validate the PAID → READY_TO_SHIP status transition.
    3. Guard against a duplicate shipment on the same order.
    4. Persist a ShipmentDB with status=PENDING (label not yet created).
    5. Advance the order status to READY_TO_SHIP.

    Args:
        order_id:        UUID of the order to attach the shipment to.
        carrier:         Carrier enum value (MANUAL or DHL).
        tracking_number: Optional carrier tracking number; may be None when
                         the label is created later (Phase 3).
        session:         AsyncSession for all DB operations.

    Returns:
        Tuple of (updated OrderDB, newly created ShipmentDB).

    Raises:
        NotFoundError (404):    If the order does not exist or is soft-deleted.
        BusinessRuleError (400): If the order is not in PAID status, or if a
                                 shipment already exists for this order.
    """
    order_repo = get_order_repository(session)
    shipment_repo = get_shipment_repository(session)

    order = await order_repo.get(order_id)
    if not order or order.deleted_at is not None:
        raise entity_not_found("Order", order_id)

    validate_status_transition(order, OrderStatus.READY_TO_SHIP)

    existing = await shipment_repo.get_by(order_id=order_id)
    if existing is not None:
        raise BusinessRuleError(
            message="A shipment already exists for this order.",
            context={"order_id": str(order_id), "shipment_id": str(existing.id)},
        )

    shipment: ShipmentDB = await shipment_repo.create(
        order_id=order_id,
        carrier=carrier.value,
        tracking_number=tracking_number,
        status=ShipmentStatus.PENDING.value,
    )
    logger.info(
        "Shipment created",
        extra={
            "order_id": str(order_id),
            "shipment_id": str(shipment.id),
            "carrier": carrier.value,
        },
    )

    updated_order: OrderDB = await order_repo.update(
        order_id, status=OrderStatus.READY_TO_SHIP.value
    )
    logger.info(
        "Order advanced to READY_TO_SHIP",
        extra={"order_id": str(order_id)},
    )

    return updated_order, shipment


async def mark_order_shipped(
    order_id: UUID,
    session: AsyncSession,
) -> OrderDB:
    """
    Advance a READY_TO_SHIP order to SHIPPED.

    This is the final admin action before sending the tracking e-mail.
    The calling router is responsible for triggering send_tracking_email
    after this function returns.

    Steps:
    1. Load the order; raise 404 if missing or soft-deleted.
    2. Validate the READY_TO_SHIP → SHIPPED status transition.
    3. Persist status = SHIPPED.

    Args:
        order_id: UUID of the order to mark as shipped.
        session:  AsyncSession for all DB operations.

    Returns:
        Updated OrderDB with status=SHIPPED.

    Raises:
        NotFoundError (404):     If the order does not exist or is soft-deleted.
        BusinessRuleError (400): If the order is not in READY_TO_SHIP status.
    """
    order_repo = get_order_repository(session)

    order = await order_repo.get(order_id)
    if not order or order.deleted_at is not None:
        raise entity_not_found("Order", order_id)

    validate_status_transition(order, OrderStatus.SHIPPED)

    updated_order: OrderDB = await order_repo.update(
        order_id, status=OrderStatus.SHIPPED.value
    )
    logger.info("Order marked as SHIPPED", extra={"order_id": str(order_id)})

    return updated_order
