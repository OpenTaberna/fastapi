"""
Integration tests for the Inventory Admin API.

These tests run against the actual running API and database.
Make sure the Docker containers are running before executing these tests:

    docker-compose -f docker-compose.dev.yml up -d

Endpoints covered:
    POST   /v1/admin/inventory              — create_inventory_item
    GET    /v1/admin/inventory              — list_inventory_items
    GET    /v1/admin/inventory/by-sku/{sku} — get_inventory_by_sku
    GET    /v1/admin/inventory/{id}         — get_inventory_item
    PATCH  /v1/admin/inventory/{id}         — update_inventory_item
    DELETE /v1/admin/inventory/{id}         — delete_inventory_item

Auth note:
    All endpoints require X-Admin-Key header.  In dev mode any non-empty
    value is accepted.  Tests use "dev" for authorised requests and omit the
    header to exercise the 403 guard.
"""

import os
import subprocess
import uuid

import pytest
import requests

_BASE = os.getenv("TEST_API_URL", "http://localhost:8000")
INVENTORY_URL = f"{_BASE}/v1/admin/inventory"
ADMIN_HEADERS = {"X-Admin-Key": "dev"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _unique_sku(prefix: str = "INV-TEST") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8].upper()}"


def _psql(sql: str) -> None:
    """Execute a SQL statement inside the running Postgres container."""
    subprocess.run(
        [
            "docker", "exec", "opentaberna-db",
            "psql", "-U", "opentaberna", "-d", "opentaberna", "-c", sql,
        ],
        check=True,
        capture_output=True,
    )


# ---------------------------------------------------------------------------
# Module-scoped fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def inventory_item():
    """
    Create a real inventory item for the whole test module and delete it
    in teardown.  Tests that need a pre-existing item use this fixture.
    """
    sku = _unique_sku()
    payload = {"sku": sku, "on_hand": 100}
    response = requests.post(INVENTORY_URL + "/", json=payload, headers=ADMIN_HEADERS)
    assert response.status_code == 201, (
        f"inventory_item fixture failed: {response.status_code} {response.json()}"
    )
    item = response.json()
    yield item
    requests.delete(f"{INVENTORY_URL}/{item['id']}", headers=ADMIN_HEADERS)


@pytest.fixture
def create_item():
    """
    Function-scoped factory fixture.

    Creates one or more inventory items via the API and guarantees their
    deletion in teardown — even when a test assertion fails mid-test.

    Usage::

        def test_something(self, create_item):
            item = create_item("MY-SKU", on_hand=10)
            # item is a dict with all response fields
    """
    created_ids: list[str] = []

    def _create(sku: str, on_hand: int, **extra) -> dict:
        resp = requests.post(
            INVENTORY_URL + "/",
            json={"sku": sku, "on_hand": on_hand, **extra},
            headers=ADMIN_HEADERS,
        )
        assert resp.status_code == 201, (
            f"create_item fixture failed: {resp.status_code} {resp.json()}"
        )
        item = resp.json()
        created_ids.append(item["id"])
        return item

    yield _create

    for item_id in created_ids:
        requests.delete(f"{INVENTORY_URL}/{item_id}", headers=ADMIN_HEADERS)


# ---------------------------------------------------------------------------
# TestCreateInventoryItem  — POST /v1/admin/inventory/
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestCreateInventoryItem:
    """POST /v1/admin/inventory/"""

    def test_create_success_returns_201(self, create_item):
        """Creating a new inventory record returns 201 with the expected fields."""
        sku = _unique_sku()
        data = create_item(sku, 50)

        assert data["sku"] == sku
        assert data["on_hand"] == 50
        assert data["reserved"] == 0  # always starts at 0
        assert "id" in data
        assert "created_at" in data
        assert "updated_at" in data

    def test_create_reserved_always_zero(self, create_item):
        """Even if reserved is provided in payload it starts at 0."""
        sku = _unique_sku()
        data = create_item(sku, 10, reserved=5)

        assert data["reserved"] == 0

    def test_create_on_hand_zero_accepted(self, create_item):
        """on_hand=0 is valid (out-of-stock from the start)."""
        sku = _unique_sku()
        data = create_item(sku, 0)

        assert data["on_hand"] == 0

    def test_create_duplicate_sku_returns_422(self, inventory_item):
        """Creating a second record for the same SKU returns 422."""
        response = requests.post(
            INVENTORY_URL + "/",
            json={"sku": inventory_item["sku"], "on_hand": 10},
            headers=ADMIN_HEADERS,
        )

        assert response.status_code == 422
        data = response.json()
        assert "already exists" in data["message"]

    def test_create_negative_on_hand_returns_422(self):
        """Pydantic validation: on_hand < 0 returns 422."""
        response = requests.post(
            INVENTORY_URL + "/",
            json={"sku": _unique_sku(), "on_hand": -1},
            headers=ADMIN_HEADERS,
        )

        assert response.status_code == 422

    def test_create_empty_sku_returns_422(self):
        """Pydantic validation: empty SKU returns 422."""
        response = requests.post(
            INVENTORY_URL + "/",
            json={"sku": "", "on_hand": 10},
            headers=ADMIN_HEADERS,
        )

        assert response.status_code == 422

    def test_create_missing_admin_key_returns_403(self):
        """Omitting X-Admin-Key returns 403."""
        response = requests.post(
            INVENTORY_URL + "/",
            json={"sku": _unique_sku(), "on_hand": 10},
        )

        assert response.status_code == 403

    def test_create_missing_sku_returns_422(self):
        """Omitting the required sku field returns 422."""
        response = requests.post(
            INVENTORY_URL + "/",
            json={"on_hand": 10},
            headers=ADMIN_HEADERS,
        )

        assert response.status_code == 422

    def test_create_missing_on_hand_returns_422(self):
        """Omitting the required on_hand field returns 422."""
        response = requests.post(
            INVENTORY_URL + "/",
            json={"sku": _unique_sku()},
            headers=ADMIN_HEADERS,
        )

        assert response.status_code == 422


# ---------------------------------------------------------------------------
# TestListInventoryItems — GET /v1/admin/inventory/
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestListInventoryItems:
    """GET /v1/admin/inventory/"""

    def test_list_returns_200(self, inventory_item):
        """Listing inventory items returns 200 with a paginated response."""
        response = requests.get(INVENTORY_URL + "/", headers=ADMIN_HEADERS)

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "page_info" in data
        assert isinstance(data["items"], list)

    def test_list_contains_created_item(self, inventory_item):
        """The module-scoped fixture item must appear in the list."""
        response = requests.get(INVENTORY_URL + "/?limit=200", headers=ADMIN_HEADERS)

        assert response.status_code == 200
        ids = [item["id"] for item in response.json()["items"]]
        assert inventory_item["id"] in ids

    def test_list_pagination_skip(self, inventory_item):
        """skip parameter is accepted without error."""
        response = requests.get(
            INVENTORY_URL + "/?skip=0&limit=5", headers=ADMIN_HEADERS
        )

        assert response.status_code == 200
        assert len(response.json()["items"]) <= 5

    def test_list_limit_respected(self, inventory_item):
        """limit=1 returns at most 1 item."""
        response = requests.get(
            INVENTORY_URL + "/?limit=1", headers=ADMIN_HEADERS
        )

        assert response.status_code == 200
        assert len(response.json()["items"]) <= 1

    def test_list_invalid_skip_returns_422(self):
        """skip < 0 returns 422."""
        response = requests.get(
            INVENTORY_URL + "/?skip=-1", headers=ADMIN_HEADERS
        )

        assert response.status_code == 422

    def test_list_invalid_limit_returns_422(self):
        """limit=0 is below the minimum of 1 — returns 422."""
        response = requests.get(
            INVENTORY_URL + "/?limit=0", headers=ADMIN_HEADERS
        )

        assert response.status_code == 422

    def test_list_limit_above_max_returns_422(self):
        """limit=201 is above the maximum of 200 — returns 422."""
        response = requests.get(
            INVENTORY_URL + "/?limit=201", headers=ADMIN_HEADERS
        )

        assert response.status_code == 422

    def test_list_missing_admin_key_returns_403(self):
        """Omitting X-Admin-Key returns 403."""
        response = requests.get(INVENTORY_URL + "/")

        assert response.status_code == 403


# ---------------------------------------------------------------------------
# TestGetInventoryBySku — GET /v1/admin/inventory/by-sku/{sku}
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestGetInventoryBySku:
    """GET /v1/admin/inventory/by-sku/{sku}"""

    def test_get_by_sku_success(self, inventory_item):
        """Fetching an existing SKU returns 200 with correct data."""
        response = requests.get(
            f"{INVENTORY_URL}/by-sku/{inventory_item['sku']}",
            headers=ADMIN_HEADERS,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["sku"] == inventory_item["sku"]
        assert data["id"] == inventory_item["id"]

    def test_get_by_sku_not_found(self):
        """A SKU that has no inventory record returns 404."""
        response = requests.get(
            f"{INVENTORY_URL}/by-sku/DOES-NOT-EXIST-XYZ",
            headers=ADMIN_HEADERS,
        )

        assert response.status_code == 404
        assert "not found" in response.json()["message"].lower()

    def test_get_by_sku_missing_admin_key_returns_403(self, inventory_item):
        """Omitting X-Admin-Key returns 403."""
        response = requests.get(
            f"{INVENTORY_URL}/by-sku/{inventory_item['sku']}"
        )

        assert response.status_code == 403


# ---------------------------------------------------------------------------
# TestGetInventoryItem — GET /v1/admin/inventory/{id}
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestGetInventoryItem:
    """GET /v1/admin/inventory/{inventory_id}"""

    def test_get_by_id_success(self, inventory_item):
        """Fetching by UUID returns 200 with the correct record."""
        response = requests.get(
            f"{INVENTORY_URL}/{inventory_item['id']}",
            headers=ADMIN_HEADERS,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == inventory_item["id"]
        assert data["sku"] == inventory_item["sku"]
        assert data["on_hand"] == inventory_item["on_hand"]
        assert data["reserved"] == 0

    def test_get_not_found_returns_404(self):
        """A non-existent UUID returns 404."""
        response = requests.get(
            f"{INVENTORY_URL}/{uuid.uuid4()}",
            headers=ADMIN_HEADERS,
        )

        assert response.status_code == 404
        assert "not found" in response.json()["message"].lower()

    def test_get_invalid_uuid_returns_422(self):
        """A malformed UUID path parameter returns 422."""
        response = requests.get(
            f"{INVENTORY_URL}/not-a-uuid",
            headers=ADMIN_HEADERS,
        )

        assert response.status_code == 422

    def test_get_missing_admin_key_returns_403(self, inventory_item):
        """Omitting X-Admin-Key returns 403."""
        response = requests.get(f"{INVENTORY_URL}/{inventory_item['id']}")

        assert response.status_code == 403


# ---------------------------------------------------------------------------
# TestUpdateInventoryItem — PATCH /v1/admin/inventory/{id}
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestUpdateInventoryItem:
    """PATCH /v1/admin/inventory/{inventory_id}"""

    def test_update_on_hand_success(self, create_item):
        """Updating on_hand to a valid value returns 200 with updated data."""
        sku = _unique_sku("UPD")
        item = create_item(sku, 50)

        update_resp = requests.patch(
            f"{INVENTORY_URL}/{item['id']}",
            json={"on_hand": 80},
            headers=ADMIN_HEADERS,
        )

        assert update_resp.status_code == 200
        data = update_resp.json()
        assert data["on_hand"] == 80
        assert data["id"] == item["id"]

    def test_update_on_hand_to_zero_accepted(self, create_item):
        """on_hand=0 is a valid update (item sold out)."""
        sku = _unique_sku("ZERO")
        item = create_item(sku, 20)

        update_resp = requests.patch(
            f"{INVENTORY_URL}/{item['id']}",
            json={"on_hand": 0},
            headers=ADMIN_HEADERS,
        )

        assert update_resp.status_code == 200
        assert update_resp.json()["on_hand"] == 0

    def test_update_on_hand_below_reserved_returns_400(self, create_item):
        """Setting on_hand below the current reserved count returns 400.

        reserved is managed exclusively by the checkout flow and cannot be set
        via PATCH. This test seeds reserved directly via psql so the constraint
        can be exercised without a full checkout.
        """
        sku = _unique_sku("RES")
        item = create_item(sku, 20)

        # Seed reserved=10 directly in the DB — the API intentionally does not
        # expose reserved as a writable field.
        _psql(
            f"UPDATE inventory_items SET reserved = 10 WHERE id = '{item['id']}'"
        )

        # Now try to set on_hand=5 (below reserved=10) — must fail
        update_resp = requests.patch(
            f"{INVENTORY_URL}/{item['id']}",
            json={"on_hand": 5},
            headers=ADMIN_HEADERS,
        )

        assert update_resp.status_code == 400
        assert "reserved" in update_resp.json()["message"].lower()

    def test_update_not_found_returns_404(self):
        """Patching a non-existent UUID returns 404."""
        response = requests.patch(
            f"{INVENTORY_URL}/{uuid.uuid4()}",
            json={"on_hand": 10},
            headers=ADMIN_HEADERS,
        )

        assert response.status_code == 404

    def test_update_invalid_uuid_returns_422(self):
        """A malformed UUID path parameter returns 422."""
        response = requests.patch(
            f"{INVENTORY_URL}/not-a-uuid",
            json={"on_hand": 10},
            headers=ADMIN_HEADERS,
        )

        assert response.status_code == 422

    def test_update_negative_on_hand_returns_422(self, inventory_item):
        """Pydantic validation: on_hand < 0 returns 422."""
        response = requests.patch(
            f"{INVENTORY_URL}/{inventory_item['id']}",
            json={"on_hand": -5},
            headers=ADMIN_HEADERS,
        )

        assert response.status_code == 422

    def test_update_missing_admin_key_returns_403(self, inventory_item):
        """Omitting X-Admin-Key returns 403."""
        response = requests.patch(
            f"{INVENTORY_URL}/{inventory_item['id']}",
            json={"on_hand": 50},
        )

        assert response.status_code == 403

    def test_empty_patch_body_accepted(self, inventory_item):
        """PATCH with an empty body (no-op update) returns 200 unchanged."""
        response = requests.patch(
            f"{INVENTORY_URL}/{inventory_item['id']}",
            json={},
            headers=ADMIN_HEADERS,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == inventory_item["id"]
        assert data["on_hand"] == inventory_item["on_hand"]


# ---------------------------------------------------------------------------
# TestDeleteInventoryItem — DELETE /v1/admin/inventory/{id}
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestDeleteInventoryItem:
    """DELETE /v1/admin/inventory/{inventory_id}"""

    def test_delete_success_returns_204(self, create_item):
        """Deleting an existing item returns 204 and the item is no longer found."""
        sku = _unique_sku("DEL")
        item = create_item(sku, 10)

        delete_resp = requests.delete(
            f"{INVENTORY_URL}/{item['id']}", headers=ADMIN_HEADERS
        )
        assert delete_resp.status_code == 204

        # Verify the record is gone
        get_resp = requests.get(f"{INVENTORY_URL}/{item['id']}", headers=ADMIN_HEADERS)
        assert get_resp.status_code == 404

    def test_delete_not_found_returns_404(self):
        """Deleting a non-existent UUID returns 404."""
        response = requests.delete(
            f"{INVENTORY_URL}/{uuid.uuid4()}", headers=ADMIN_HEADERS
        )

        assert response.status_code == 404

    def test_delete_invalid_uuid_returns_422(self):
        """A malformed UUID path parameter returns 422."""
        response = requests.delete(
            f"{INVENTORY_URL}/not-a-uuid", headers=ADMIN_HEADERS
        )

        assert response.status_code == 422

    def test_delete_missing_admin_key_returns_403(self, inventory_item):
        """Omitting X-Admin-Key returns 403."""
        response = requests.delete(f"{INVENTORY_URL}/{inventory_item['id']}")

        assert response.status_code == 403

    def test_delete_idempotent_second_call_returns_404(self, create_item):
        """Deleting the same item twice — second call returns 404."""
        sku = _unique_sku("IDEM")
        item = create_item(sku, 5)

        requests.delete(f"{INVENTORY_URL}/{item['id']}", headers=ADMIN_HEADERS)

        second_resp = requests.delete(
            f"{INVENTORY_URL}/{item['id']}", headers=ADMIN_HEADERS
        )
        assert second_resp.status_code == 404
