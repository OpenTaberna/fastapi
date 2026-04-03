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
