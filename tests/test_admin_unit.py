"""
Unit tests for the Admin service — pure business logic, no DB, no network.

Covers:
    - AdminCreateShipmentRequest / AdminStatusOverrideRequest — Pydantic validation
    - PickListItem / PickListResponse                         — schema fields
    - db_to_order_response()                                  — ORM-mock → schema
    - db_to_admin_order_detail_response()                     — full admin detail assembly
    - build_pick_list()                                       — aggregation logic
    - render_packing_slip()                                   — HTML contains key fields
    - render_pick_list_html()                                 — HTML contains key fields
    - send_tracking_email() — skips when smtp_host is empty
    - _build_plain_text() / _build_html()                     — email body content
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.services.admin.functions.admin_transformations import (
    db_to_admin_order_detail_response,
    db_to_order_response,
)
from app.services.admin.functions.packing_documents import (
    build_pick_list,
    render_packing_slip,
    render_pick_list_html,
)
from app.services.admin.functions.send_tracking_email import (
    _build_html,
    _build_plain_text,
    send_tracking_email,
)
from app.services.admin.models.admin_models import (
    AdminCreateShipmentRequest,
    AdminOrderDetailResponse,
    AdminStatusOverrideRequest,
    PickListItem,
    PickListResponse,
)
from app.services.orders.models.orders_models import OrderResponse, OrderStatus
from app.services.shipments.models.shipments_models import Carrier


# ---------------------------------------------------------------------------
# Mock factories — lightweight stand-ins for SQLAlchemy model instances
# ---------------------------------------------------------------------------


def _make_order(
    status: OrderStatus = OrderStatus.DRAFT,
    customer_id: UUID | None = None,
    total_amount: int = 4999,
    currency: str = "EUR",
) -> MagicMock:
    """Return a mock that behaves like an OrderDB row."""
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
    order_id: UUID,
    sku: str = "SKU-001",
    quantity: int = 2,
    unit_price: int = 999,
) -> MagicMock:
    """Return a mock that behaves like an OrderItemDB row."""
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


def _make_customer(email: str = "customer@example.com") -> MagicMock:
    """Return a mock that behaves like a CustomerDB row."""
    now = datetime.now(UTC)
    c = MagicMock()
    c.id = uuid4()
    c.keycloak_user_id = "kc-" + uuid4().hex[:8]
    c.email = email
    c.first_name = "Jane"
    c.last_name = "Doe"
    c.created_at = now
    c.updated_at = now
    return c


def _make_address(customer_id: UUID | None = None) -> MagicMock:
    """Return a mock that behaves like an AddressDB row."""
    now = datetime.now(UTC)
    a = MagicMock()
    a.id = uuid4()
    a.customer_id = customer_id or uuid4()
    a.street = "Musterstraße 1"
    a.city = "Berlin"
    a.zip_code = "10115"
    a.country = "DE"
    a.is_default = True
    a.created_at = now
    a.updated_at = now
    return a


def _make_payment(order_id: UUID | None = None) -> MagicMock:
    """Return a mock that behaves like a PaymentDB row."""
    now = datetime.now(UTC)
    p = MagicMock()
    p.id = uuid4()
    p.order_id = order_id or uuid4()
    p.provider = "stripe"
    p.provider_reference = "pi_" + uuid4().hex
    p.amount = 4999
    p.currency = "EUR"
    p.status = "succeeded"
    p.created_at = now
    p.updated_at = now
    return p


def _make_shipment(
    order_id: UUID | None = None, tracking_number: str = "DE123456789"
) -> MagicMock:
    """Return a mock that behaves like a ShipmentDB row."""
    now = datetime.now(UTC)
    s = MagicMock()
    s.id = uuid4()
    s.order_id = order_id or uuid4()
    s.carrier = "manual"
    s.tracking_number = tracking_number
    s.label_url = None
    s.label_format = None
    s.status = "pending"
    s.created_at = now
    s.updated_at = now
    return s


def _make_settings(smtp_host: str = "") -> MagicMock:
    """Return a mock Settings object."""
    s = MagicMock()
    s.smtp_host = smtp_host
    s.smtp_port = 587
    s.smtp_user = "user@example.com"
    s.smtp_password = "secret"
    s.email_from = "noreply@opentaberna.local"
    return s


# ---------------------------------------------------------------------------
# AdminCreateShipmentRequest — Pydantic validation
# ---------------------------------------------------------------------------


class TestAdminCreateShipmentRequest:
    """Input validation for the create-shipment request schema."""

    def test_defaults_to_manual_carrier(self):
        req = AdminCreateShipmentRequest()
        assert req.carrier == Carrier.MANUAL

    def test_accepts_tracking_number(self):
        req = AdminCreateShipmentRequest(tracking_number="DE123456789")
        assert req.tracking_number == "DE123456789"

    def test_tracking_number_defaults_to_none(self):
        req = AdminCreateShipmentRequest()
        assert req.tracking_number is None

    def test_accepts_dhl_carrier(self):
        req = AdminCreateShipmentRequest(carrier=Carrier.DHL)
        assert req.carrier == Carrier.DHL

    def test_empty_tracking_number_rejected(self):
        with pytest.raises(Exception):
            AdminCreateShipmentRequest(tracking_number="")

    def test_tracking_number_too_long_rejected(self):
        with pytest.raises(Exception):
            AdminCreateShipmentRequest(tracking_number="X" * 101)


# ---------------------------------------------------------------------------
# AdminStatusOverrideRequest — Pydantic validation
# ---------------------------------------------------------------------------


class TestAdminStatusOverrideRequest:
    """Input validation for the status-override request schema."""

    def test_valid_request(self):
        req = AdminStatusOverrideRequest(
            status=OrderStatus.PAID,
            reason="Correcting a webhook delivery failure",
        )
        assert req.status == OrderStatus.PAID
        assert req.reason == "Correcting a webhook delivery failure"

    def test_reason_is_required(self):
        with pytest.raises(Exception):
            AdminStatusOverrideRequest(status=OrderStatus.PAID)

    def test_empty_reason_rejected(self):
        with pytest.raises(Exception):
            AdminStatusOverrideRequest(status=OrderStatus.PAID, reason="")

    def test_reason_too_long_rejected(self):
        with pytest.raises(Exception):
            AdminStatusOverrideRequest(status=OrderStatus.PAID, reason="X" * 501)

    def test_status_is_required(self):
        with pytest.raises(Exception):
            AdminStatusOverrideRequest(reason="some reason")


# ---------------------------------------------------------------------------
# db_to_order_response
# ---------------------------------------------------------------------------


class TestDbToOrderResponse:
    """ORM mock → OrderResponse (list-view) conversion."""

    def test_maps_scalar_fields(self):
        order = _make_order(OrderStatus.PAID, total_amount=9999, currency="USD")
        result = db_to_order_response(order)

        assert result.id == order.id
        assert result.customer_id == order.customer_id
        assert result.status == OrderStatus.PAID
        assert result.total_amount == 9999
        assert result.currency == "USD"

    def test_returns_order_response_type(self):
        order = _make_order()
        result = db_to_order_response(order)
        assert isinstance(result, OrderResponse)

    def test_deleted_at_is_propagated(self):
        order = _make_order()
        order.deleted_at = datetime.now(UTC)
        result = db_to_order_response(order)
        assert result.deleted_at is not None


# ---------------------------------------------------------------------------
# db_to_admin_order_detail_response
# ---------------------------------------------------------------------------


class TestDbToAdminOrderDetailResponse:
    """Assembly of AdminOrderDetailResponse from independently-fetched DB mocks."""

    def test_maps_order_fields(self):
        order = _make_order(OrderStatus.PAID, total_amount=4999, currency="EUR")
        result = db_to_admin_order_detail_response(order, [], None, None, None, None)

        assert result.id == order.id
        assert result.status == OrderStatus.PAID
        assert result.total_amount == 4999

    def test_maps_items(self):
        order = _make_order()
        item = _make_order_item(order.id, sku="SKU-X", quantity=3, unit_price=500)
        result = db_to_admin_order_detail_response(
            order, [item], None, None, None, None
        )

        assert len(result.items) == 1
        assert result.items[0].sku == "SKU-X"
        assert result.items[0].quantity == 3

    def test_customer_is_none_when_not_provided(self):
        order = _make_order()
        result = db_to_admin_order_detail_response(order, [], None, None, None, None)
        assert result.customer is None

    def test_customer_is_mapped_when_provided(self):
        order = _make_order()
        customer = _make_customer("jane@example.com")
        result = db_to_admin_order_detail_response(
            order, [], customer, None, None, None
        )

        assert result.customer is not None
        assert result.customer.email == "jane@example.com"
        assert result.customer.first_name == "Jane"

    def test_shipping_address_is_none_when_not_provided(self):
        order = _make_order()
        result = db_to_admin_order_detail_response(order, [], None, None, None, None)
        assert result.shipping_address is None

    def test_shipping_address_is_mapped_when_provided(self):
        order = _make_order()
        address = _make_address()
        result = db_to_admin_order_detail_response(order, [], None, address, None, None)

        assert result.shipping_address is not None
        assert result.shipping_address.street == "Musterstraße 1"
        assert result.shipping_address.city == "Berlin"

    def test_payment_is_none_when_not_provided(self):
        order = _make_order()
        result = db_to_admin_order_detail_response(order, [], None, None, None, None)
        assert result.payment is None

    def test_payment_is_mapped_when_provided(self):
        order = _make_order()
        payment = _make_payment(order.id)
        result = db_to_admin_order_detail_response(order, [], None, None, payment, None)

        assert result.payment is not None
        assert result.payment.status.value == "succeeded"

    def test_shipment_is_none_when_not_provided(self):
        order = _make_order()
        result = db_to_admin_order_detail_response(order, [], None, None, None, None)
        assert result.shipment is None

    def test_shipment_is_mapped_when_provided(self):
        order = _make_order()
        shipment = _make_shipment(order.id, tracking_number="DE9999")
        result = db_to_admin_order_detail_response(
            order, [], None, None, None, shipment
        )

        assert result.shipment is not None
        assert result.shipment.tracking_number == "DE9999"

    def test_returns_admin_order_detail_response_type(self):
        order = _make_order()
        result = db_to_admin_order_detail_response(order, [], None, None, None, None)
        assert isinstance(result, AdminOrderDetailResponse)

    def test_all_related_entities_populated(self):
        order = _make_order(OrderStatus.PAID)
        item = _make_order_item(order.id)
        customer = _make_customer()
        address = _make_address(customer.id)
        payment = _make_payment(order.id)
        shipment = _make_shipment(order.id)

        result = db_to_admin_order_detail_response(
            order, [item], customer, address, payment, shipment
        )

        assert result.customer is not None
        assert result.shipping_address is not None
        assert result.payment is not None
        assert result.shipment is not None
        assert len(result.items) == 1


# ---------------------------------------------------------------------------
# build_pick_list
# ---------------------------------------------------------------------------


class TestBuildPickList:
    """Aggregation logic for the batch pick list."""

    def test_empty_orders_returns_empty_list(self):
        result = build_pick_list([], [])
        assert result.items == []
        assert result.order_ids == []

    def test_single_order_single_sku(self):
        order = _make_order(OrderStatus.PAID)
        item = _make_order_item(order.id, sku="SKU-A", quantity=3)
        result = build_pick_list([order], [item])

        assert len(result.items) == 1
        assert result.items[0].sku == "SKU-A"
        assert result.items[0].total_quantity == 3
        assert result.items[0].order_count == 1

    def test_two_orders_same_sku_quantities_sum(self):
        order1 = _make_order(OrderStatus.PAID)
        order2 = _make_order(OrderStatus.PAID)
        item1 = _make_order_item(order1.id, sku="SKU-A", quantity=2)
        item2 = _make_order_item(order2.id, sku="SKU-A", quantity=5)
        result = build_pick_list([order1, order2], [item1, item2])

        assert len(result.items) == 1
        assert result.items[0].total_quantity == 7
        assert result.items[0].order_count == 2

    def test_two_skus_are_sorted_alphabetically(self):
        order = _make_order(OrderStatus.PAID)
        item_b = _make_order_item(order.id, sku="SKU-B", quantity=1)
        item_a = _make_order_item(order.id, sku="SKU-A", quantity=2)
        result = build_pick_list([order], [item_b, item_a])

        assert result.items[0].sku == "SKU-A"
        assert result.items[1].sku == "SKU-B"

    def test_order_ids_are_included(self):
        order = _make_order(OrderStatus.PAID)
        result = build_pick_list([order], [])
        assert order.id in result.order_ids

    def test_generated_at_is_set(self):
        result = build_pick_list([], [])
        assert result.generated_at is not None

    def test_same_sku_across_three_orders_order_count_is_three(self):
        orders = [_make_order(OrderStatus.PAID) for _ in range(3)]
        items = [_make_order_item(o.id, sku="SKU-X", quantity=1) for o in orders]
        result = build_pick_list(orders, items)

        assert result.items[0].order_count == 3

    def test_multiple_skus_per_order(self):
        order = _make_order(OrderStatus.PAID)
        items = [
            _make_order_item(order.id, sku="SKU-A", quantity=1),
            _make_order_item(order.id, sku="SKU-B", quantity=2),
            _make_order_item(order.id, sku="SKU-C", quantity=3),
        ]
        result = build_pick_list([order], items)

        assert len(result.items) == 3
        total_qty = sum(i.total_quantity for i in result.items)
        assert total_qty == 6


# ---------------------------------------------------------------------------
# render_packing_slip
# ---------------------------------------------------------------------------


class TestRenderPackingSlip:
    """HTML packing slip content validation."""

    def test_contains_order_id(self):
        order = _make_order()
        html = render_packing_slip(order, [], None, None, None)
        assert str(order.id) in html

    def test_contains_sku_when_items_present(self):
        order = _make_order()
        item = _make_order_item(order.id, sku="MY-SKU-001", quantity=2, unit_price=1000)
        html = render_packing_slip(order, [item], None, None, None)
        assert "MY-SKU-001" in html

    def test_contains_customer_name_when_customer_provided(self):
        order = _make_order()
        customer = _make_customer()
        customer.first_name = "Ada"
        customer.last_name = "Lovelace"
        html = render_packing_slip(order, [], customer, None, None)
        assert "Ada" in html
        assert "Lovelace" in html

    def test_shows_dash_when_no_customer(self):
        order = _make_order()
        html = render_packing_slip(order, [], None, None, None)
        assert "—" in html

    def test_contains_tracking_number_when_shipment_provided(self):
        order = _make_order()
        shipment = _make_shipment(order.id, tracking_number="TRACK-99")
        html = render_packing_slip(order, [], None, None, shipment)
        assert "TRACK-99" in html

    def test_contains_address_when_provided(self):
        order = _make_order()
        address = _make_address()
        html = render_packing_slip(order, [], None, address, None)
        assert "Musterstraße 1" in html
        assert "Berlin" in html

    def test_is_valid_html(self):
        order = _make_order()
        html = render_packing_slip(order, [], None, None, None)
        assert "<!DOCTYPE html>" in html
        assert "<html" in html
        assert "</html>" in html

    def test_contains_line_total(self):
        order = _make_order(currency="EUR")
        item = _make_order_item(order.id, sku="SKU-A", quantity=2, unit_price=1000)
        html = render_packing_slip(order, [item], None, None, None)
        # 2 × 10.00 = 20.00
        assert "20.00" in html


# ---------------------------------------------------------------------------
# render_pick_list_html
# ---------------------------------------------------------------------------


class TestRenderPickListHtml:
    """HTML pick list content validation."""

    def test_contains_sku(self):
        pick_list = PickListResponse(
            items=[PickListItem(sku="SKU-Z", total_quantity=5, order_count=2)],
            order_ids=[uuid4()],
            generated_at=datetime.now(UTC),
        )
        html = render_pick_list_html(pick_list)
        assert "SKU-Z" in html

    def test_contains_total_quantity(self):
        pick_list = PickListResponse(
            items=[PickListItem(sku="SKU-A", total_quantity=42, order_count=3)],
            order_ids=[uuid4()],
            generated_at=datetime.now(UTC),
        )
        html = render_pick_list_html(pick_list)
        assert "42" in html

    def test_empty_pick_list_renders_without_error(self):
        pick_list = PickListResponse(
            items=[],
            order_ids=[],
            generated_at=datetime.now(UTC),
        )
        html = render_pick_list_html(pick_list)
        assert "<!DOCTYPE html>" in html

    def test_is_valid_html(self):
        pick_list = PickListResponse(
            items=[],
            order_ids=[],
            generated_at=datetime.now(UTC),
        )
        html = render_pick_list_html(pick_list)
        assert "<html" in html
        assert "</html>" in html

    def test_contains_pick_list_heading(self):
        pick_list = PickListResponse(
            items=[],
            order_ids=[],
            generated_at=datetime.now(UTC),
        )
        html = render_pick_list_html(pick_list)
        assert "Pick List" in html


# ---------------------------------------------------------------------------
# _build_plain_text / _build_html
# ---------------------------------------------------------------------------


class TestBuildEmailBodies:
    """Email body content validation — both plain text and HTML."""

    def test_plain_text_contains_order_id(self):
        order_id = uuid4()
        text = _build_plain_text("Jane Doe", order_id, "DE123", "manual")
        assert str(order_id) in text

    def test_plain_text_contains_customer_name(self):
        text = _build_plain_text("Jane Doe", uuid4(), None, "manual")
        assert "Jane Doe" in text

    def test_plain_text_contains_tracking_number(self):
        text = _build_plain_text("Jane", uuid4(), "TRACK-42", "dhl")
        assert "TRACK-42" in text

    def test_plain_text_shows_not_available_when_no_tracking(self):
        text = _build_plain_text("Jane", uuid4(), None, "manual")
        assert "not yet available" in text.lower()

    def test_html_contains_order_id(self):
        order_id = uuid4()
        html = _build_html("Jane Doe", order_id, "DE123", "dhl")
        assert str(order_id) in html

    def test_html_contains_tracking_number(self):
        html = _build_html("Jane", uuid4(), "TRACK-99", "dhl")
        assert "TRACK-99" in html

    def test_html_shows_not_available_when_no_tracking(self):
        html = _build_html("Jane", uuid4(), None, "manual")
        assert "Not yet available" in html

    def test_html_is_valid_structure(self):
        html = _build_html("Jane", uuid4(), None, "manual")
        assert "<!DOCTYPE html>" in html
        assert "</html>" in html


# ---------------------------------------------------------------------------
# send_tracking_email — async, SMTP interaction
# ---------------------------------------------------------------------------


class TestSendTrackingEmail:
    """Email dispatch — verifies skip-when-unconfigured and SMTP call."""

    async def test_skips_send_when_smtp_host_empty(self):
        """When smtp_host is empty, _send_via_smtp must never be called."""
        settings = _make_settings(smtp_host="")

        with patch(
            "app.services.admin.functions.send_tracking_email._send_via_smtp"
        ) as mock_send:
            await send_tracking_email(
                to_email="customer@example.com",
                customer_name="Jane Doe",
                order_id=uuid4(),
                tracking_number="DE123",
                carrier="manual",
                settings=settings,
            )
            mock_send.assert_not_called()

    async def test_calls_smtp_when_host_configured(self):
        """When smtp_host is set, _send_via_smtp must be called once."""
        settings = _make_settings(smtp_host="smtp.example.com")

        with patch(
            "app.services.admin.functions.send_tracking_email._send_via_smtp"
        ) as mock_send:
            await send_tracking_email(
                to_email="customer@example.com",
                customer_name="Jane Doe",
                order_id=uuid4(),
                tracking_number="DE123",
                carrier="manual",
                settings=settings,
            )
            mock_send.assert_called_once()

    async def test_smtp_called_with_correct_recipient(self):
        """Recipient e-mail is forwarded to _send_via_smtp unchanged."""
        settings = _make_settings(smtp_host="smtp.example.com")

        with patch(
            "app.services.admin.functions.send_tracking_email._send_via_smtp"
        ) as mock_send:
            await send_tracking_email(
                to_email="specific@example.com",
                customer_name="Jane",
                order_id=uuid4(),
                tracking_number=None,
                carrier="manual",
                settings=settings,
            )
            call_kwargs = mock_send.call_args[1]
            assert call_kwargs["to_addr"] == "specific@example.com"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
