"""
Real Keycloak tokens for the integration tests.

The API has no header shim any more, so tests authenticate the way the
frontends do. That costs a token request per session and gains something worth
more: the tests exercise the code path that actually ships, rather than a
bypass that only exists for them.

Accounts come from the realm committed at ``keycloak/opentaberna-realm.json``.
"""

import os
from functools import lru_cache

import pytest
import requests

_KEYCLOAK = os.getenv("TEST_KEYCLOAK_URL", "http://localhost:8080")
_TOKEN_URL = f"{_KEYCLOAK}/realms/opentaberna/protocol/openid-connect/token"

ADMIN_CLIENT = "opentaberna-admin-ui"
STORE_CLIENT = "opentaberna-store-ui"

# Seeded development accounts.
ADMIN = ("adminuser", "adminpassword")
CUSTOMER = ("testuser", "testpassword")
OTHER_CUSTOMER = ("testuser2", "testpassword2")


@lru_cache(maxsize=8)
def token(client_id: str, username: str, password: str) -> str:
    """
    Obtain an access token, or skip the test when Keycloak is unreachable.

    Cached per account for the session: these tests make many calls and there
    is no value in re-authenticating for each one.

    Args:
        client_id: Keycloak client to authenticate against.
        username:  Account username.
        password:  Account password.

    Returns:
        The raw access token.
    """
    try:
        response = requests.post(
            _TOKEN_URL,
            data={
                "client_id": client_id,
                "grant_type": "password",
                "username": username,
                "password": password,
            },
            timeout=20,
        )
    except requests.RequestException as exc:  # pragma: no cover - environment
        # allow_module_level, because header constants are built at import
        # time; without it an unreachable Keycloak is a collection error
        # rather than a clean skip.
        pytest.skip(f"Keycloak is not reachable: {exc}", allow_module_level=True)

    if response.status_code != 200:  # pragma: no cover - environment
        pytest.skip(
            f"Could not authenticate {username}: {response.text[:120]}",
            allow_module_level=True,
        )

    return response.json()["access_token"]


def admin_headers() -> dict[str, str]:
    """Authorization header for an administrator, from the admin frontend."""
    return {"Authorization": f"Bearer {token(ADMIN_CLIENT, *ADMIN)}"}


def customer_headers() -> dict[str, str]:
    """Authorization header for the primary test customer."""
    return {"Authorization": f"Bearer {token(STORE_CLIENT, *CUSTOMER)}"}


def other_customer_headers() -> dict[str, str]:
    """Authorization header for a second customer, for cross-account checks."""
    return {"Authorization": f"Bearer {token(STORE_CLIENT, *OTHER_CUSTOMER)}"}


def admin_headers_from_store() -> dict[str, str]:
    """
    The administrator, but signed into the storefront client.

    Admin endpoints must refuse this: the role is present, the client is not
    the admin frontend.
    """
    return {"Authorization": f"Bearer {token(STORE_CLIENT, *ADMIN)}"}
