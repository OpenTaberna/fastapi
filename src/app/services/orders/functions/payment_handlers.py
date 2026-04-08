"""
Payment Webhook Handler Functions

Business logic for processing Stripe payment outcome events.

Extracted from the webhooks router so the router contains only HTTP/transport
concerns (header guards, 200-always contract, idempotency record). All order
state transitions and inventory side-effects live here.
"""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.payments.adapters import WebhookEventResult
from app.shared.logger import get_logger

from .inventory_functions import commit_reservation, release_reservation
from ..models import OrderStatus
from ..services import OrderRepository

from app.services.payments.services.payments_db_service import get_payment_repository

logger = get_logger(__name__)


def extract_order_id_from_webhook(event: WebhookEventResult) -> UUID | None:
    """
    Extract and validate the order_id from a Stripe webhook event's metadata.

    Stripe stores the internal order_id in the PaymentIntent metadata under the
    key "order_id". Returns None if the key is absent or the value is not a
    valid UUID — callers should record the event and return 200 in either case
    to uphold Stripe's 200-always contract (don't retry on bad data).

    Args:
        event: Parsed and signature-verified webhook event.

    Returns:
        order_id UUID if present and valid, otherwise None.
    """
    metadata: dict = (
        event.raw_payload.get("data", {}).get("object", {}).get("metadata", {})
    )
    raw_order_id: str | None = metadata.get("order_id")

    if raw_order_id is None:
        logger.warning(
            "Stripe webhook event has no order_id in metadata — ignoring",
            extra={"event_id": event.event_id, "event_type": event.event_type},
        )
        return None

    try:
        return UUID(raw_order_id)
    except ValueError:
        logger.warning(
            "Stripe webhook metadata.order_id is not a valid UUID",
            extra={"event_id": event.event_id, "raw_order_id": raw_order_id},
        )
        return None


async def handle_payment_succeeded(
    session: AsyncSession,
    order_repo: OrderRepository,
    order_id: UUID,
    event_id: str,
) -> None:
    """
    Transition order → PAID and commit inventory reservation.

    Guards: only acts if the order exists and is in PENDING_PAYMENT status.
    Logs and returns silently for any other state so the webhook handler can
    still record the event and return 200 to Stripe.

    Args:
        session:    Active AsyncSession (must be inside a transaction).
        order_repo: OrderRepository instance.
        order_id:   Internal order UUID from webhook metadata.
        event_id:   Stripe event ID for log context.
    """
    order = await order_repo.get(order_id)
    if order is None:
        logger.error(
            "payment_intent.succeeded for unknown order",
            extra={"order_id": str(order_id), "event_id": event_id},
        )
        return

    if order.status != OrderStatus.PENDING_PAYMENT.value:
        logger.warning(
            "payment_intent.succeeded but order is not PENDING_PAYMENT — skipping",
            extra={
                "order_id": str(order_id),
                "current_status": order.status,
                "event_id": event_id,
            },
        )
        return

    await order_repo.update(order_id, status=OrderStatus.PAID.value)
    await commit_reservation(session, order_id)

    logger.info(
        "Order marked PAID and inventory committed",
        extra={"order_id": str(order_id), "event_id": event_id},
    )


async def handle_payment_failed(
    session: AsyncSession,
    order_repo: OrderRepository,
    order_id: UUID,
    event_id: str,
) -> None:
    """
    Transition order → CANCELLED and release inventory reservation.

    Guards: only acts if the order exists and is in PENDING_PAYMENT or DRAFT
    status. Logs a warning for terminal states (already PAID / SHIPPED / etc.)
    and returns silently so Stripe's 200-always contract is upheld.

    Args:
        session:    Active AsyncSession (must be inside a transaction).
        order_repo: OrderRepository instance.
        order_id:   Internal order UUID from webhook metadata.
        event_id:   Stripe event ID for log context.
    """
    order = await order_repo.get(order_id)
    if order is None:
        logger.error(
            "payment_intent.payment_failed for unknown order",
            extra={"order_id": str(order_id), "event_id": event_id},
        )
        return

    if order.status not in (
        OrderStatus.PENDING_PAYMENT.value,
        OrderStatus.DRAFT.value,
    ):
        logger.warning(
            "payment_intent.payment_failed but order already in terminal state — skipping",
            extra={
                "order_id": str(order_id),
                "current_status": order.status,
                "event_id": event_id,
            },
        )
        return

    await order_repo.update(
        order_id,
        status=OrderStatus.CANCELLED.value,
        deleted_at=datetime.now(UTC),
    )
    await release_reservation(session, order_id)

    logger.info(
        "Order cancelled and inventory reservation released",
        extra={"order_id": str(order_id), "event_id": event_id},
    )


async def handle_charge_refunded(
    session: AsyncSession,
    order_repo: OrderRepository,
    order_id: UUID,
    event_id: str,
) -> None:
    """
    Transition order → REFUNDED and mark the payment record as refunded.

    Guards: only acts when the order is in PAID, READY_TO_SHIP, or SHIPPED
    status — a refund can arrive after the order has already shipped.  Logs
    a warning for orders already in REFUNDED or CANCELLED and returns silently
    so the webhook handler can still record the event and return 200 to Stripe.

    Args:
        session:    Active AsyncSession (must be inside a transaction).
        order_repo: OrderRepository instance.
        order_id:   Internal order UUID from webhook metadata.
        event_id:   Stripe event ID for log context.
    """
    _REFUNDABLE_STATUSES = (
        OrderStatus.PAID.value,
        OrderStatus.READY_TO_SHIP.value,
        OrderStatus.SHIPPED.value,
    )

    order = await order_repo.get(order_id)
    if order is None:
        logger.error(
            "charge.refunded for unknown order",
            extra={"order_id": str(order_id), "event_id": event_id},
        )
        return

    if order.status not in _REFUNDABLE_STATUSES:
        logger.warning(
            "charge.refunded but order is not in a refundable status — skipping",
            extra={
                "order_id": str(order_id),
                "current_status": order.status,
                "event_id": event_id,
            },
        )
        return

    await order_repo.update(order_id, status=OrderStatus.REFUNDED.value)
    await _mark_payment_refunded(session, order_id, event_id)

    logger.info(
        "Order marked REFUNDED",
        extra={"order_id": str(order_id), "event_id": event_id},
    )


async def handle_payment_intent_canceled(
    session: AsyncSession,
    order_repo: OrderRepository,
    order_id: UUID,
    event_id: str,
) -> None:
    """
    Transition order → CANCELLED and release any active inventory reservation.

    Called when Stripe fires a ``payment_intent.canceled`` event — this means
    the PSP session was voided before payment was captured.  The business
    effect is identical to ``payment_intent.payment_failed``: cancel the order
    and free the reserved stock.

    Guards: only acts when the order is in PENDING_PAYMENT or DRAFT status.
    Terminal states (PAID, SHIPPED, etc.) are logged and skipped.

    Args:
        session:    Active AsyncSession (must be inside a transaction).
        order_repo: OrderRepository instance.
        order_id:   Internal order UUID from webhook metadata.
        event_id:   Stripe event ID for log context.
    """
    order = await order_repo.get(order_id)
    if order is None:
        logger.error(
            "payment_intent.canceled for unknown order",
            extra={"order_id": str(order_id), "event_id": event_id},
        )
        return

    if order.status not in (
        OrderStatus.PENDING_PAYMENT.value,
        OrderStatus.DRAFT.value,
    ):
        logger.warning(
            "payment_intent.canceled but order already in terminal state — skipping",
            extra={
                "order_id": str(order_id),
                "current_status": order.status,
                "event_id": event_id,
            },
        )
        return

    await order_repo.update(
        order_id,
        status=OrderStatus.CANCELLED.value,
        deleted_at=datetime.now(UTC),
    )
    await release_reservation(session, order_id)

    logger.info(
        "Order cancelled via payment_intent.canceled and reservation released",
        extra={"order_id": str(order_id), "event_id": event_id},
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


async def _mark_payment_refunded(
    session: AsyncSession,
    order_id: UUID,
    event_id: str,
) -> None:
    """
    Update the payment record linked to ``order_id`` to status REFUNDED.

    Logs a warning without raising when no payment record is found — this is
    abnormal (a refund without a payment row) but should not fail the webhook.

    Args:
        session:  Active AsyncSession.
        order_id: Internal order UUID used to look up the payment record.
        event_id: Stripe event ID for log context.
    """
    from app.services.payments.models.payments_models import PaymentStatus

    payment_repo = get_payment_repository(session)
    payments = await payment_repo.filter(order_id=order_id)
    payment_list = list(payments)

    if not payment_list:
        logger.warning(
            "charge.refunded: no payment record found for order",
            extra={"order_id": str(order_id), "event_id": event_id},
        )
        return

    payment = payment_list[0]
    await payment_repo.update(payment.id, status=PaymentStatus.REFUNDED.value)
    logger.debug(
        "Payment record marked REFUNDED",
        extra={
            "payment_id": str(payment.id),
            "order_id": str(order_id),
            "event_id": event_id,
        },
    )
