"""
Webhooks Router — Phase 1.5

FastAPI router for incoming payment-provider webhooks:

    POST /webhooks/stripe — Handle Stripe payment_intent.succeeded /
                            payment_intent.payment_failed

Phase 1.5 implements:
    - Routing and HTTP concerns (header check, 200-always contract)
    - Idempotency via WebhookEventDB (provider + event_id UNIQUE)
    - Order status transitions: PENDING_PAYMENT → PAID / CANCELLED
    - Inventory commit / release after payment outcome

Signature verification is deliberately delegated to the PSP adapter
(Phase 1.4, colleague's branch). This router receives a parsed, already-
verified event dict from the adapter and is otherwise adapter-agnostic.

    TODO (after 1.4 merge): inject PaymentProviderAdapter and call
    adapter.verify_webhook(raw_body, signature) instead of the
    _parse_and_verify_event stub below.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Header, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.payments.adapters import PaymentProviderAdapter, WebhookEventResult
from app.services.payments.dependencies import get_payment_adapter
from app.services.webhooks.models import WebhookEventDB
from app.services.webhooks.services import get_webhook_event_repository
from app.shared.database.session import get_session_dependency
from app.shared.exceptions import operation_not_allowed
from app.shared.logger import get_logger

from ..functions import (
    extract_order_id_from_webhook,
    handle_payment_failed,
    handle_payment_succeeded,
)
from ..responses import STRIPE_WEBHOOK_RESPONSES
from ..services import get_order_repository

logger = get_logger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Event type constants (Stripe event names)
# ---------------------------------------------------------------------------

_EVT_SUCCEEDED = "payment_intent.succeeded"
_EVT_FAILED = "payment_intent.payment_failed"


# ---------------------------------------------------------------------------
# POST /webhooks/stripe
# ---------------------------------------------------------------------------


@router.post(
    "/stripe",
    status_code=status.HTTP_200_OK,
    summary="Stripe payment webhook",
    description=(
        "Receives Stripe webhook events (`payment_intent.succeeded` / "
        "`payment_intent.payment_failed`). "
        "Verifies the `Stripe-Signature` HMAC via the `StripeAdapter`, enforces "
        "idempotency via the `webhook_events` inbox table, then transitions the "
        "associated order to **PAID** (+ commits inventory) or **CANCELLED** "
        "(+ releases inventory reservation).\n\n"
        "Always returns **200 OK** so Stripe stops retrying — processing errors "
        "are logged and will trigger an alert in production."
    ),
    responses=STRIPE_WEBHOOK_RESPONSES,
    tags=["Webhooks"],
)
async def stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
    session: AsyncSession = Depends(get_session_dependency),
    adapter: PaymentProviderAdapter = Depends(get_payment_adapter),
) -> dict:
    """
    Handle incoming Stripe webhook events.

    Flow:
    1. Reject missing Stripe-Signature with 400.
    2. Verify HMAC signature and parse event via PaymentProviderAdapter.
    3. Check WebhookEventDB for duplicate (provider='stripe', event_id=evt.id).
       Return 200 immediately if already processed (idempotent).
    4. Dispatch:
       - payment_intent.succeeded      → PAID   + commit_reservation
       - payment_intent.payment_failed → CANCELLED + release_reservation
    5. Insert WebhookEventDB row in the same DB transaction.

    Args:
        request:          Raw HTTP request (body needed for HMAC verification).
        stripe_signature: Value of the ``Stripe-Signature`` header.
        session:          Database session.
        adapter:          Payment provider adapter (injected via Depends).

    Returns:
        {"received": True}

    Raises:
        BusinessRuleError (400):   Missing Stripe-Signature header.
        WebhookSignatureError (400): Invalid or expired HMAC signature.
        DatabaseError (500):       DB operation failure.
    """
    # ------------------------------------------------------------------
    # 1. Guard: header must be present
    # ------------------------------------------------------------------
    if stripe_signature is None:
        raise operation_not_allowed(
            operation="stripe_webhook",
            reason="Missing Stripe-Signature header",
        )

    raw_body: bytes = await request.body()

    # ------------------------------------------------------------------
    # 2. Verify HMAC signature and parse event via PSP adapter
    # ------------------------------------------------------------------
    event: WebhookEventResult = await adapter.parse_webhook_event(
        raw_body, stripe_signature
    )

    event_id: str = event.event_id
    event_type: str = event.event_type

    logger.info(
        "Stripe webhook received",
        extra={"event_id": event_id, "event_type": event_type},
    )

    # ------------------------------------------------------------------
    # 3. Idempotency check
    # ------------------------------------------------------------------
    webhook_repo = get_webhook_event_repository(session)
    existing = await webhook_repo.get_by(provider="stripe", event_id=event_id)
    if existing is not None:
        logger.info(
            "Stripe webhook duplicate — already processed",
            extra={"event_id": event_id},
        )
        return {"received": True}

    # ------------------------------------------------------------------
    # 4. Extract order_id from event metadata
    # ------------------------------------------------------------------
    order_id = extract_order_id_from_webhook(event)

    if order_id is None:
        await _record_webhook_event(session, webhook_repo, event_id, event.raw_payload)
        return {"received": True}

    # ------------------------------------------------------------------
    # 5. Dispatch by event type
    # ------------------------------------------------------------------
    order_repo = get_order_repository(session)

    if event_type == _EVT_SUCCEEDED:
        await handle_payment_succeeded(session, order_repo, order_id, event_id)
    elif event_type == _EVT_FAILED:
        await handle_payment_failed(session, order_repo, order_id, event_id)
    else:
        logger.debug(
            "Stripe webhook event type not handled — ignored",
            extra={"event_id": event_id, "event_type": event_type},
        )

    # ------------------------------------------------------------------
    # 6. Record event in inbox (idempotency guard for future duplicates)
    # ------------------------------------------------------------------
    await _record_webhook_event(session, webhook_repo, event_id, event.raw_payload)

    return {"received": True}


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


async def _record_webhook_event(
    session: AsyncSession,
    webhook_repo,
    event_id: str,
    event: dict,
) -> None:
    """
    Persist a WebhookEventDB row for idempotency tracking.

    Flushes immediately so the UNIQUE constraint (provider, event_id) fires
    before the transaction commits. If two concurrent requests race past the
    idempotency SELECT, only one flush will succeed — the loser's IntegrityError
    triggers a rollback of just the flush, not the whole transaction.
    """
    row = WebhookEventDB(
        provider="stripe",
        event_id=event_id,
        payload=event,
        processed_at=datetime.now(UTC),
    )
    session.add(row)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        logger.info(
            "Stripe webhook inbox insert raced — already recorded by concurrent request",
            extra={"event_id": event_id},
        )
