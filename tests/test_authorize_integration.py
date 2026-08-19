"""
Integration tests for Keycloak-backed authorization.

Runs against the live stack, using real tokens minted by the running Keycloak:

    docker compose -f docker-compose.dev.yml up -d

What is asserted:
    - Admin endpoints need the admin realm role AND a token from the admin
      frontend client. An administrator's storefront token is refused, which is
      the guarantee that back-office actions cannot be driven from the shop.
    - Customer endpoints identify the caller from the verified token, and a
      forged X-Keycloak-User-ID header cannot override it.
    - Catalogue and health endpoints stay open to everyone.
"""

import os
import subprocess

import pytest
import requests

_BASE = os.getenv("TEST_API_URL", "http://localhost:8000")
_KC = os.getenv("TEST_KEYCLOAK_URL", "http://localhost:8080")
_TOKEN_URL = f"{_KC}/realms/opentaberna/protocol/openid-connect/token"

ADMIN_INVENTORY = f"{_BASE}/v1/admin/inventory/"
ADMIN_ORDERS = f"{_BASE}/v1/admin/orders/"
CUSTOMERS_ME = f"{_BASE}/v1/customers/me"

ADMIN_CLIENT = "opentaberna-admin-ui"
STORE_CLIENT = "opentaberna-store-ui"


def _token(client_id: str, username: str, password: str) -> str | None:
    """Mint an access token, or return None when Keycloak is unreachable."""
    try:
        resp = requests.post(
            _TOKEN_URL,
            data={
                "client_id": client_id,
                "grant_type": "password",
                "username": username,
                "password": password,
            },
            timeout=15,
        )
    except requests.RequestException:
        return None
    if resp.status_code != 200:
        return None
    return resp.json().get("access_token")


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def admin_token():
    tok = _token(ADMIN_CLIENT, "adminuser", "adminpassword")
    if tok is None:
        pytest.skip("Keycloak is not reachable")
    return tok


@pytest.fixture(scope="module")
def admin_token_from_store():
    """The admin user, but logged into the storefront instead."""
    tok = _token(STORE_CLIENT, "adminuser", "adminpassword")
    if tok is None:
        pytest.skip("Keycloak is not reachable")
    return tok


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
        check=False,
        capture_output=True,
    )


@pytest.fixture(scope="module", autouse=True)
def _clear_stale_profile():
    """
    Drop any profile left over from an earlier Keycloak instance.

    Recreating the Keycloak volume regenerates every user's subject claim, so a
    profile created before the wipe is bound to an id nobody holds any more.
    Because e-mail is unique, the API then correctly refuses to create a second
    profile for the same address - which is right in production but leaves this
    suite unable to exercise first-contact creation.
    """
    _psql(
        "DELETE FROM addresses WHERE customer_id IN "
        "(SELECT id FROM customers WHERE email = 'testuser@opentaberna.dev');"
    )
    _psql("DELETE FROM customers WHERE email = 'testuser@opentaberna.dev';")
    yield


@pytest.fixture(scope="module")
def customer_token():
    tok = _token(STORE_CLIENT, "testuser", "testpassword")
    if tok is None:
        pytest.skip("Keycloak is not reachable")
    return tok


# ---------------------------------------------------------------------------
# Realm wiring
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestRealmConfiguration:
    def test_registered_user_gets_the_customer_role_automatically(self, customer_token):
        import base64
        import json

        payload = customer_token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload))
        assert "customer" in claims["realm_access"]["roles"]

    def test_customer_does_not_get_the_admin_role(self, customer_token):
        import base64
        import json

        payload = customer_token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload))
        assert "admin" not in claims["realm_access"]["roles"]

    def test_token_carries_the_api_audience(self, customer_token):
        import base64
        import json

        payload = customer_token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload))
        aud = claims["aud"]
        aud = aud if isinstance(aud, list) else [aud]
        assert "opentaberna-api" in aud


# ---------------------------------------------------------------------------
# Admin endpoints
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestAdminEndpointProtection:
    def test_admin_from_admin_frontend_is_allowed(self, admin_token):
        assert (
            requests.get(ADMIN_INVENTORY, headers=_auth(admin_token)).status_code == 200
        )

    def test_admin_from_storefront_is_refused(self, admin_token_from_store):
        # Same person, same role — but the token belongs to the shop client.
        resp = requests.get(ADMIN_INVENTORY, headers=_auth(admin_token_from_store))
        assert resp.status_code == 403

    def test_customer_is_refused(self, customer_token):
        assert (
            requests.get(ADMIN_INVENTORY, headers=_auth(customer_token)).status_code
            == 403
        )

    def test_anonymous_is_refused(self):
        assert requests.get(ADMIN_INVENTORY).status_code == 403

    def test_garbage_token_is_refused(self):
        assert (
            requests.get(ADMIN_INVENTORY, headers=_auth("not.a.token")).status_code
            == 403
        )

    def test_admin_orders_is_protected_too(self, customer_token):
        assert (
            requests.get(ADMIN_ORDERS, headers=_auth(customer_token)).status_code == 403
        )

    def test_admin_orders_allows_the_admin_frontend(self, admin_token):
        assert requests.get(ADMIN_ORDERS, headers=_auth(admin_token)).status_code == 200


# ---------------------------------------------------------------------------
# Customer endpoints
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestCustomerIdentity:
    def test_profile_is_created_from_the_token(self, customer_token):
        resp = requests.get(CUSTOMERS_ME, headers=_auth(customer_token))
        assert resp.status_code == 200
        assert resp.json()["email"] == "testuser@opentaberna.dev"

    def test_profile_carries_the_optional_phone_from_keycloak(self, customer_token):
        assert requests.get(CUSTOMERS_ME, headers=_auth(customer_token)).json()["phone"]

    def test_identity_is_the_token_subject(self, customer_token):
        import base64
        import json

        payload = customer_token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        sub = json.loads(base64.urlsafe_b64decode(payload))["sub"]
        body = requests.get(CUSTOMERS_ME, headers=_auth(customer_token)).json()
        assert body["keycloak_user_id"] == sub

    def test_forged_header_cannot_override_the_token(self, customer_token):
        # Without this, anyone could read another customer's profile by
        # guessing their id while holding a valid token of their own.
        headers = _auth(customer_token) | {"X-Keycloak-User-ID": "someone-else"}
        body = requests.get(CUSTOMERS_ME, headers=headers).json()
        assert body["keycloak_user_id"] != "someone-else"

    def test_repeated_calls_do_not_duplicate_the_profile(self, customer_token):
        first = requests.get(CUSTOMERS_ME, headers=_auth(customer_token)).json()
        second = requests.get(CUSTOMERS_ME, headers=_auth(customer_token)).json()
        assert first["id"] == second["id"]

    def test_invalid_token_is_refused(self):
        assert (
            requests.get(CUSTOMERS_ME, headers=_auth("bad.token.value")).status_code
            == 403
        )


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestPublicEndpoints:
    def test_catalogue_needs_no_credentials(self):
        assert requests.get(f"{_BASE}/v1/items/").status_code == 200

    def test_health_needs_no_credentials(self):
        assert requests.get(f"{_BASE}/health").status_code == 200

    def test_readiness_needs_no_credentials(self):
        assert requests.get(f"{_BASE}/health/ready").status_code == 200

    def test_openapi_is_reachable(self):
        assert requests.get(f"{_BASE}/openapi.json").status_code == 200


# ---------------------------------------------------------------------------
# The write surface is closed
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestNoAnonymousWrites:
    """
    Nothing that changes the shop may be done without an administrator's token.

    These endpoints were reachable by anyone who could open the port: a caller
    could create, alter or delete catalogue products, which is exactly what
    customers see in the store.
    """

    @staticmethod
    def _item_payload() -> dict:
        import uuid as _uuid

        unique = _uuid.uuid4().hex[:8].upper()
        return {
            "sku": f"SEC-{unique}",
            "status": "active",
            "name": "Security probe",
            "slug": f"sec-{unique.lower()}",
            "brand": "Probe",
            "categories": [],
            "price": {"amount": 100, "currency": "EUR", "includes_tax": True},
            "media": {"gallery": []},
            "inventory": {
                "stock_quantity": 1,
                "stock_status": "in_stock",
                "allow_backorder": False,
            },
            "shipping": {"is_physical": True, "shipping_class": "standard"},
            "attributes": {},
            "identifiers": {},
            "custom": {},
            "system": {"version": 1, "source": "api", "locale": "en_US"},
        }

    def test_anonymous_cannot_create_a_product(self):
        resp = requests.post(f"{_BASE}/v1/items/", json=self._item_payload())
        assert resp.status_code == 403

    def test_a_customer_cannot_create_a_product(self, customer_token):
        # Signed in is not the same as authorised.
        resp = requests.post(
            f"{_BASE}/v1/items/",
            json=self._item_payload(),
            headers=_auth(customer_token),
        )
        assert resp.status_code == 403

    def test_an_admin_from_the_storefront_cannot_create_a_product(
        self, admin_token_from_store
    ):
        resp = requests.post(
            f"{_BASE}/v1/items/",
            json=self._item_payload(),
            headers=_auth(admin_token_from_store),
        )
        assert resp.status_code == 403

    def test_an_admin_can_create_and_delete_a_product(self, admin_token):
        created = requests.post(
            f"{_BASE}/v1/items/", json=self._item_payload(), headers=_auth(admin_token)
        )
        assert created.status_code == 201
        uuid_ = created.json()["uuid"]
        deleted = requests.delete(
            f"{_BASE}/v1/items/{uuid_}", headers=_auth(admin_token)
        )
        assert deleted.status_code == 204

    def test_anonymous_cannot_delete_a_product(self, admin_token):
        created = requests.post(
            f"{_BASE}/v1/items/", json=self._item_payload(), headers=_auth(admin_token)
        )
        uuid_ = created.json()["uuid"]
        try:
            assert requests.delete(f"{_BASE}/v1/items/{uuid_}").status_code == 403
        finally:
            requests.delete(f"{_BASE}/v1/items/{uuid_}", headers=_auth(admin_token))

    def test_forged_admin_header_grants_nothing(self):
        # X-Admin-Key used to accept any non-empty value.
        resp = requests.post(
            f"{_BASE}/v1/items/",
            json=self._item_payload(),
            headers={"X-Admin-Key": "anything"},
        )
        assert resp.status_code == 403

    def test_forged_identity_header_grants_nothing(self):
        # X-Keycloak-User-ID used to name the caller.
        resp = requests.get(
            f"{_BASE}/v1/customers/me", headers={"X-Keycloak-User-ID": "kc-anything"}
        )
        assert resp.status_code == 403

    def test_forged_customer_header_grants_nothing(self):
        # X-Customer-ID used to attribute orders.
        resp = requests.post(
            f"{_BASE}/v1/orders/",
            json={"items": [], "currency": "EUR"},
            headers={"X-Customer-ID": "00000000-0000-0000-0000-000000000001"},
        )
        assert resp.status_code == 403

    def test_reads_stay_public_for_the_storefront(self):
        # Shoppers browse before signing in; closing this would close the shop.
        assert requests.get(f"{_BASE}/v1/items/").status_code == 200
