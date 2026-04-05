"""
Integration tests for the Admin API (Phase 2).

These tests run against the actual running API and database.
Make sure the Docker containers are running before executing:

    docker-compose -f docker-compose.dev.yml up -d

Endpoints covered:
    GET    /v1/admin/orders/                    — list_orders
    GET    /v1/admin/orders/pick-list           — get_pick_list
    GET    /v1/admin/orders/{id}                — get_order_detail
    PATCH  /v1/admin/orders/{id}/status         — override_order_status
    GET    /v1/admin/orders/{id}/packing-slip   — get_packing_slip
    POST   /v1/admin/orders/{id}/shipments      — create_order_shipment
    POST   /v1/admin/orders/{id}/ship           — ship_order

Auth note:
    The dev-only X-Admin-Key header is accepted with any non-empty value.
    Tests send "test-admin-key" as the header value.

DB note:
    All fixtures insert data directly via docker psql (same approach as
    test_orders_integration.py) since there is no customer REST API yet.
    FK cascade on orders.customer_id automatically cleans up orders when
    the customer fixture is torn down.
"""

import subprocess
import uuid
import os

import pytest
import requests

_BASE = os.getenv("TEST_API_URL", "http://localhost:8000")
ADMIN_URL = f"{_BASE}/v1/admin/orders"
ORDERS_URL = f"{_BASE}/v1/orders"
ITEMS_URL = f"{_BASE}/v1/items"

_ADMIN_HEADERS = {"X-Admin-Key": "test-admin-key"}


# ---------------------------------------------------------------------------
# DB helper — direct psql access
# ---------------------------------------------------------------------------


def _psql(sql: str) -> None:
    """Execute a SQL statement inside the running Postgres container."""
    subprocess.run(
        [
            "docker",
            "exec",
            "opentaberna-db",
            "psql",
            "-U",
            "opentaberna",
            "-d",
            "opentaberna",
            "-c",
            sql,
        ],
        check=True,
        capture_output=True,
    )


# ---------------------------------------------------------------------------
# Module-scoped fixtures — customer + catalogue item
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def admin_customer():
    """
    Insert a customer row used by all admin integration tests.

    The customer_id is also the value we pass in X-Customer-ID when creating
    orders on behalf of this customer.
    """
    customer_id = str(uuid.uuid4())
    unique = uuid.uuid4().hex[:8]
    _psql(
        f"INSERT INTO customers (id, keycloak_user_id, email, first_name, last_name) "
        f"VALUES ('{customer_id}', 'kc-admin-{unique}', '{unique}@admin-test.example', "
        f"'Admin', 'Tester');"
    )
    yield customer_id
    _psql(f"DELETE FROM customers WHERE id = '{customer_id}';")


@pytest.fixture(scope="module")
def admin_catalogue_item():
    """Create a catalogue item to use in admin integration test orders."""
    unique = uuid.uuid4().hex[:8].upper()
    payload = {
        "sku": f"ADM-TEST-{unique}",
        "status": "active",
        "name": "Admin Integration Test Product",
        "slug": f"adm-test-{unique.lower()}",
        "short_description": "Used by admin integration tests",
        "description": "Temporary product for test_admin_integration.py",
        "brand": "AdminBrand",
        "categories": [str(uuid.uuid4())],
        "price": {
            "amount": 2500,
            "currency": "EUR",
            "includes_tax": True,
            "original_amount": None,
            "tax_class": "standard",
        },
        "media": {"main_image": None, "gallery": []},
        "inventory": {
            "stock_quantity": 100,
            "stock_status": "in_stock",
            "allow_backorder": False,
        },
        "shipping": {
            "is_physical": True,
            "shipping_class": "standard",
            "weight": None,
            "dimensions": None,
        },
        "attributes": {},
        "identifiers": {
            "barcode": None,
            "manufacturer_part_number": None,
            "country_of_origin": None,
        },
        "custom": {},
        "system": {"version": 1, "source": "api", "locale": "en_US"},
    }
    response = requests.post(ITEMS_URL + "/", json=payload)
    assert response.status_code == 201, (
        f"admin_catalogue_item fixture failed: {response.status_code} {response.json()}"
    )
    item = response.json()
    yield item
    requests.delete(f"{ITEMS_URL}/{item['uuid']}")


# ---------------------------------------------------------------------------
# Function-scoped fixture — fresh draft order
# ---------------------------------------------------------------------------


@pytest.fixture
def admin_draft_order(admin_customer, admin_catalogue_item):
    """
    Create a fresh DRAFT order before each test and soft-cancel it after.

    The X-Customer-ID header is used so the orders service stores the correct
    customer_id (FK constraint on orders.customer_id → customers.id).
    """
    payload = {
        "items": [{"sku": admin_catalogue_item["sku"], "quantity": 1}],
        "currency": "EUR",
    }
    headers = {"X-Customer-ID": admin_customer}
    response = requests.post(ORDERS_URL + "/", json=payload, headers=headers)
    assert response.status_code == 201, (
        f"admin_draft_order fixture failed: {response.status_code} {response.json()}"
    )
    order = response.json()
    yield order
    # Soft-cancel if still in draft so the row is cleaned up
    if order.get("status") == "draft":
        requests.delete(f"{ORDERS_URL}/{order['id']}", headers=headers)


@pytest.fixture
def admin_paid_order(admin_customer, admin_catalogue_item):
    """
    Create a DRAFT order and advance it to PAID directly via SQL.

    Phase 1 checkout requires Stripe, so we bypass it here by inserting a
    payment record and patching the order status straight to PAID — the same
    way our webhook handler would.  This gives admin endpoint tests a realistic
    PAID order without requiring a live Stripe key.

    Also inserts an inventory_items + stock_reservations row so the inventory
    FK constraints are satisfied if present.
    """
    # 1. Create draft order via the API (validates SKU, creates order_items)
    payload = {
        "items": [{"sku": admin_catalogue_item["sku"], "quantity": 1}],
        "currency": "EUR",
    }
    headers = {"X-Customer-ID": admin_customer}
    resp = requests.post(ORDERS_URL + "/", json=payload, headers=headers)
    assert resp.status_code == 201
    order = resp.json()
    order_id = order["id"]

    # 2. Patch order status to PAID directly (bypass Stripe for tests)
    _psql(f"UPDATE orders SET status = 'paid' WHERE id = '{order_id}';")

    # 3. Insert a matching payment record
    payment_id = str(uuid.uuid4())
    _psql(
        f"INSERT INTO payments (id, order_id, provider, provider_reference, amount, currency, status) "
        f"VALUES ('{payment_id}', '{order_id}', 'stripe', 'pi_test_{uuid.uuid4().hex}', "
        f"2500, 'EUR', 'succeeded');"
    )

    order["status"] = "paid"
    yield order

    # Teardown: remove RESTRICT-FK rows first so the customer cascade can delete the order.
    # payments.order_id and shipments.order_id both use RESTRICT — they must be removed
    # before the customer fixture's DELETE FROM customers cascades through orders.
    _psql(f"DELETE FROM shipments WHERE order_id = '{order_id}';")
    _psql(f"DELETE FROM payments WHERE order_id = '{order_id}';")


# ---------------------------------------------------------------------------
# TestAdminAuthGuard
# ---------------------------------------------------------------------------


class TestAdminAuthGuard:
    """Every admin endpoint must return 403 without the X-Admin-Key header."""

    def test_list_orders_requires_admin(self):
        response = requests.get(ADMIN_URL + "/")
        assert response.status_code == 403

    def test_pick_list_requires_admin(self):
        response = requests.get(ADMIN_URL + "/pick-list")
        assert response.status_code == 403

    def test_get_order_detail_requires_admin(self):
        response = requests.get(f"{ADMIN_URL}/{uuid.uuid4()}")
        assert response.status_code == 403

    def test_status_override_requires_admin(self):
        response = requests.patch(
            f"{ADMIN_URL}/{uuid.uuid4()}/status",
            json={"status": "paid", "reason": "test"},
        )
        assert response.status_code == 403

    def test_packing_slip_requires_admin(self):
        response = requests.get(f"{ADMIN_URL}/{uuid.uuid4()}/packing-slip")
        assert response.status_code == 403

    def test_create_shipment_requires_admin(self):
        response = requests.post(
            f"{ADMIN_URL}/{uuid.uuid4()}/shipments",
            json={"carrier": "manual"},
        )
        assert response.status_code == 403

    def test_ship_order_requires_admin(self):
        response = requests.post(f"{ADMIN_URL}/{uuid.uuid4()}/ship")
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# TestAdminListOrders
# ---------------------------------------------------------------------------


class TestAdminListOrders:
    """GET /v1/admin/orders/"""

    def test_returns_200_with_admin_key(self, admin_draft_order):
        response = requests.get(ADMIN_URL + "/", headers=_ADMIN_HEADERS)
        assert response.status_code == 200

    def test_response_has_pagination_fields(self, admin_draft_order):
        response = requests.get(ADMIN_URL + "/", headers=_ADMIN_HEADERS)
        data = response.json()
        assert "orders" in data
        assert "total" in data
        assert "skip" in data
        assert "limit" in data

    def test_total_is_integer(self, admin_draft_order):
        response = requests.get(ADMIN_URL + "/", headers=_ADMIN_HEADERS)
        assert isinstance(response.json()["total"], int)

    def test_created_order_appears_in_list(self, admin_draft_order):
        response = requests.get(ADMIN_URL + "/", headers=_ADMIN_HEADERS)
        order_ids = [o["id"] for o in response.json()["orders"]]
        assert admin_draft_order["id"] in order_ids

    def test_status_filter_draft_only(self, admin_draft_order):
        response = requests.get(
            ADMIN_URL + "/", headers=_ADMIN_HEADERS, params={"status": "draft"}
        )
        assert response.status_code == 200
        for order in response.json()["orders"]:
            assert order["status"] == "draft"

    def test_status_filter_excludes_other_statuses(self, admin_draft_order):
        response = requests.get(
            ADMIN_URL + "/", headers=_ADMIN_HEADERS, params={"status": "shipped"}
        )
        assert response.status_code == 200
        for order in response.json()["orders"]:
            assert order["status"] == "shipped"

    def test_invalid_status_returns_422(self):
        response = requests.get(
            ADMIN_URL + "/", headers=_ADMIN_HEADERS, params={"status": "not_a_status"}
        )
        assert response.status_code == 422

    def test_pagination_skip_and_limit(self, admin_draft_order):
        response = requests.get(
            ADMIN_URL + "/", headers=_ADMIN_HEADERS, params={"skip": 0, "limit": 2}
        )
        data = response.json()
        assert data["skip"] == 0
        assert data["limit"] == 2
        assert len(data["orders"]) <= 2


# ---------------------------------------------------------------------------
# TestAdminGetOrderDetail
# ---------------------------------------------------------------------------


class TestAdminGetOrderDetail:
    """GET /v1/admin/orders/{id}"""

    def test_returns_200_for_existing_order(self, admin_draft_order):
        response = requests.get(
            f"{ADMIN_URL}/{admin_draft_order['id']}", headers=_ADMIN_HEADERS
        )
        assert response.status_code == 200

    def test_response_has_all_required_fields(self, admin_draft_order):
        response = requests.get(
            f"{ADMIN_URL}/{admin_draft_order['id']}", headers=_ADMIN_HEADERS
        )
        data = response.json()
        assert "id" in data
        assert "status" in data
        assert "total_amount" in data
        assert "currency" in data
        assert "items" in data
        assert "customer" in data
        assert "shipping_address" in data
        assert "payment" in data
        assert "shipment" in data

    def test_correct_order_id_returned(self, admin_draft_order):
        response = requests.get(
            f"{ADMIN_URL}/{admin_draft_order['id']}", headers=_ADMIN_HEADERS
        )
        assert response.json()["id"] == admin_draft_order["id"]

    def test_customer_populated(self, admin_draft_order, admin_customer):
        response = requests.get(
            f"{ADMIN_URL}/{admin_draft_order['id']}", headers=_ADMIN_HEADERS
        )
        customer = response.json()["customer"]
        assert customer is not None
        assert customer["id"] == admin_customer

    def test_not_found_returns_404(self):
        response = requests.get(f"{ADMIN_URL}/{uuid.uuid4()}", headers=_ADMIN_HEADERS)
        assert response.status_code == 404

    def test_invalid_uuid_returns_422(self):
        response = requests.get(f"{ADMIN_URL}/not-a-uuid", headers=_ADMIN_HEADERS)
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# TestAdminStatusOverride
# ---------------------------------------------------------------------------


class TestAdminStatusOverride:
    """PATCH /v1/admin/orders/{id}/status"""

    def test_overrides_status_successfully(self, admin_draft_order):
        payload = {"status": "cancelled", "reason": "Integration test override"}
        response = requests.patch(
            f"{ADMIN_URL}/{admin_draft_order['id']}/status",
            json=payload,
            headers=_ADMIN_HEADERS,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"

    def test_response_contains_updated_status(self, admin_draft_order):
        payload = {"status": "cancelled", "reason": "Test"}
        response = requests.patch(
            f"{ADMIN_URL}/{admin_draft_order['id']}/status",
            json=payload,
            headers=_ADMIN_HEADERS,
        )
        data = response.json()
        assert data["status"] == "cancelled"
        assert "id" in data

    def test_not_found_returns_404(self):
        payload = {"status": "paid", "reason": "Test"}
        response = requests.patch(
            f"{ADMIN_URL}/{uuid.uuid4()}/status",
            json=payload,
            headers=_ADMIN_HEADERS,
        )
        assert response.status_code == 404

    def test_missing_reason_returns_422(self, admin_draft_order):
        response = requests.patch(
            f"{ADMIN_URL}/{admin_draft_order['id']}/status",
            json={"status": "paid"},
            headers=_ADMIN_HEADERS,
        )
        assert response.status_code == 422

    def test_missing_status_returns_422(self, admin_draft_order):
        response = requests.patch(
            f"{ADMIN_URL}/{admin_draft_order['id']}/status",
            json={"reason": "some reason"},
            headers=_ADMIN_HEADERS,
        )
        assert response.status_code == 422

    def test_invalid_status_value_returns_422(self, admin_draft_order):
        response = requests.patch(
            f"{ADMIN_URL}/{admin_draft_order['id']}/status",
            json={"status": "flying", "reason": "Test"},
            headers=_ADMIN_HEADERS,
        )
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# TestAdminPackingSlip
# ---------------------------------------------------------------------------


class TestAdminPackingSlip:
    """GET /v1/admin/orders/{id}/packing-slip"""

    def test_returns_html_content_type(self, admin_draft_order):
        response = requests.get(
            f"{ADMIN_URL}/{admin_draft_order['id']}/packing-slip",
            headers=_ADMIN_HEADERS,
        )
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_html_contains_order_id(self, admin_draft_order):
        response = requests.get(
            f"{ADMIN_URL}/{admin_draft_order['id']}/packing-slip",
            headers=_ADMIN_HEADERS,
        )
        assert admin_draft_order["id"] in response.text

    def test_html_contains_sku(self, admin_draft_order, admin_catalogue_item):
        response = requests.get(
            f"{ADMIN_URL}/{admin_draft_order['id']}/packing-slip",
            headers=_ADMIN_HEADERS,
        )
        assert admin_catalogue_item["sku"] in response.text

    def test_not_found_returns_404(self):
        response = requests.get(
            f"{ADMIN_URL}/{uuid.uuid4()}/packing-slip", headers=_ADMIN_HEADERS
        )
        assert response.status_code == 404

    def test_invalid_uuid_returns_422(self):
        response = requests.get(
            f"{ADMIN_URL}/not-a-uuid/packing-slip", headers=_ADMIN_HEADERS
        )
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# TestAdminPickList
# ---------------------------------------------------------------------------


class TestAdminPickList:
    """GET /v1/admin/orders/pick-list"""

    def test_returns_html_content_type(self):
        response = requests.get(ADMIN_URL + "/pick-list", headers=_ADMIN_HEADERS)
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_html_contains_pick_list_heading(self):
        response = requests.get(ADMIN_URL + "/pick-list", headers=_ADMIN_HEADERS)
        assert "Pick List" in response.text

    def test_responds_even_when_no_paid_orders(self):
        """Pick list must render without error even if no PAID orders exist."""
        response = requests.get(ADMIN_URL + "/pick-list", headers=_ADMIN_HEADERS)
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# TestAdminCreateShipment
# ---------------------------------------------------------------------------


class TestAdminCreateShipment:
    """POST /v1/admin/orders/{id}/shipments"""

    def test_creates_shipment_on_paid_order(self, admin_paid_order):
        payload = {"carrier": "manual", "tracking_number": "TRACK-IT-001"}
        response = requests.post(
            f"{ADMIN_URL}/{admin_paid_order['id']}/shipments",
            json=payload,
            headers=_ADMIN_HEADERS,
        )
        assert response.status_code == 201

    def test_order_status_becomes_ready_to_ship(self, admin_paid_order):
        payload = {"carrier": "manual", "tracking_number": "TRACK-IT-002"}
        response = requests.post(
            f"{ADMIN_URL}/{admin_paid_order['id']}/shipments",
            json=payload,
            headers=_ADMIN_HEADERS,
        )
        assert response.json()["status"] == "ready_to_ship"

    def test_shipment_is_in_response(self, admin_paid_order):
        payload = {"carrier": "manual", "tracking_number": "TRACK-IT-003"}
        response = requests.post(
            f"{ADMIN_URL}/{admin_paid_order['id']}/shipments",
            json=payload,
            headers=_ADMIN_HEADERS,
        )
        shipment = response.json()["shipment"]
        assert shipment is not None
        assert shipment["tracking_number"] == "TRACK-IT-003"
        assert shipment["carrier"] == "manual"

    def test_not_found_returns_404(self):
        response = requests.post(
            f"{ADMIN_URL}/{uuid.uuid4()}/shipments",
            json={"carrier": "manual"},
            headers=_ADMIN_HEADERS,
        )
        assert response.status_code == 404

    def test_draft_order_returns_400(self, admin_draft_order):
        """Only PAID orders can receive a shipment — DRAFT must return 400."""
        response = requests.post(
            f"{ADMIN_URL}/{admin_draft_order['id']}/shipments",
            json={"carrier": "manual"},
            headers=_ADMIN_HEADERS,
        )
        assert response.status_code == 400

    def test_duplicate_shipment_returns_400(self, admin_paid_order):
        """Creating a second shipment on the same order must return 400."""
        payload = {"carrier": "manual", "tracking_number": "FIRST-SHIP"}
        first = requests.post(
            f"{ADMIN_URL}/{admin_paid_order['id']}/shipments",
            json=payload,
            headers=_ADMIN_HEADERS,
        )
        assert first.status_code == 201

        second = requests.post(
            f"{ADMIN_URL}/{admin_paid_order['id']}/shipments",
            json={"carrier": "manual", "tracking_number": "SECOND-SHIP"},
            headers=_ADMIN_HEADERS,
        )
        assert second.status_code == 400

    def test_invalid_uuid_returns_422(self):
        response = requests.post(
            f"{ADMIN_URL}/not-a-uuid/shipments",
            json={"carrier": "manual"},
            headers=_ADMIN_HEADERS,
        )
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# TestAdminShipOrder
# ---------------------------------------------------------------------------


class TestAdminShipOrder:
    """POST /v1/admin/orders/{id}/ship"""

    @pytest.fixture
    def ready_to_ship_order(self, admin_paid_order):
        """Advance a PAID order to READY_TO_SHIP by creating a shipment first."""
        payload = {"carrier": "manual", "tracking_number": "SHIP-ME-NOW"}
        response = requests.post(
            f"{ADMIN_URL}/{admin_paid_order['id']}/shipments",
            json=payload,
            headers=_ADMIN_HEADERS,
        )
        assert response.status_code == 201
        return response.json()

    def test_marks_order_as_shipped(self, ready_to_ship_order):
        response = requests.post(
            f"{ADMIN_URL}/{ready_to_ship_order['id']}/ship",
            headers=_ADMIN_HEADERS,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "shipped"

    def test_response_has_shipment(self, ready_to_ship_order):
        response = requests.post(
            f"{ADMIN_URL}/{ready_to_ship_order['id']}/ship",
            headers=_ADMIN_HEADERS,
        )
        assert response.json()["shipment"] is not None

    def test_not_found_returns_404(self):
        response = requests.post(
            f"{ADMIN_URL}/{uuid.uuid4()}/ship", headers=_ADMIN_HEADERS
        )
        assert response.status_code == 404

    def test_paid_order_without_shipment_returns_400(self, admin_paid_order):
        """An order in PAID (not READY_TO_SHIP) status must return 400."""
        response = requests.post(
            f"{ADMIN_URL}/{admin_paid_order['id']}/ship", headers=_ADMIN_HEADERS
        )
        assert response.status_code == 400

    def test_invalid_uuid_returns_422(self):
        response = requests.post(f"{ADMIN_URL}/not-a-uuid/ship", headers=_ADMIN_HEADERS)
        assert response.status_code == 422


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
