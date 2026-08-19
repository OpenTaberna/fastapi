"""
Unit tests for the Orders service — pure business logic, no DB, no network.

Covers:
    - OrderStatus enum values
    - _ALLOWED_TRANSITIONS state-machine definition
    - validate_status_transition() — every allowed and every forbidden path
    - assert_order_owned_by()      — owner passes, non-owner raises
    - OrderCreate / OrderItemCreate — Pydantic input validation
    - CheckoutResponse              — carries client_secret alongside order fields
    - db_to_order_detail_response() — ORM-mock → schema
    - db_to_checkout_response()     — ORM-mock → schema with client_secret
"""

import pytest
from datetime import datetime, UTC
from unittest.mock import MagicMock
from uuid import UUID, uuid4

from app.services.orders.models import (
    CheckoutResponse,
    OrderCreate,
    OrderDetailResponse,
    OrderItemCreate,
    OrderStatus,
)
from app.services.orders.functions.order_validation import (
    _ALLOWED_TRANSITIONS,
    assert_order_owned_by,
    validate_status_transition,
)
from app.services.orders.functions.order_transformations import (
    db_to_checkout_response,
    db_to_order_detail_response,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_order(
    status: OrderStatus = OrderStatus.DRAFT,
    customer_id: UUID | None = None,
    total_amount: int = 4999,
    currency: str = "EUR",
) -> MagicMock:
    """Return a lightweight mock that behaves like an OrderDB row."""
    now = datetime.now(UTC)
    order = MagicMock()
    order.id = uuid4()
    order.customer_id = customer_id or uuid4()
    order.status = status.value
    order.total_amount = total_amount
    order.currency = currency
    order.created_at = now
    order.updated_at = now
    order.deleted_at = None
    return order


def _make_order_item(
    order_id: UUID, sku: str = "SKU-001", quantity: int = 2, unit_price: int = 999
) -> MagicMock:
    """Return a lightweight mock that behaves like an OrderItemDB row."""
    now = datetime.now(UTC)
    item = MagicMock()
    item.id = uuid4()
    item.order_id = order_id
    item.sku = sku
    item.quantity = quantity
    item.unit_price = unit_price
    item.created_at = now
    item.updated_at = now
    return item


# ---------------------------------------------------------------------------
# OrderStatus enum
# ---------------------------------------------------------------------------


class TestOrderStatus:
    """Enum values must match the strings stored in the DB."""

    def test_draft_value(self):
        assert OrderStatus.DRAFT == "draft"

    def test_pending_payment_value(self):
        assert OrderStatus.PENDING_PAYMENT == "pending_payment"

    def test_paid_value(self):
        assert OrderStatus.PAID == "paid"

    def test_ready_to_ship_value(self):
        assert OrderStatus.READY_TO_SHIP == "ready_to_ship"

    def test_shipped_value(self):
        assert OrderStatus.SHIPPED == "shipped"

    def test_cancelled_value(self):
        assert OrderStatus.CANCELLED == "cancelled"

    def test_all_six_statuses_exist(self):
        assert len(OrderStatus) == 6


# ---------------------------------------------------------------------------
# _ALLOWED_TRANSITIONS state-machine definition
# ---------------------------------------------------------------------------


class TestAllowedTransitions:
    """_ALLOWED_TRANSITIONS must cover all statuses and encode the correct graph."""

    def test_all_statuses_have_an_entry(self):
        for status in OrderStatus:
            assert status in _ALLOWED_TRANSITIONS, (
                f"{status} missing from _ALLOWED_TRANSITIONS"
            )

    def test_draft_allows_pending_payment_and_cancelled(self):
        assert _ALLOWED_TRANSITIONS[OrderStatus.DRAFT] == {
            OrderStatus.PENDING_PAYMENT,
            OrderStatus.CANCELLED,
        }

    def test_pending_payment_allows_paid_and_cancelled(self):
        assert _ALLOWED_TRANSITIONS[OrderStatus.PENDING_PAYMENT] == {
            OrderStatus.PAID,
            OrderStatus.CANCELLED,
        }

    def test_paid_allows_only_ready_to_ship(self):
        assert _ALLOWED_TRANSITIONS[OrderStatus.PAID] == {OrderStatus.READY_TO_SHIP}

    def test_ready_to_ship_allows_only_shipped(self):
        assert _ALLOWED_TRANSITIONS[OrderStatus.READY_TO_SHIP] == {OrderStatus.SHIPPED}

    def test_shipped_is_terminal(self):
        assert _ALLOWED_TRANSITIONS[OrderStatus.SHIPPED] == set()

    def test_cancelled_is_terminal(self):
        assert _ALLOWED_TRANSITIONS[OrderStatus.CANCELLED] == set()


# ---------------------------------------------------------------------------
# validate_status_transition — allowed paths
# ---------------------------------------------------------------------------


class TestValidateStatusTransitionAllowed:
    """Every permitted transition must not raise."""

    def test_draft_to_pending_payment(self):
        order = _make_order(OrderStatus.DRAFT)
        validate_status_transition(order, OrderStatus.PENDING_PAYMENT)  # no raise

    def test_draft_to_cancelled(self):
        order = _make_order(OrderStatus.DRAFT)
        validate_status_transition(order, OrderStatus.CANCELLED)

    def test_pending_payment_to_paid(self):
        order = _make_order(OrderStatus.PENDING_PAYMENT)
        validate_status_transition(order, OrderStatus.PAID)

    def test_pending_payment_to_cancelled(self):
        order = _make_order(OrderStatus.PENDING_PAYMENT)
        validate_status_transition(order, OrderStatus.CANCELLED)

    def test_paid_to_ready_to_ship(self):
        order = _make_order(OrderStatus.PAID)
        validate_status_transition(order, OrderStatus.READY_TO_SHIP)

    def test_ready_to_ship_to_shipped(self):
        order = _make_order(OrderStatus.READY_TO_SHIP)
        validate_status_transition(order, OrderStatus.SHIPPED)


# ---------------------------------------------------------------------------
# validate_status_transition — forbidden paths
# ---------------------------------------------------------------------------


class TestValidateStatusTransitionForbidden:
    """Every invalid transition must raise an exception."""

    def test_draft_to_paid_raises(self):
        order = _make_order(OrderStatus.DRAFT)
        with pytest.raises(Exception):
            validate_status_transition(order, OrderStatus.PAID)

    def test_draft_to_shipped_raises(self):
        order = _make_order(OrderStatus.DRAFT)
        with pytest.raises(Exception):
            validate_status_transition(order, OrderStatus.SHIPPED)

    def test_draft_to_ready_to_ship_raises(self):
        order = _make_order(OrderStatus.DRAFT)
        with pytest.raises(Exception):
            validate_status_transition(order, OrderStatus.READY_TO_SHIP)

    def test_pending_payment_to_draft_raises(self):
        order = _make_order(OrderStatus.PENDING_PAYMENT)
        with pytest.raises(Exception):
            validate_status_transition(order, OrderStatus.DRAFT)

    def test_pending_payment_to_shipped_raises(self):
        order = _make_order(OrderStatus.PENDING_PAYMENT)
        with pytest.raises(Exception):
            validate_status_transition(order, OrderStatus.SHIPPED)

    def test_paid_to_draft_raises(self):
        order = _make_order(OrderStatus.PAID)
        with pytest.raises(Exception):
            validate_status_transition(order, OrderStatus.DRAFT)

    def test_paid_to_cancelled_raises(self):
        order = _make_order(OrderStatus.PAID)
        with pytest.raises(Exception):
            validate_status_transition(order, OrderStatus.CANCELLED)

    def test_shipped_is_terminal_raises(self):
        order = _make_order(OrderStatus.SHIPPED)
        with pytest.raises(Exception):
            validate_status_transition(order, OrderStatus.CANCELLED)

    def test_cancelled_is_terminal_raises(self):
        order = _make_order(OrderStatus.CANCELLED)
        with pytest.raises(Exception):
            validate_status_transition(order, OrderStatus.DRAFT)


# ---------------------------------------------------------------------------
# assert_order_owned_by
# ---------------------------------------------------------------------------


class TestAssertOrderOwnedBy:
    """Ownership check must pass for the owner and raise for anyone else."""

    def test_owner_passes(self):
        customer_id = uuid4()
        order = _make_order(customer_id=customer_id)
        assert_order_owned_by(order, customer_id)  # no raise

    def test_non_owner_raises(self):
        order = _make_order(customer_id=uuid4())
        with pytest.raises(Exception):
            assert_order_owned_by(order, uuid4())

    def test_same_uuid_value_passes(self):
        """UUID equality is value-based, not identity-based."""
        uid_str = str(uuid4())
        order = _make_order(customer_id=UUID(uid_str))
        assert_order_owned_by(order, UUID(uid_str))  # no raise


# ---------------------------------------------------------------------------
# OrderCreate / OrderItemCreate — Pydantic validation
# ---------------------------------------------------------------------------


class TestOrderItemCreate:
    """OrderItemCreate input validation."""

    def test_valid_item(self):
        item = OrderItemCreate(sku="SKU-001", quantity=2)
        assert item.sku == "SKU-001"
        assert item.quantity == 2

    def test_quantity_zero_rejected(self):
        with pytest.raises(Exception):
            OrderItemCreate(sku="SKU-001", quantity=0)

    def test_quantity_negative_rejected(self):
        with pytest.raises(Exception):
            OrderItemCreate(sku="SKU-001", quantity=-1)

    def test_sku_empty_string_rejected(self):
        with pytest.raises(Exception):
            OrderItemCreate(sku="", quantity=1)

    def test_sku_too_long_rejected(self):
        with pytest.raises(Exception):
            OrderItemCreate(sku="X" * 101, quantity=1)


class TestOrderCreate:
    """OrderCreate input validation."""

    def test_valid_order(self):
        order = OrderCreate(items=[OrderItemCreate(sku="SKU-001", quantity=1)])
        assert len(order.items) == 1
        assert order.currency == "EUR"  # default

    def test_currency_defaults_to_eur(self):
        order = OrderCreate(items=[OrderItemCreate(sku="SKU-001", quantity=1)])
        assert order.currency == "EUR"

    def test_custom_currency_accepted(self):
        order = OrderCreate(
            items=[OrderItemCreate(sku="SKU-001", quantity=1)],
            currency="USD",
        )
        assert order.currency == "USD"

    def test_empty_items_list_rejected(self):
        with pytest.raises(Exception):
            OrderCreate(items=[])

    def test_currency_too_short_rejected(self):
        with pytest.raises(Exception):
            OrderCreate(
                items=[OrderItemCreate(sku="SKU-001", quantity=1)], currency="EU"
            )

    def test_currency_too_long_rejected(self):
        with pytest.raises(Exception):
            OrderCreate(
                items=[OrderItemCreate(sku="SKU-001", quantity=1)], currency="EURO"
            )


# ---------------------------------------------------------------------------
# CheckoutResponse — client_secret field
# ---------------------------------------------------------------------------


class TestCheckoutResponse:
    """CheckoutResponse must carry client_secret on top of order detail fields."""

    def test_has_client_secret_field(self):
        assert "client_secret" in CheckoutResponse.model_fields

    def test_client_secret_is_required(self):
        """client_secret has no default — omitting it must raise."""
        now = datetime.now(UTC)
        with pytest.raises(Exception):
            CheckoutResponse(
                id=uuid4(),
                customer_id=uuid4(),
                status=OrderStatus.PENDING_PAYMENT,
                total_amount=999,
                currency="EUR",
                created_at=now,
                updated_at=now,
                items=[],
                # client_secret intentionally omitted
            )

    def test_instantiation_with_all_fields(self):
        now = datetime.now(UTC)
        resp = CheckoutResponse(
            id=uuid4(),
            customer_id=uuid4(),
            status=OrderStatus.PENDING_PAYMENT,
            total_amount=999,
            currency="EUR",
            created_at=now,
            updated_at=now,
            items=[],
            client_secret="pi_test_secret",
        )
        assert resp.client_secret == "pi_test_secret"
        assert resp.status == OrderStatus.PENDING_PAYMENT


# ---------------------------------------------------------------------------
# db_to_order_detail_response
# ---------------------------------------------------------------------------


class TestDbToOrderDetailResponse:
    """ORM mock → OrderDetailResponse transformation."""

    def test_maps_all_scalar_fields(self):
        order = _make_order(OrderStatus.DRAFT, total_amount=1999, currency="EUR")
        result = db_to_order_detail_response(order, [])

        assert result.id == order.id
        assert result.customer_id == order.customer_id
        assert result.status == OrderStatus.DRAFT
        assert result.total_amount == 1999
        assert result.currency == "EUR"
        assert result.deleted_at is None

    def test_empty_items_list(self):
        order = _make_order()
        result = db_to_order_detail_response(order, [])
        assert result.items == []

    def test_items_are_mapped(self):
        order = _make_order()
        item = _make_order_item(order.id, sku="SKU-A", quantity=3, unit_price=500)
        result = db_to_order_detail_response(order, [item])

        assert len(result.items) == 1
        assert result.items[0].sku == "SKU-A"
        assert result.items[0].quantity == 3
        assert result.items[0].unit_price == 500

    def test_multiple_items(self):
        order = _make_order()
        items = [
            _make_order_item(order.id, sku="SKU-A", quantity=1, unit_price=100),
            _make_order_item(order.id, sku="SKU-B", quantity=2, unit_price=200),
        ]
        result = db_to_order_detail_response(order, items)
        assert len(result.items) == 2

    def test_returns_order_detail_response_type(self):
        order = _make_order()
        result = db_to_order_detail_response(order, [])
        assert isinstance(result, OrderDetailResponse)


# ---------------------------------------------------------------------------
# db_to_checkout_response
# ---------------------------------------------------------------------------


class TestDbToCheckoutResponse:
    """ORM mock → CheckoutResponse transformation including client_secret."""

    def test_maps_client_secret(self):
        order = _make_order(OrderStatus.PENDING_PAYMENT)
        result = db_to_checkout_response(order, [], "pi_test_secret_xyz")
        assert result.client_secret == "pi_test_secret_xyz"

    def test_maps_order_fields(self):
        order = _make_order(
            OrderStatus.PENDING_PAYMENT, total_amount=3999, currency="USD"
        )
        result = db_to_checkout_response(order, [], "secret")

        assert result.total_amount == 3999
        assert result.currency == "USD"
        assert result.status == OrderStatus.PENDING_PAYMENT

    def test_maps_items(self):
        order = _make_order(OrderStatus.PENDING_PAYMENT)
        item = _make_order_item(order.id, sku="SKU-X", quantity=1, unit_price=1999)
        result = db_to_checkout_response(order, [item], "secret")

        assert len(result.items) == 1
        assert result.items[0].sku == "SKU-X"

    def test_returns_checkout_response_type(self):
        order = _make_order(OrderStatus.PENDING_PAYMENT)
        result = db_to_checkout_response(order, [], "secret")
        assert isinstance(result, CheckoutResponse)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
