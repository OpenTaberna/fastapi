"""Unit tests for payment persistence during Stripe webhook handling."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.orders.functions.payment_handlers import (
    handle_payment_failed,
    handle_payment_succeeded,
)
from app.services.orders.models import OrderStatus
from app.services.payments.adapters import WebhookEventResult


def _event(event_type: str = "payment_intent.succeeded") -> WebhookEventResult:
    return WebhookEventResult(
        event_id="evt_test_123",
        event_type=event_type,
        provider_reference="pi_test_123",
        raw_payload={},
    )


def _order() -> MagicMock:
    order = MagicMock()
    order.id = uuid4()
    order.status = OrderStatus.PENDING_PAYMENT.value
    order.total_amount = 2599
    order.currency = "EUR"
    return order


@pytest.mark.asyncio
async def test_succeeded_webhook_updates_existing_payment() -> None:
    session = MagicMock()
    order = _order()
    order_repo = MagicMock()
    order_repo.get = AsyncMock(return_value=order)
    order_repo.update = AsyncMock()
    payment = MagicMock(id=uuid4(), order_id=order.id)
    payment_repo = MagicMock()
    payment_repo.get_by = AsyncMock(return_value=payment)
    payment_repo.update = AsyncMock()

    with (
        patch(
            "app.services.orders.functions.payment_handlers.get_payment_repository",
            return_value=payment_repo,
        ),
        patch(
            "app.services.orders.functions.payment_handlers.commit_reservation",
            new=AsyncMock(),
        ),
    ):
        await handle_payment_succeeded(session, order_repo, order.id, _event())

    payment_repo.update.assert_awaited_once_with(payment.id, status="succeeded")
    order_repo.update.assert_awaited_once_with(order.id, status="paid")


@pytest.mark.asyncio
async def test_failed_webhook_updates_existing_payment() -> None:
    session = MagicMock()
    order = _order()
    order_repo = MagicMock()
    order_repo.get = AsyncMock(return_value=order)
    order_repo.update = AsyncMock()
    payment = MagicMock(id=uuid4(), order_id=order.id)
    payment_repo = MagicMock()
    payment_repo.get_by = AsyncMock(return_value=payment)
    payment_repo.update = AsyncMock()

    with (
        patch(
            "app.services.orders.functions.payment_handlers.get_payment_repository",
            return_value=payment_repo,
        ),
        patch(
            "app.services.orders.functions.payment_handlers.release_reservation",
            new=AsyncMock(),
        ),
    ):
        await handle_payment_failed(
            session,
            order_repo,
            order.id,
            _event("payment_intent.payment_failed"),
        )

    payment_repo.update.assert_awaited_once_with(payment.id, status="failed")
    assert order_repo.update.await_args.kwargs["status"] == "cancelled"


@pytest.mark.asyncio
async def test_webhook_backfills_missing_payment() -> None:
    session = MagicMock()
    order = _order()
    order_repo = MagicMock()
    order_repo.get = AsyncMock(return_value=order)
    order_repo.update = AsyncMock()
    payment_repo = MagicMock()
    payment_repo.get_by = AsyncMock(return_value=None)
    payment_repo.create = AsyncMock()

    with (
        patch(
            "app.services.orders.functions.payment_handlers.get_payment_repository",
            return_value=payment_repo,
        ),
        patch(
            "app.services.orders.functions.payment_handlers.commit_reservation",
            new=AsyncMock(),
        ),
    ):
        await handle_payment_succeeded(session, order_repo, order.id, _event())

    payment_repo.create.assert_awaited_once_with(
        order_id=order.id,
        provider="stripe",
        provider_reference="pi_test_123",
        amount=2599,
        currency="EUR",
        status="succeeded",
    )
