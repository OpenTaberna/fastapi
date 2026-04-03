"""
Integration tests for the Orders API.

These tests run against the actual running API and database.
Make sure the Docker containers are running before executing these tests:

    docker-compose -f docker-compose.dev.yml up -d

Endpoints covered:
    POST   /v1/orders/                  — create_order
    GET    /v1/orders/{id}              — get_order
    DELETE /v1/orders/{id}              — cancel_order
    POST   /v1/orders/{id}/checkout     — checkout_order

DB note:
    All tables are created automatically when the API container starts
    (Base.metadata.create_all runs in the app lifespan) — no manual migration
    step is needed.

    The one thing tests must handle explicitly is that orders.customer_id is a
    real FK → customers.id. Since there is no customer REST API yet, the
    customer and other_customer fixtures insert rows directly into the DB via
    `docker exec psql` and clean up after themselves.  The CASCADE on the FK
    means deleting the customer automatically removes any leftover orders too.
"""

import subprocess
import uuid
import os

import pytest
import requests

_BASE = os.getenv("TEST_API_URL", "http://localhost:8001")
ORDERS_URL = f"{_BASE}/v1/orders"
ITEMS_URL = f"{_BASE}/v1/items"


# ---------------------------------------------------------------------------
# DB helper — direct psql access (no customer API exists yet)
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
# Module-scoped fixtures — customers
#
# Scoped to module so the two customer rows are created once and reused by
# every test class.  The CASCADE on orders.customer_id → customers.id means
# the DELETE in teardown also cleans up any leftover orders automatically.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def customer():
    """
    Insert a real customer row and return its UUID as the test customer.

    The same UUID is passed in the X-Customer-ID header so the orders router
    stores it as customer_id and the FK constraint is satisfied.
    """
    customer_id = str(uuid.uuid4())
    unique = uuid.uuid4().hex[:8]
    _psql(
        f"INSERT INTO customers (id, keycloak_user_id, email, first_name, last_name) "
        f"VALUES ('{customer_id}', 'kc-{unique}', '{unique}@orders-test.example', "
        f"'Orders', 'Test');"
    )
    yield customer_id
    _psql(f"DELETE FROM customers WHERE id = '{customer_id}';")


@pytest.fixture(scope="module")
def other_customer():
    """Second customer used to verify 403 cross-customer access guards."""
    customer_id = str(uuid.uuid4())
    unique = uuid.uuid4().hex[:8]
    _psql(
        f"INSERT INTO customers (id, keycloak_user_id, email, first_name, last_name) "
        f"VALUES ('{customer_id}', 'kc-other-{unique}', 'other-{unique}@orders-test.example', "
        f"'Other', 'Test');"
    )
    yield customer_id
    _psql(f"DELETE FROM customers WHERE id = '{customer_id}';")


# ---------------------------------------------------------------------------
# Module-scoped fixture — catalogue item
#
# A real item must exist in the catalogue so the orders router can resolve the
# SKU → price snapshot.  Created once for the whole module via the items API.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def catalogue_item():
    """Create a catalogue item to order against and delete it after the module."""
    unique = uuid.uuid4().hex[:8].upper()
    payload = {
        "sku": f"ORD-TEST-{unique}",
        "status": "active",
        "name": "Order Integration Test Product",
        "slug": f"ord-test-{unique.lower()}",
        "short_description": "Used by order integration tests",
        "description": "Temporary product for test_orders_integration.py",
        "brand": "TestBrand",
        "categories": [str(uuid.uuid4())],
        "price": {
            "amount": 1999,
            "currency": "EUR",
            "includes_tax": True,
            "original_amount": None,
            "tax_class": "standard",
        },
        "media": {"main_image": None, "gallery": []},
        "inventory": {
            "stock_quantity": 50,
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
        f"catalogue_item fixture failed: {response.status_code} {response.json()}"
    )
    item = response.json()
    yield item
    requests.delete(f"{ITEMS_URL}/{item['uuid']}")


# ---------------------------------------------------------------------------
# Function-scoped fixture — draft order
#
# Creates a fresh DRAFT order before each test that needs one and cancels it
# in teardown (the CASCADE also removes order_items rows automatically).
# ---------------------------------------------------------------------------


@pytest.fixture
def draft_order(customer, catalogue_item):
    """Create a DRAFT order owned by `customer` and cancel it after the test."""
    payload = {
        "items": [{"sku": catalogue_item["sku"], "quantity": 1}],
        "currency": "EUR",
    }
    headers = {"X-Customer-ID": customer}
    response = requests.post(ORDERS_URL + "/", json=payload, headers=headers)
    assert response.status_code == 201, (
        f"draft_order fixture failed: {response.status_code} {response.json()}"
    )
    order = response.json()
    yield order
    # Soft-cancel in teardown so the row is cleaned up
    if order.get("status") == "draft":
        requests.delete(f"{ORDERS_URL}/{order['id']}", headers=headers)


# ---------------------------------------------------------------------------
# TestCreateOrder
# ---------------------------------------------------------------------------


class TestCreateOrder:
    """POST /v1/orders/"""

    def test_create_order_success(self, customer, catalogue_item):
        """Creating a DRAFT order returns 201 with all expected fields."""
        headers = {"X-Customer-ID": customer}
        payload = {
            "items": [{"sku": catalogue_item["sku"], "quantity": 2}],
            "currency": "EUR",
        }
        response = requests.post(ORDERS_URL + "/", json=payload, headers=headers)

        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "draft"
        assert data["currency"] == "EUR"
        assert data["customer_id"] == customer
        assert data["total_amount"] == catalogue_item["price"]["amount"] * 2
        assert len(data["items"]) == 1
        assert data["items"][0]["sku"] == catalogue_item["sku"]
        assert data["items"][0]["quantity"] == 2
        assert "id" in data
        assert "created_at" in data
        assert "updated_at" in data

        # Cleanup
        requests.delete(f"{ORDERS_URL}/{data['id']}", headers=headers)

    def test_create_order_multiple_units_correct_total(self, customer, catalogue_item):
        """total_amount equals unit_price × quantity."""
        headers = {"X-Customer-ID": customer}
        payload = {
            "items": [{"sku": catalogue_item["sku"], "quantity": 3}],
            "currency": "EUR",
        }
        response = requests.post(ORDERS_URL + "/", json=payload, headers=headers)

        assert response.status_code == 201
        assert response.json()["total_amount"] == catalogue_item["price"]["amount"] * 3

        requests.delete(f"{ORDERS_URL}/{response.json()['id']}", headers=headers)

    def test_create_order_unknown_sku_returns_404(self, customer):
        """Ordering a non-existent SKU returns 404."""
        headers = {"X-Customer-ID": customer}
        payload = {"items": [{"sku": "DOES-NOT-EXIST-XYZ", "quantity": 1}]}
        response = requests.post(ORDERS_URL + "/", json=payload, headers=headers)

        assert response.status_code == 404

    def test_create_order_zero_quantity_rejected(self, customer, catalogue_item):
        """Pydantic validation: quantity=0 is rejected with 422."""
        headers = {"X-Customer-ID": customer}
        payload = {"items": [{"sku": catalogue_item["sku"], "quantity": 0}]}
        response = requests.post(ORDERS_URL + "/", json=payload, headers=headers)

        assert response.status_code == 422

    def test_create_order_empty_items_list_rejected(self, customer):
        """Pydantic validation: empty items list is rejected with 422."""
        headers = {"X-Customer-ID": customer}
        payload = {"items": [], "currency": "EUR"}
        response = requests.post(ORDERS_URL + "/", json=payload, headers=headers)

        assert response.status_code == 422

    def test_create_order_invalid_currency_rejected(self, customer, catalogue_item):
        """Pydantic validation: currency shorter than 3 chars is rejected with 422."""
        headers = {"X-Customer-ID": customer}
        payload = {
            "items": [{"sku": catalogue_item["sku"], "quantity": 1}],
            "currency": "EU",
        }
        response = requests.post(ORDERS_URL + "/", json=payload, headers=headers)

        assert response.status_code == 422

    def test_create_order_defaults_currency_to_eur(self, customer, catalogue_item):
        """When currency is omitted the server defaults to EUR."""
        headers = {"X-Customer-ID": customer}
        payload = {"items": [{"sku": catalogue_item["sku"], "quantity": 1}]}
        response = requests.post(ORDERS_URL + "/", json=payload, headers=headers)

        assert response.status_code == 201
        data = response.json()
        assert data["currency"] == "EUR"

        requests.delete(f"{ORDERS_URL}/{data['id']}", headers=headers)


# ---------------------------------------------------------------------------
# TestGetOrder
# ---------------------------------------------------------------------------


class TestGetOrder:
    """GET /v1/orders/{order_id}"""

    def test_get_order_success(self, customer, draft_order):
        """Fetching own order returns 200 with the correct data."""
        headers = {"X-Customer-ID": customer}
        response = requests.get(f"{ORDERS_URL}/{draft_order['id']}", headers=headers)

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == draft_order["id"]
        assert data["status"] == "draft"
        assert data["customer_id"] == customer
        assert "items" in data

    def test_get_order_not_found(self, customer):
        """Fetching a non-existent UUID returns 404."""
        headers = {"X-Customer-ID": customer}
        response = requests.get(f"{ORDERS_URL}/{uuid.uuid4()}", headers=headers)

        assert response.status_code == 404

    def test_get_order_wrong_customer_returns_403(self, other_customer, draft_order):
        """A different customer cannot read someone else's order."""
        headers = {"X-Customer-ID": other_customer}
        response = requests.get(f"{ORDERS_URL}/{draft_order['id']}", headers=headers)

        assert response.status_code == 403

    def test_get_order_invalid_uuid_returns_422(self, customer):
        """A malformed order ID returns 422."""
        headers = {"X-Customer-ID": customer}
        response = requests.get(f"{ORDERS_URL}/not-a-uuid", headers=headers)

        assert response.status_code == 422


# ---------------------------------------------------------------------------
# TestCancelOrder
# ---------------------------------------------------------------------------


class TestCancelOrder:
    """DELETE /v1/orders/{order_id}"""

    def test_cancel_draft_order_success(self, customer, catalogue_item):
        """Cancelling a DRAFT order returns 204 and the order is then 404."""
        headers = {"X-Customer-ID": customer}
        payload = {"items": [{"sku": catalogue_item["sku"], "quantity": 1}]}
        create_resp = requests.post(ORDERS_URL + "/", json=payload, headers=headers)
        assert create_resp.status_code == 201
        order_id = create_resp.json()["id"]

        cancel_resp = requests.delete(f"{ORDERS_URL}/{order_id}", headers=headers)
        assert cancel_resp.status_code == 204

        # Soft-deleted order is no longer visible
        get_resp = requests.get(f"{ORDERS_URL}/{order_id}", headers=headers)
        assert get_resp.status_code == 404

    def test_cancel_not_found(self, customer):
        """Cancelling a non-existent UUID returns 404."""
        headers = {"X-Customer-ID": customer}
        response = requests.delete(f"{ORDERS_URL}/{uuid.uuid4()}", headers=headers)

        assert response.status_code == 404

    def test_cancel_wrong_customer_returns_403(self, other_customer, draft_order):
        """A different customer cannot cancel someone else's order."""
        headers = {"X-Customer-ID": other_customer}
        response = requests.delete(f"{ORDERS_URL}/{draft_order['id']}", headers=headers)

        assert response.status_code == 403

    def test_cancel_invalid_uuid_returns_422(self, customer):
        """A malformed order ID returns 422."""
        headers = {"X-Customer-ID": customer}
        response = requests.delete(f"{ORDERS_URL}/not-a-uuid", headers=headers)

        assert response.status_code == 422


# ---------------------------------------------------------------------------
# TestCheckoutOrder
# ---------------------------------------------------------------------------


class TestCheckoutOrder:
    """POST /v1/orders/{order_id}/checkout

    Happy-path checkout requires a configured Stripe test key and available
    inventory — those cases are run manually via `stripe listen`.
    These tests cover the guard/validation paths that work without Stripe.
    """

    def test_checkout_not_found(self, customer):
        """Checking out a non-existent order returns 404."""
        headers = {"X-Customer-ID": customer}
        response = requests.post(
            f"{ORDERS_URL}/{uuid.uuid4()}/checkout", headers=headers
        )
        assert response.status_code == 404

    def test_checkout_wrong_customer_returns_403(self, other_customer, draft_order):
        """Another customer cannot check out someone else's order."""
        headers = {"X-Customer-ID": other_customer}
        response = requests.post(
            f"{ORDERS_URL}/{draft_order['id']}/checkout", headers=headers
        )
        assert response.status_code == 403

    def test_checkout_cancelled_order_returns_404(self, customer, catalogue_item):
        """Checking out a soft-deleted (cancelled) order returns 404."""
        headers = {"X-Customer-ID": customer}
        payload = {"items": [{"sku": catalogue_item["sku"], "quantity": 1}]}
        create_resp = requests.post(ORDERS_URL + "/", json=payload, headers=headers)
        assert create_resp.status_code == 201
        order_id = create_resp.json()["id"]

        requests.delete(f"{ORDERS_URL}/{order_id}", headers=headers)

        checkout_resp = requests.post(
            f"{ORDERS_URL}/{order_id}/checkout", headers=headers
        )
        assert checkout_resp.status_code == 404

    def test_checkout_invalid_uuid_returns_422(self, customer):
        """A malformed order ID returns 422."""
        headers = {"X-Customer-ID": customer}
        response = requests.post(f"{ORDERS_URL}/not-a-uuid/checkout", headers=headers)
        assert response.status_code == 422


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
