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
    All endpoints require a Keycloak bearer token; identity comes from its
    subject claim. There are two seeded customer accounts, so tests that once
    invented an identity per case now share them.

    Formerly documented: X-Customer-Email / X-Customer-First-Name /
    X-Customer-Last-Name on the first call (profile creation).
"""

import os
import subprocess
import uuid

import pytest
import requests

from auth_helpers import customer_headers, other_customer_headers

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
    The primary seeded customer, resolved through the API.

    GET /me creates the profile from the token's claims on first contact, so
    this both authenticates and guarantees the row exists.
    """
    headers = customer_headers()
    response = requests.get(f"{CUSTOMERS_URL}/me", headers=headers, timeout=20)
    assert response.status_code == 200, response.text
    body = response.json()
    yield {
        "headers": headers,
        "id": body["id"],
        "kc_id": body["keycloak_user_id"],
        "email": body["email"],
    }


@pytest.fixture(scope="module")
def other_customer():
    """A second seeded account, for cross-customer authorization checks."""
    headers = other_customer_headers()
    response = requests.get(f"{CUSTOMERS_URL}/me", headers=headers, timeout=20)
    assert response.status_code == 200, response.text
    body = response.json()
    yield {"headers": headers, "id": body["id"], "kc_id": body["keycloak_user_id"]}


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
            headers=customer["headers"],
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
            headers=customer["headers"],
        )


# ---------------------------------------------------------------------------
# GET /me — get_my_profile
# ---------------------------------------------------------------------------


class TestGetMyProfile:
    def test_returns_200_for_existing_customer(self, customer):
        resp = requests.get(
            f"{CUSTOMERS_URL}/me",
            headers=customer["headers"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == customer["id"]
        assert body["keycloak_user_id"] == customer["kc_id"]
        assert body["email"] == customer["email"]

    def test_response_contains_expected_fields(self, customer):
        resp = requests.get(
            f"{CUSTOMERS_URL}/me",
            headers=customer["headers"],
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

    def test_missing_keycloak_id_header_returns_403(self):
        # Identity is now resolved by app.authorize: with no bearer token and
        # no dev header there is no caller to act as, which is an authorization
        # failure rather than a malformed request.
        resp = requests.get(f"{CUSTOMERS_URL}/me")
        assert resp.status_code == 403


class TestUpdateMyProfile:
    def test_update_first_name(self, customer):
        resp = requests.patch(
            f"{CUSTOMERS_URL}/me",
            json={"first_name": "Updated"},
            headers=customer["headers"],
        )
        assert resp.status_code == 200
        assert resp.json()["first_name"] == "Updated"

        # Restore original name
        requests.patch(
            f"{CUSTOMERS_URL}/me",
            json={"first_name": "Int"},
            headers=customer["headers"],
        )

    def test_update_last_name(self, customer):
        resp = requests.patch(
            f"{CUSTOMERS_URL}/me",
            json={"last_name": "UpdatedLast"},
            headers=customer["headers"],
        )
        assert resp.status_code == 200
        assert resp.json()["last_name"] == "UpdatedLast"

        requests.patch(
            f"{CUSTOMERS_URL}/me",
            json={"last_name": "Test"},
            headers=customer["headers"],
        )

    def test_empty_payload_returns_200(self, customer):
        resp = requests.patch(
            f"{CUSTOMERS_URL}/me",
            json={},
            headers=customer["headers"],
        )
        assert resp.status_code == 200

    def test_invalid_email_returns_422(self, customer):
        resp = requests.patch(
            f"{CUSTOMERS_URL}/me",
            json={"email": "not-an-email"},
            headers=customer["headers"],
        )
        assert resp.status_code == 422

    def test_missing_keycloak_header_returns_403(self):
        # Identity is now resolved by app.authorize: with no bearer token and
        # no dev header there is no caller to act as, which is an authorization
        # failure rather than a malformed request.
        resp = requests.patch(f"{CUSTOMERS_URL}/me", json={"first_name": "X"})
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /me/addresses — list_my_addresses
# ---------------------------------------------------------------------------


class TestListMyAddresses:
    def test_returns_empty_list_when_no_addresses(self, customer):
        resp = requests.get(
            f"{CUSTOMERS_URL}/me/addresses",
            headers=customer["headers"],
        )
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_returns_created_addresses(self, customer, create_address):
        create_address()
        create_address(city="Hamburg")

        resp = requests.get(
            f"{CUSTOMERS_URL}/me/addresses",
            headers=customer["headers"],
        )
        assert resp.status_code == 200
        addresses = resp.json()
        assert len(addresses) >= 2

    def test_missing_keycloak_header_returns_403(self):
        # Identity is now resolved by app.authorize: with no bearer token and
        # no dev header there is no caller to act as, which is an authorization
        # failure rather than a malformed request.
        resp = requests.get(f"{CUSTOMERS_URL}/me/addresses")
        assert resp.status_code == 403


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
            headers=customer["headers"],
        )
        addresses = {a["id"]: a for a in resp.json()}
        assert addresses[first["id"]]["is_default"] is False
        assert addresses[second["id"]]["is_default"] is True

    def test_missing_street_returns_422(self, customer):
        payload = {"city": "Berlin", "zip_code": "10115", "country": "DE"}
        resp = requests.post(
            f"{CUSTOMERS_URL}/me/addresses",
            json=payload,
            headers=customer["headers"],
        )
        assert resp.status_code == 422

    def test_invalid_country_code_returns_422(self, customer):
        resp = requests.post(
            f"{CUSTOMERS_URL}/me/addresses",
            json=_address_payload(country="GERMANY"),
            headers=customer["headers"],
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
            headers=customer["headers"],
        )
        assert resp.status_code == 200
        assert resp.json()["city"] == "Frankfurt"

    def test_empty_payload_returns_200(self, customer, create_address):
        addr = create_address()
        resp = requests.patch(
            f"{CUSTOMERS_URL}/me/addresses/{addr['id']}",
            json={},
            headers=customer["headers"],
        )
        assert resp.status_code == 200

    def test_address_not_found_returns_404(self, customer):
        resp = requests.patch(
            f"{CUSTOMERS_URL}/me/addresses/{uuid.uuid4()}",
            json={"city": "X"},
            headers=customer["headers"],
        )
        assert resp.status_code == 404
        assert resp.json()["error_code"] == "entity_not_found"

    def test_wrong_owner_returns_403(self, customer, other_customer, create_address):
        addr = create_address()  # belongs to `customer`
        resp = requests.patch(
            f"{CUSTOMERS_URL}/me/addresses/{addr['id']}",
            json={"city": "X"},
            headers=other_customer["headers"],
        )
        assert resp.status_code == 403
        assert resp.json()["error_code"] == "access_denied"

    def test_invalid_uuid_returns_422(self, customer):
        resp = requests.patch(
            f"{CUSTOMERS_URL}/me/addresses/not-a-uuid",
            json={"city": "X"},
            headers=customer["headers"],
        )
        assert resp.status_code == 422


class TestDeleteMyAddress:
    def test_deletes_address_returns_204(self, customer):
        # Create manually so we can assert it's gone (not tracked by create_address fixture)
        resp = requests.post(
            f"{CUSTOMERS_URL}/me/addresses",
            json=_address_payload(),
            headers=customer["headers"],
        )
        assert resp.status_code == 201
        addr_id = resp.json()["id"]

        del_resp = requests.delete(
            f"{CUSTOMERS_URL}/me/addresses/{addr_id}",
            headers=customer["headers"],
        )
        assert del_resp.status_code == 204
        assert del_resp.content == b""

    def test_deleted_address_no_longer_returned(self, customer):
        resp = requests.post(
            f"{CUSTOMERS_URL}/me/addresses",
            json=_address_payload(city="ToDelete"),
            headers=customer["headers"],
        )
        addr_id = resp.json()["id"]
        requests.delete(
            f"{CUSTOMERS_URL}/me/addresses/{addr_id}",
            headers=customer["headers"],
        )

        list_resp = requests.get(
            f"{CUSTOMERS_URL}/me/addresses",
            headers=customer["headers"],
        )
        ids = [a["id"] for a in list_resp.json()]
        assert addr_id not in ids

    def test_address_not_found_returns_404(self, customer):
        resp = requests.delete(
            f"{CUSTOMERS_URL}/me/addresses/{uuid.uuid4()}",
            headers=customer["headers"],
        )
        assert resp.status_code == 404
        assert resp.json()["error_code"] == "entity_not_found"

    def test_wrong_owner_returns_403(self, customer, other_customer, create_address):
        addr = create_address()  # belongs to `customer`
        resp = requests.delete(
            f"{CUSTOMERS_URL}/me/addresses/{addr['id']}",
            headers=other_customer["headers"],
        )
        assert resp.status_code == 403
        assert resp.json()["error_code"] == "access_denied"

    def test_invalid_uuid_returns_422(self, customer):
        resp = requests.delete(
            f"{CUSTOMERS_URL}/me/addresses/not-a-uuid",
            headers=customer["headers"],
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# What replaced the removed cases
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestIdentityComesFromTheToken:
    """
    The cases this class replaces used to invent an identity per test by
    sending X-Keycloak-User-ID and X-Customer-* headers. Those headers are gone:
    anyone who could set them could read and modify any customer's data.
    """

    def test_profile_is_created_from_the_token_on_first_contact(self, customer):
        # No creation headers exist any more - e-mail and name come from the
        # verified token, so a first call cannot fail for want of them.
        response = requests.get(f"{CUSTOMERS_URL}/me", headers=customer["headers"])
        assert response.status_code == 200
        body = response.json()
        assert body["email"]
        assert body["first_name"]

    def test_repeated_calls_resolve_to_the_same_profile(self, customer):
        first = requests.get(f"{CUSTOMERS_URL}/me", headers=customer["headers"]).json()
        second = requests.get(f"{CUSTOMERS_URL}/me", headers=customer["headers"]).json()
        assert first["id"] == second["id"]

    def test_a_forged_header_cannot_name_a_different_subject(self, customer):
        # The header is ignored outright; identity is the token's subject.
        headers = customer["headers"] | {"X-Keycloak-User-ID": "someone-else"}
        body = requests.get(f"{CUSTOMERS_URL}/me", headers=headers).json()
        assert body["keycloak_user_id"] == customer["kc_id"]

    def test_two_accounts_resolve_to_different_profiles(self, customer, other_customer):
        assert customer["id"] != other_customer["id"]

    def test_no_token_is_refused(self):
        assert requests.get(f"{CUSTOMERS_URL}/me").status_code == 403

    def test_a_garbage_token_is_refused(self):
        headers = {"Authorization": "Bearer not.a.real.token"}
        assert requests.get(f"{CUSTOMERS_URL}/me", headers=headers).status_code == 403
