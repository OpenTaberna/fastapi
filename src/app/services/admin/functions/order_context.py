"""
Order Context

Loads the complete set of entities needed by every admin order-detail endpoint
in a single place, eliminating the five-query pattern that was duplicated
across four router functions.
"""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.customers.models.customers_db_models import AddressDB, CustomerDB
from app.services.customers.services.customers_db_service import (
    get_address_repository,
    get_customer_repository,
)
from app.services.admin.services.admin_db_service import get_admin_order_repository
from app.services.orders.models.orders_db_models import OrderDB, OrderItemDB
from app.services.orders.services.orders_db_service import get_order_item_repository
from app.services.payments.models.payments_db_models import PaymentDB
from app.services.payments.services.payments_db_service import get_payment_repository
from app.services.shipments.models.shipments_db_models import ShipmentDB
from app.services.shipments.services.shipments_db_service import get_shipment_repository
from app.shared.logger import get_logger

logger = get_logger(__name__)


@dataclass
class OrderContext:
    """
    All entities related to a single order, loaded together.

    Each field may be None when the related record does not yet exist
    (e.g. no shipment on a DRAFT order). Callers must handle None values.
    """

    order: OrderDB
    items: list[OrderItemDB]
    customer: CustomerDB | None
    shipping_address: AddressDB | None
    payment: PaymentDB | None
    shipment: ShipmentDB | None


async def fetch_order_context(order_id: UUID, session: AsyncSession) -> OrderContext:
    """
    Load all entities related to a single order in five targeted queries.

    This function is the single authoritative place that knows which
    repositories to call and in what order. Router functions call it once
    and pass the result to the transformation layer — they never build
    individual repositories themselves.

    Args:
        order_id: UUID of the order whose context should be loaded.
        session:  AsyncSession for all DB operations.

    Returns:
        OrderContext dataclass with the order and all related entities.
        Related entities (customer, address, payment, shipment) are None
        when they do not exist.

    Note:
        This function does NOT raise 404 if the order is missing — callers
        are responsible for checking `context.order` and raising as needed,
        since some callers already hold the order object from a prior step.
    """
    logger.debug(
        "Fetching full order context",
        extra={"order_id": str(order_id)},
    )

    item_repo = get_order_item_repository(session)
    customer_repo = get_customer_repository(session)
    address_repo = get_address_repository(session)
    payment_repo = get_payment_repository(session)
    shipment_repo = get_shipment_repository(session)

    order_repo = get_admin_order_repository(session)
    order = await order_repo.get(order_id)

    items = list(await item_repo.filter(order_id=order_id)) if order else []

    customer = await customer_repo.get(order.customer_id) if order else None

    shipping_address = None
    if customer:
        shipping_address = await address_repo.get_by(
            customer_id=customer.id, is_default=True
        )

    payment = await payment_repo.get_by(order_id=order_id)
    shipment = await shipment_repo.get_by(order_id=order_id)

    logger.debug(
        "Order context loaded",
        extra={
            "order_id": str(order_id),
            "has_customer": customer is not None,
            "has_payment": payment is not None,
            "has_shipment": shipment is not None,
        },
    )

    return OrderContext(
        order=order,
        items=items,
        customer=customer,
        shipping_address=shipping_address,
        payment=payment,
        shipment=shipment,
    )
