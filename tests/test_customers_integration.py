"""
Integration tests for the Customers API.

These tests run against the actual running API and database.
Make sure the Docker containers are running before executing these tests:

    docker-compose -f docker-compose.dev.yml up -d

Endpoints covered:
    GET    /v1/customers/me                    — get_my_profile (auto-create on first call)
    PATCH  /v1/customers/me                    — update_my_profile
    GET    /v1/customers/me/addresses          — list_my_addresses
    POST   /v1/customers/me/addresses          — create_my_address
    PATCH  /v1/customers/me/addresses/{id}     — update_my_address
    DELETE /v1/customers/me/addresses/{id}     — delete_my_address

Auth note:
    All endpoints require X-Keycloak-User-ID.
    GET /me additionally accepts X-Customer-Email / X-Customer-First-Name /
    X-Customer-Last-Name on the first call (profile creation).
"""

import os
import subprocess
import uuid

import pytest
import requests

_BASE = os.getenv("TEST_API_URL", "http://localhost:8000")
CUSTOMERS_URL = f"{_BASE}/v1/customers"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _unique_kc_id(prefix: str = "kc-int") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _unique_email(prefix: str = "cust-int") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}@example.com"


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


def _creation_headers(
    kc_id: str, email: str, first: str = "Int", last: str = "Test"
) -> dict:
    """Return all four headers needed to auto-create a profile via GET /me."""
    return {
        "X-Keycloak-User-ID": kc_id,
        "X-Customer-Email": email,
        "X-Customer-First-Name": first,
        "X-Customer-Last-Name": last,
    }


def _id_header(kc_id: str) -> dict:
    """Return the single header needed by all non-creation endpoints."""
    return {"X-Keycloak-User-ID": kc_id}


def _address_payload(**overrides) -> dict:
    base = {
        "street": "Teststraße 1",
        "city": "Berlin",
        "zip_code": "10115",
        "country": "DE",
        "is_default": False,
    }
    return {**base, **overrides}


# ---------------------------------------------------------------------------
# Module-scoped fixture — one customer for the whole module
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def customer():
    """
    Create a real customer profile via GET /me (auto-create path) and
    delete the DB row in teardown.  CASCADE removes any leftover addresses.
    """
    kc_id = _unique_kc_id()
    email = _unique_email()
    headers = _creation_headers(kc_id, email)

    resp = requests.get(f"{CUSTOMERS_URL}/me", headers=headers)
    assert resp.status_code == 200, (
        f"customer fixture: GET /me failed {resp.status_code} {resp.json()}"
    )
    data = resp.json()
    yield {"kc_id": kc_id, "email": email, "id": data["id"], "data": data}

    _psql(f"DELETE FROM customers WHERE id = '{data['id']}';")


@pytest.fixture(scope="module")
def other_customer():
    """Second customer — used to verify 403 cross-customer access guards."""
    kc_id = _unique_kc_id(prefix="kc-other")
    email = _unique_email(prefix="other")
    headers = _creation_headers(kc_id, email, first="Other", last="Customer")

    resp = requests.get(f"{CUSTOMERS_URL}/me", headers=headers)
    assert resp.status_code == 200, (
        f"other_customer fixture: GET /me failed {resp.status_code} {resp.json()}"
    )
    data = resp.json()
    yield {"kc_id": kc_id, "email": email, "id": data["id"], "data": data}

    _psql(f"DELETE FROM customers WHERE id = '{data['id']}';")


@pytest.fixture
def create_address(customer):
    """
    Function-scoped factory fixture: creates one address per call and
    guarantees deletion even if the test fails.
    """
    created_ids: list[str] = []

    def _create(**overrides) -> dict:
        resp = requests.post(
            f"{CUSTOMERS_URL}/me/addresses",
            json=_address_payload(**overrides),
            headers=_id_header(customer["kc_id"]),
        )
        assert resp.status_code == 201, (
            f"create_address fixture failed: {resp.status_code} {resp.json()}"
        )
        data = resp.json()
        created_ids.append(data["id"])
        return data

    yield _create

    for addr_id in created_ids:
        requests.delete(
            f"{CUSTOMERS_URL}/me/addresses/{addr_id}",
            headers=_id_header(customer["kc_id"]),
        )


# ---------------------------------------------------------------------------
# GET /me — get_my_profile
# ---------------------------------------------------------------------------


class TestGetMyProfile:
    def test_returns_200_for_existing_customer(self, customer):
        resp = requests.get(
            f"{CUSTOMERS_URL}/me",
            headers=_id_header(customer["kc_id"]),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == customer["id"]
        assert body["keycloak_user_id"] == customer["kc_id"]
        assert body["email"] == customer["email"]

    def test_response_contains_expected_fields(self, customer):
        resp = requests.get(
            f"{CUSTOMERS_URL}/me",
            headers=_id_header(customer["kc_id"]),
        )
        body = resp.json()
        for field in (
            "id",
            "keycloak_user_id",
            "email",
            "first_name",
            "last_name",
            "created_at",
            "updated_at",
        ):
            assert field in body, f"Missing field: {field}"

    def test_auto_creates_profile_on_first_call(self):
        """A brand-new Keycloak ID with creation headers should yield 200 + new profile."""
        kc_id = _unique_kc_id(prefix="kc-autocreate")
        email = _unique_email(prefix="autocreate")
        headers = _creation_headers(kc_id, email)

        resp = requests.get(f"{CUSTOMERS_URL}/me", headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["keycloak_user_id"] == kc_id

        _psql(f"DELETE FROM customers WHERE id = '{body['id']}';")

    def test_missing_keycloak_id_header_returns_422(self):
        resp = requests.get(f"{CUSTOMERS_URL}/me")
        assert resp.status_code == 422

    def test_missing_creation_headers_for_new_user_returns_422(self):
        kc_id = _unique_kc_id(prefix="kc-nocreate")
        resp = requests.get(
            f"{CUSTOMERS_URL}/me",
            headers=_id_header(kc_id),
        )
        assert resp.status_code == 422
        body = resp.json()
        assert body["error_code"] == "missing_field"

    def test_missing_creation_headers_error_contains_field_context(self):
        kc_id = _unique_kc_id(prefix="kc-ctx")
        resp = requests.get(
            f"{CUSTOMERS_URL}/me",
            headers=_id_header(kc_id),
        )
        body = resp.json()
        assert body["details"]["field"] == "X-Customer-Email"

    def test_second_call_without_creation_headers_succeeds(self, customer):
        """After profile exists, creation headers are not required on subsequent calls."""
        resp = requests.get(
            f"{CUSTOMERS_URL}/me",
            headers=_id_header(customer["kc_id"]),
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# PATCH /me — update_my_profile
# ---------------------------------------------------------------------------


class TestUpdateMyProfile:
    def test_update_first_name(self, customer):
        resp = requests.patch(
            f"{CUSTOMERS_URL}/me",
            json={"first_name": "Updated"},
            headers=_id_header(customer["kc_id"]),
        )
        assert resp.status_code == 200
        assert resp.json()["first_name"] == "Updated"

        # Restore original name
        requests.patch(
            f"{CUSTOMERS_URL}/me",
            json={"first_name": "Int"},
            headers=_id_header(customer["kc_id"]),
        )

    def test_update_last_name(self, customer):
        resp = requests.patch(
            f"{CUSTOMERS_URL}/me",
            json={"last_name": "UpdatedLast"},
            headers=_id_header(customer["kc_id"]),
        )
        assert resp.status_code == 200
        assert resp.json()["last_name"] == "UpdatedLast"

        requests.patch(
            f"{CUSTOMERS_URL}/me",
            json={"last_name": "Test"},
            headers=_id_header(customer["kc_id"]),
        )

    def test_empty_payload_returns_200(self, customer):
        resp = requests.patch(
            f"{CUSTOMERS_URL}/me",
            json={},
            headers=_id_header(customer["kc_id"]),
        )
        assert resp.status_code == 200

    def test_unknown_customer_returns_404(self):
        resp = requests.patch(
            f"{CUSTOMERS_URL}/me",
            json={"first_name": "Ghost"},
            headers=_id_header(_unique_kc_id(prefix="kc-ghost")),
        )
        assert resp.status_code == 404
        body = resp.json()
        assert body["error_code"] == "entity_not_found"

    def test_invalid_email_returns_422(self, customer):
        resp = requests.patch(
            f"{CUSTOMERS_URL}/me",
            json={"email": "not-an-email"},
            headers=_id_header(customer["kc_id"]),
        )
        assert resp.status_code == 422

    def test_missing_keycloak_header_returns_422(self):
        resp = requests.patch(f"{CUSTOMERS_URL}/me", json={"first_name": "X"})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /me/addresses — list_my_addresses
# ---------------------------------------------------------------------------


class TestListMyAddresses:
    def test_returns_empty_list_when_no_addresses(self, customer):
        resp = requests.get(
            f"{CUSTOMERS_URL}/me/addresses",
            headers=_id_header(customer["kc_id"]),
        )
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_returns_created_addresses(self, customer, create_address):
        create_address()
        create_address(city="Hamburg")

        resp = requests.get(
            f"{CUSTOMERS_URL}/me/addresses",
            headers=_id_header(customer["kc_id"]),
        )
        assert resp.status_code == 200
        addresses = resp.json()
        assert len(addresses) >= 2

    def test_unknown_customer_returns_404(self):
        resp = requests.get(
            f"{CUSTOMERS_URL}/me/addresses",
            headers=_id_header(_unique_kc_id(prefix="kc-ghost")),
        )
        assert resp.status_code == 404

    def test_missing_keycloak_header_returns_422(self):
        resp = requests.get(f"{CUSTOMERS_URL}/me/addresses")
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /me/addresses — create_my_address
# ---------------------------------------------------------------------------


class TestCreateMyAddress:
    def test_creates_address_returns_201(self, create_address):
        addr = create_address()
        assert addr["street"] == "Teststraße 1"
        assert addr["city"] == "Berlin"
        assert addr["country"] == "DE"
        assert "id" in addr

    def test_response_contains_expected_fields(self, create_address):
        addr = create_address()
        for field in (
            "id",
            "customer_id",
            "street",
            "city",
            "zip_code",
            "country",
            "is_default",
            "created_at",
            "updated_at",
        ):
            assert field in addr, f"Missing field: {field}"

    def test_default_address_clears_previous_default(self, customer, create_address):
        first = create_address(is_default=True)
        assert first["is_default"] is True

        second = create_address(city="Munich", is_default=True)
        assert second["is_default"] is True

        # Re-fetch the first address — it should no longer be default.
        resp = requests.get(
            f"{CUSTOMERS_URL}/me/addresses",
            headers=_id_header(customer["kc_id"]),
        )
        addresses = {a["id"]: a for a in resp.json()}
        assert addresses[first["id"]]["is_default"] is False
        assert addresses[second["id"]]["is_default"] is True

    def test_unknown_customer_returns_404(self):
        resp = requests.post(
            f"{CUSTOMERS_URL}/me/addresses",
            json=_address_payload(),
            headers=_id_header(_unique_kc_id(prefix="kc-ghost")),
        )
        assert resp.status_code == 404

    def test_missing_street_returns_422(self, customer):
        payload = {"city": "Berlin", "zip_code": "10115", "country": "DE"}
        resp = requests.post(
            f"{CUSTOMERS_URL}/me/addresses",
            json=payload,
            headers=_id_header(customer["kc_id"]),
        )
        assert resp.status_code == 422

    def test_invalid_country_code_returns_422(self, customer):
        resp = requests.post(
            f"{CUSTOMERS_URL}/me/addresses",
            json=_address_payload(country="GERMANY"),
            headers=_id_header(customer["kc_id"]),
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# PATCH /me/addresses/{id} — update_my_address
# ---------------------------------------------------------------------------


class TestUpdateMyAddress:
    def test_updates_city(self, customer, create_address):
        addr = create_address()
        resp = requests.patch(
            f"{CUSTOMERS_URL}/me/addresses/{addr['id']}",
            json={"city": "Frankfurt"},
            headers=_id_header(customer["kc_id"]),
        )
        assert resp.status_code == 200
        assert resp.json()["city"] == "Frankfurt"

    def test_empty_payload_returns_200(self, customer, create_address):
        addr = create_address()
        resp = requests.patch(
            f"{CUSTOMERS_URL}/me/addresses/{addr['id']}",
            json={},
            headers=_id_header(customer["kc_id"]),
        )
        assert resp.status_code == 200

    def test_address_not_found_returns_404(self, customer):
        resp = requests.patch(
            f"{CUSTOMERS_URL}/me/addresses/{uuid.uuid4()}",
            json={"city": "X"},
            headers=_id_header(customer["kc_id"]),
        )
        assert resp.status_code == 404
        assert resp.json()["error_code"] == "entity_not_found"

    def test_wrong_owner_returns_403(self, customer, other_customer, create_address):
        addr = create_address()  # belongs to `customer`
        resp = requests.patch(
            f"{CUSTOMERS_URL}/me/addresses/{addr['id']}",
            json={"city": "X"},
            headers=_id_header(other_customer["kc_id"]),
        )
        assert resp.status_code == 403
        assert resp.json()["error_code"] == "access_denied"

    def test_invalid_uuid_returns_422(self, customer):
        resp = requests.patch(
            f"{CUSTOMERS_URL}/me/addresses/not-a-uuid",
            json={"city": "X"},
            headers=_id_header(customer["kc_id"]),
        )
        assert resp.status_code == 422

    def test_unknown_customer_returns_404(self, create_address, customer):
        addr = create_address()
        resp = requests.patch(
            f"{CUSTOMERS_URL}/me/addresses/{addr['id']}",
            json={"city": "X"},
            headers=_id_header(_unique_kc_id(prefix="kc-ghost")),
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /me/addresses/{id} — delete_my_address
# ---------------------------------------------------------------------------


class TestDeleteMyAddress:
    def test_deletes_address_returns_204(self, customer):
        # Create manually so we can assert it's gone (not tracked by create_address fixture)
        resp = requests.post(
            f"{CUSTOMERS_URL}/me/addresses",
            json=_address_payload(),
            headers=_id_header(customer["kc_id"]),
        )
        assert resp.status_code == 201
        addr_id = resp.json()["id"]

        del_resp = requests.delete(
            f"{CUSTOMERS_URL}/me/addresses/{addr_id}",
            headers=_id_header(customer["kc_id"]),
        )
        assert del_resp.status_code == 204
        assert del_resp.content == b""

    def test_deleted_address_no_longer_returned(self, customer):
        resp = requests.post(
            f"{CUSTOMERS_URL}/me/addresses",
            json=_address_payload(city="ToDelete"),
            headers=_id_header(customer["kc_id"]),
        )
        addr_id = resp.json()["id"]
        requests.delete(
            f"{CUSTOMERS_URL}/me/addresses/{addr_id}",
            headers=_id_header(customer["kc_id"]),
        )

        list_resp = requests.get(
            f"{CUSTOMERS_URL}/me/addresses",
            headers=_id_header(customer["kc_id"]),
        )
        ids = [a["id"] for a in list_resp.json()]
        assert addr_id not in ids

    def test_address_not_found_returns_404(self, customer):
        resp = requests.delete(
            f"{CUSTOMERS_URL}/me/addresses/{uuid.uuid4()}",
            headers=_id_header(customer["kc_id"]),
        )
        assert resp.status_code == 404
        assert resp.json()["error_code"] == "entity_not_found"

    def test_wrong_owner_returns_403(self, customer, other_customer, create_address):
        addr = create_address()  # belongs to `customer`
        resp = requests.delete(
            f"{CUSTOMERS_URL}/me/addresses/{addr['id']}",
            headers=_id_header(other_customer["kc_id"]),
        )
        assert resp.status_code == 403
        assert resp.json()["error_code"] == "access_denied"

    def test_invalid_uuid_returns_422(self, customer):
        resp = requests.delete(
            f"{CUSTOMERS_URL}/me/addresses/not-a-uuid",
            headers=_id_header(customer["kc_id"]),
        )
        assert resp.status_code == 422

    def test_unknown_customer_returns_404(self, create_address, customer):
        addr = create_address()
        resp = requests.delete(
            f"{CUSTOMERS_URL}/me/addresses/{addr['id']}",
            headers=_id_header(_unique_kc_id(prefix="kc-ghost")),
        )
        assert resp.status_code == 404
