"""
Unit tests for Keycloak authorization.

No network and no Keycloak: tokens are signed with a throwaway RSA key and the
JWKS lookup is patched, so the real validation path runs against known input.

Covers:
    - decode_token: signature, issuer, audience, expiry, required claims
    - principal_from_claims
    - require_admin: role check, admin-client check, dev shim
    - get_keycloak_id: token wins over header; header refused when disabled
"""

import time
from unittest.mock import MagicMock, patch

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.authorize import token as token_mod
from app.authorize.dependencies import (
    get_keycloak_id,
    get_optional_principal,
    require_admin,
)
from app.authorize.token import (
    Principal,
    TokenError,
    decode_token,
    principal_from_claims,
)
from app.shared.exceptions.errors import AuthorizationError

ISSUER = "http://localhost:8080/realms/opentaberna"
AUDIENCE = "opentaberna-api"

_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _make_token(**overrides) -> str:
    """Sign a token with the test key, overriding any claim."""
    now = int(time.time())
    claims = {
        "sub": "user-123",
        "iss": ISSUER,
        "aud": AUDIENCE,
        "iat": now,
        "exp": now + 300,
        "azp": "opentaberna-admin-ui",
        "preferred_username": "adminuser",
        "email": "admin@opentaberna.dev",
        "given_name": "Admin",
        "family_name": "User",
        "realm_access": {"roles": ["admin", "customer"]},
    }
    claims.update(overrides)
    for k, v in list(claims.items()):
        if v is None:
            del claims[k]
    return jwt.encode(claims, _KEY, algorithm="RS256")


class _FakeSigningKey:
    key = _KEY.public_key()


def _patched_decode(tok: str):
    """Run the real decode_token with the JWKS lookup stubbed out."""
    client = MagicMock()
    client.get_signing_key_from_jwt.return_value = _FakeSigningKey()
    with patch.object(token_mod, "_jwk_client", return_value=client):
        return decode_token(tok)


# ---------------------------------------------------------------------------
# Token validation
# ---------------------------------------------------------------------------


class TestDecodeToken:
    def test_accepts_a_well_formed_token(self):
        assert _patched_decode(_make_token())["sub"] == "user-123"

    def test_rejects_a_token_signed_by_another_key(self):
        other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        forged = jwt.encode(
            {
                "sub": "x",
                "iss": ISSUER,
                "aud": AUDIENCE,
                "iat": int(time.time()),
                "exp": int(time.time()) + 300,
            },
            other,
            algorithm="RS256",
        )
        with pytest.raises(TokenError):
            _patched_decode(forged)

    def test_rejects_an_expired_token(self):
        past = int(time.time()) - 10
        with pytest.raises(TokenError):
            _patched_decode(_make_token(exp=past, iat=past - 300))

    def test_rejects_a_foreign_issuer(self):
        # A token from another Keycloak or another realm must not authenticate.
        with pytest.raises(TokenError):
            _patched_decode(_make_token(iss="http://evil.example/realms/other"))

    def test_rejects_a_token_for_a_different_audience(self):
        # Public clients get "account" by default; accepting that would let a
        # token meant for an unrelated service in.
        with pytest.raises(TokenError):
            _patched_decode(_make_token(aud="account"))

    def test_accepts_audience_list_containing_the_api(self):
        assert (
            _patched_decode(_make_token(aud=[AUDIENCE, "account"]))["sub"] == "user-123"
        )

    def test_rejects_a_token_without_sub(self):
        # Keycloak drops sub when the "basic" client scope is missing, which
        # would otherwise leave the API with no identity to key off.
        with pytest.raises(TokenError):
            _patched_decode(_make_token(sub=None))

    def test_rejects_unparseable_garbage(self):
        with pytest.raises(TokenError):
            _patched_decode("not.a.token")


class TestPrincipalFromClaims:
    def test_maps_the_identity_claims(self):
        p = principal_from_claims(_patched_decode(_make_token()))
        assert p.subject == "user-123"
        assert p.email == "admin@opentaberna.dev"
        assert p.client_id == "opentaberna-admin-ui"

    def test_maps_realm_roles(self):
        p = principal_from_claims(_patched_decode(_make_token()))
        assert p.has_role("admin") and p.has_role("customer")

    def test_maps_the_optional_phone_claim(self):
        p = principal_from_claims(_patched_decode(_make_token(phone_number="+49 30 1")))
        assert p.phone == "+49 30 1"

    def test_phone_is_none_when_not_supplied(self):
        assert principal_from_claims(_patched_decode(_make_token())).phone is None

    def test_missing_realm_access_yields_no_roles(self):
        p = principal_from_claims(_patched_decode(_make_token(realm_access=None)))
        assert p.roles == frozenset()


class TestOpenApiSecurity:
    """
    The published schema must say which operations need a token.

    Enforcement that is invisible in the documentation gets rediscovered by
    trial and error, and a reader cannot tell a route that is deliberately
    public from one that was left unprotected by accident.
    """

    @staticmethod
    def _spec():
        from app.main import app

        return app.openapi()

    def test_a_security_scheme_is_declared(self):
        schemes = self._spec()["components"]["securitySchemes"]
        assert "Keycloak" in schemes
        assert schemes["Keycloak"]["type"] == "oauth2"

    def test_the_scheme_points_at_the_realm(self):
        flow = self._spec()["components"]["securitySchemes"]["Keycloak"]["flows"][
            "authorizationCode"
        ]
        assert flow["authorizationUrl"].endswith(
            "/realms/opentaberna/protocol/openid-connect/auth"
        )
        assert flow["tokenUrl"].endswith(
            "/realms/opentaberna/protocol/openid-connect/token"
        )

    @pytest.mark.parametrize(
        ("method", "path"),
        [
            ("post", "/v1/items/"),
            ("patch", "/v1/items/{item_uuid}"),
            ("delete", "/v1/items/{item_uuid}"),
            ("put", "/v1/items/{item_uuid}/image"),
            ("post", "/v1/admin/inventory/"),
            ("patch", "/v1/admin/orders/{order_id}/status"),
            ("get", "/v1/customers/me"),
            ("post", "/v1/orders/"),
        ],
    )
    def test_protected_operations_carry_security(self, method, path):
        assert self._spec()["paths"][path][method].get("security")

    @pytest.mark.parametrize(
        ("method", "path"),
        [
            ("get", "/v1/items/"),
            ("get", "/v1/items/{item_uuid}"),
            ("get", "/v1/items/{item_uuid}/image"),
            ("get", "/health"),
        ],
    )
    def test_public_operations_carry_none(self, method, path):
        assert not self._spec()["paths"][path][method].get("security")


# ---------------------------------------------------------------------------
# require_admin
# ---------------------------------------------------------------------------


def _principal(roles=("admin",), client="opentaberna-admin-ui") -> Principal:
    return Principal(subject="u1", roles=frozenset(roles), client_id=client)


class TestRequireAdmin:
    async def test_admin_from_the_admin_client_is_allowed(self):
        assert await require_admin(principal=_principal()) is not None

    async def test_admin_from_the_store_client_is_refused(self):
        # An admin browsing the shop still carries the admin role; accepting
        # that token would let shop-side script drive the back office.
        with pytest.raises(AuthorizationError):
            await require_admin(principal=_principal(client="opentaberna-store-ui"))

    async def test_non_admin_is_refused(self):
        with pytest.raises(AuthorizationError):
            await require_admin(principal=_principal(roles=("customer",)))

    async def test_unknown_client_is_refused(self):
        with pytest.raises(AuthorizationError):
            await require_admin(principal=_principal(client="some-other-app"))

    async def test_no_credentials_is_refused(self):
        with pytest.raises(AuthorizationError):
            await require_admin(principal=None)

    async def test_takes_no_header_credential_at_all(self):
        # The old X-Admin-Key shim is gone. Keeping this as a signature check
        # means re-adding a header credential fails loudly rather than quietly
        # reopening the whole admin surface.
        import inspect

        params = set(inspect.signature(require_admin).parameters)
        assert params == {"principal"}


# ---------------------------------------------------------------------------
# get_keycloak_id
# ---------------------------------------------------------------------------


class TestGetKeycloakId:
    async def test_uses_the_token_subject(self):
        assert await get_keycloak_id(principal=_principal()) == "u1"

    async def test_refuses_when_nothing_is_supplied(self):
        with pytest.raises(AuthorizationError):
            await get_keycloak_id(principal=None)

    async def test_takes_no_header_credential_at_all(self):
        # A header naming the caller is forgeable by anyone who can reach the
        # port; there must be no way to supply one.
        import inspect

        assert set(inspect.signature(get_keycloak_id).parameters) == {"principal"}


class TestGetOptionalPrincipal:
    async def test_none_without_a_token(self):
        assert await get_optional_principal(token=None) is None

    async def test_an_invalid_token_is_an_error_not_anonymity(self):
        # Silently treating a bad token as "not logged in" hides expiry and
        # misconfiguration from the caller.
        with pytest.raises(AuthorizationError):
            await get_optional_principal(token="bad.token.here")


class TestNoDevelopmentBypass:
    def test_settings_carry_no_dev_header_switch(self):
        # There is no environment in which a forgeable header is accepted, so
        # there is no flag to get wrong.
        from app.shared.config.settings import Settings

        assert "auth_allow_dev_headers" not in Settings.model_fields
