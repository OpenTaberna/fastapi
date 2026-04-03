"""
Inventory Functions — Phase 1.2

Business logic for stock reservation within the checkout flow.

All four functions operate on the same SQLAlchemy session and expect to run
inside a transaction so that failures roll back atomically.

Race-condition safety:
    reserve_inventory uses SELECT ... FOR UPDATE on InventoryItemDB rows so
    that concurrent checkouts for the same SKU are serialised at the DB level
    and can never double-book the same units.

Functions:
    reserve_inventory      — lock stock and create StockReservationDB rows
    release_reservation    — undo a reservation (payment failed / order cancelled)
    commit_reservation     — finalise a reservation after payment succeeded
    expire_reservations    — background sweep: release all TTL-exceeded reservations
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.inventory.models import (
    InventoryItemDB,
    ReservationStatus,
    StockReservationDB,
)
from app.shared.exceptions import operation_not_allowed
from app.shared.logger import get_logger

from ..models import OrderItemDB

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# reserve_inventory
# ---------------------------------------------------------------------------


async def reserve_inventory(
    session: AsyncSession,
    order_id: UUID,
    items: list[OrderItemDB],
    reservation_ttl_minutes: int = 15,
) -> None:
    """
    Lock stock for each line item and persist StockReservationDB rows.

    Uses SELECT … FOR UPDATE on each InventoryItemDB row so concurrent
    checkouts for the same SKU are serialised and cannot oversell.

    Steps (per line item):
        1. SELECT InventoryItemDB WHERE sku = ? FOR UPDATE
        2. Assert on_hand - reserved >= quantity  (raises 400 if not)
        3. Increment InventoryItemDB.reserved
        4. INSERT StockReservationDB (status=ACTIVE, expires_at=now+TTL)

    Args:
        session:                 The active AsyncSession (must be inside a transaction).
        order_id:                UUID of the order being checked out.
        items:                   OrderItemDB rows belonging to the order.
        reservation_ttl_minutes: How long the reservation is valid (default 15 min).

    Raises:
        BusinessRuleError (400): If any SKU has insufficient available stock.
    """
    expires_at = datetime.now(UTC) + timedelta(minutes=reservation_ttl_minutes)

    for item in items:
        # Pessimistic lock — prevents concurrent oversell
        stmt = (
            select(InventoryItemDB)
            .where(InventoryItemDB.sku == item.sku)
            .with_for_update()
        )
        result = await session.execute(stmt)
        inv = result.scalar_one_or_none()

        if inv is None:
            # SKU not tracked in inventory — treat as out-of-stock
            raise operation_not_allowed(
                operation="reserve_inventory",
                reason=f"SKU '{item.sku}' is not tracked in inventory",
            )

        available = inv.on_hand - inv.reserved
        if available < item.quantity:
            logger.warning(
                "Insufficient stock for reservation",
                extra={
                    "sku": item.sku,
                    "requested": item.quantity,
                    "available": available,
                    "order_id": str(order_id),
                },
            )
            raise operation_not_allowed(
                operation="reserve_inventory",
                reason=(
                    f"Insufficient stock for SKU '{item.sku}': "
                    f"requested {item.quantity}, available {available}"
                ),
            )

        # Increment reserved counter
        inv.reserved += item.quantity
        session.add(inv)

        # Create reservation row
        reservation = StockReservationDB(
            inventory_item_id=inv.id,
            order_id=order_id,
            quantity=item.quantity,
            expires_at=expires_at,
            status=ReservationStatus.ACTIVE.value,
        )
        session.add(reservation)

        logger.debug(
            "Stock reserved",
            extra={
                "sku": item.sku,
                "quantity": item.quantity,
                "order_id": str(order_id),
                "expires_at": expires_at.isoformat(),
            },
        )


# ---------------------------------------------------------------------------
# release_reservation
# ---------------------------------------------------------------------------


async def release_reservation(session: AsyncSession, order_id: UUID) -> None:
    """
    Release all ACTIVE stock reservations for an order.

    Called when:
    - Payment fails (webhook: payment_intent.payment_failed)
    - Customer cancels a DRAFT order before checkout
    - A reservation expires (see expire_reservations)

    Steps (per active reservation):
        1. Decrement InventoryItemDB.reserved by reservation.quantity
        2. Set StockReservationDB.status = RELEASED

    Args:
        session:  The active AsyncSession (must be inside a transaction).
        order_id: UUID of the order whose reservations should be released.
    """
    # Fetch all active reservations for this order
    stmt = select(StockReservationDB).where(
        and_(
            StockReservationDB.order_id == order_id,
            StockReservationDB.status == ReservationStatus.ACTIVE.value,
        )
    )
    result = await session.execute(stmt)
    reservations = list(result.scalars().all())

    if not reservations:
        logger.debug(
            "No active reservations to release",
            extra={"order_id": str(order_id)},
        )
        return

    for reservation in reservations:
        # Load the inventory item with a pessimistic lock to prevent
        # lost-update races when two concurrent releases target the same SKU.
        inv_stmt = (
            select(InventoryItemDB)
            .where(InventoryItemDB.id == reservation.inventory_item_id)
            .with_for_update()
        )
        inv_result = await session.execute(inv_stmt)
        inv = inv_result.scalar_one_or_none()
        if inv is not None:
            inv.reserved = max(0, inv.reserved - reservation.quantity)
            session.add(inv)

        reservation.status = ReservationStatus.RELEASED.value
        session.add(reservation)

    logger.info(
        "Reservations released",
        extra={"order_id": str(order_id), "count": len(reservations)},
    )


# ---------------------------------------------------------------------------
# commit_reservation
# ---------------------------------------------------------------------------


async def commit_reservation(session: AsyncSession, order_id: UUID) -> None:
    """
    Finalise all ACTIVE stock reservations after a successful payment.

    Decrements both InventoryItemDB.on_hand AND InventoryItemDB.reserved for
    each reservation and marks the reservation as COMMITTED. This is the step
    that actually reduces physical stock.

    Called by the Stripe webhook handler when payment_intent.succeeded is received.

    Steps (per active reservation):
        1. Decrement InventoryItemDB.reserved by reservation.quantity
        2. Decrement InventoryItemDB.on_hand by reservation.quantity
        3. Set StockReservationDB.status = COMMITTED

    Args:
        session:  The active AsyncSession (must be inside a transaction).
        order_id: UUID of the order whose reservations should be committed.
    """
    stmt = select(StockReservationDB).where(
        and_(
            StockReservationDB.order_id == order_id,
            StockReservationDB.status == ReservationStatus.ACTIVE.value,
        )
    )
    result = await session.execute(stmt)
    reservations = list(result.scalars().all())

    if not reservations:
        logger.warning(
            "commit_reservation called but no active reservations found",
            extra={"order_id": str(order_id)},
        )
        return

    for reservation in reservations:
        # Pessimistic lock — same reasoning as reserve_inventory:
        # concurrent commits / releases for the same SKU must be serialised.
        inv_stmt = (
            select(InventoryItemDB)
            .where(InventoryItemDB.id == reservation.inventory_item_id)
            .with_for_update()
        )
        inv_result = await session.execute(inv_stmt)
        inv = inv_result.scalar_one_or_none()
        if inv is not None:
            inv.reserved = max(0, inv.reserved - reservation.quantity)
            inv.on_hand = max(0, inv.on_hand - reservation.quantity)
            session.add(inv)

        reservation.status = ReservationStatus.COMMITTED.value
        session.add(reservation)

    logger.info(
        "Reservations committed",
        extra={"order_id": str(order_id), "count": len(reservations)},
    )


# ---------------------------------------------------------------------------
# expire_reservations
# ---------------------------------------------------------------------------


async def expire_reservations(session: AsyncSession) -> int:
    """
    Release all ACTIVE reservations whose TTL has passed.

    Intended to be called by a scheduled ARQ background job (Phase 4.2) at
    regular intervals (e.g. every 5 minutes).

    Steps:
        1. SELECT all ACTIVE reservations WHERE expires_at <= now()
        2. For each: decrement InventoryItemDB.reserved, set status = EXPIRED

    Args:
        session: The active AsyncSession (must be inside a transaction).

    Returns:
        Number of reservations that were expired.
    """
    now = datetime.now(UTC)
    stmt = select(StockReservationDB).where(
        and_(
            StockReservationDB.status == ReservationStatus.ACTIVE.value,
            StockReservationDB.expires_at <= now,
        )
    )
    result = await session.execute(stmt)
    expired = list(result.scalars().all())

    if not expired:
        logger.debug("expire_reservations: nothing to expire")
        return 0

    for reservation in expired:
        inv_stmt = (
            select(InventoryItemDB)
            .where(InventoryItemDB.id == reservation.inventory_item_id)
            .with_for_update()
        )
        inv_result = await session.execute(inv_stmt)
        inv = inv_result.scalar_one_or_none()
        if inv is not None:
            inv.reserved = max(0, inv.reserved - reservation.quantity)
            session.add(inv)

        reservation.status = ReservationStatus.EXPIRED.value
        session.add(reservation)

    logger.info(
        "Reservations expired by background sweep",
        extra={"count": len(expired)},
    )
    return len(expired)
