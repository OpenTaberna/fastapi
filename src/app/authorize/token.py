"""
Keycloak Access-Token Validation

Verifies bearer tokens issued by the Keycloak realm and turns them into a
``Principal``.

What is checked, and why each one matters:
    - **Signature** against the realm's published JWKS. Without it a caller
      could hand us any JSON they like.
    - **Issuer** must equal the realm's issuer URL, so a token minted by a
      different Keycloak (or a different realm on the same server) is refused.
    - **Audience** must include this API. Public frontend clients otherwise
      receive tokens scoped only to ``account``; accepting those would let a
      token meant for an unrelated service authenticate here.
    - **Expiry**, handled by PyJWT.

Key handling:
    Signing keys are fetched from the realm's JWKS endpoint and cached by
    ``PyJWKClient`` for ``keycloak_jwks_cache_seconds``. Keycloak rotates keys,
    so the cache has to expire rather than being fetched once at startup.

Two URLs, deliberately:
    Inside Docker the API reaches Keycloak over the compose network while the
    browser reaches it on localhost, so the token's ``iss`` does not match the
    address the API fetches keys from. ``keycloak_url`` is used to fetch,
    ``keycloak_public_url`` to validate ``iss``.
"""

from dataclasses import dataclass, field
from functools import lru_cache

import jwt
from jwt import PyJWKClient

from app.shared.config import get_settings
from app.shared.exceptions import access_denied
from app.shared.logger import get_logger

logger = get_logger(__name__)


class TokenError(Exception):
    """Raised when a bearer token cannot be trusted."""


@dataclass(frozen=True)
class Principal:
    """
    The authenticated caller, as described by a verified access token.

    Attributes:
        subject:    Keycloak user id (the ``sub`` claim). Stable for the life
                    of the account and used as ``customers.keycloak_user_id``.
        username:   Preferred username, for logs.
        email:      Verified e-mail from the token, or None.
        phone:      Optional ``phone_number`` claim the user may have supplied.
        first_name: Given name, or None.
        last_name:  Family name, or None.
        roles:      Realm roles granted to the user.
        client_id:  The ``azp`` claim - which frontend obtained this token.
    """

    subject: str
    username: str | None = None
    email: str | None = None
    phone: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    roles: frozenset[str] = field(default_factory=frozenset)
    client_id: str | None = None

    def has_role(self, role: str) -> bool:
        """
        Args:
            role: Realm role name to test for.

        Returns:
            True if the token carries the role.
        """
        return role in self.roles


def issuer_url() -> str:
    """
    Build the issuer string tokens from this realm must carry.

    Returns:
        e.g. ``http://localhost:8080/realms/opentaberna``
    """
    settings = get_settings()
    base = (settings.keycloak_public_url or settings.keycloak_url).rstrip("/")
    return f"{base}/realms/{settings.keycloak_realm}"


def jwks_url() -> str:
    """
    Build the JWKS endpoint the API fetches signing keys from.

    Returns:
        e.g. ``http://opentaberna-keycloak:8080/realms/opentaberna/protocol/openid-connect/certs``
    """
    settings = get_settings()
    base = settings.keycloak_url.rstrip("/")
    return f"{base}/realms/{settings.keycloak_realm}/protocol/openid-connect/certs"


@lru_cache(maxsize=1)
def _jwk_client() -> PyJWKClient:
    """
    Return the process-wide JWKS client.

    Cached because it holds the key cache; building a new one per request would
    hit Keycloak on every call.

    Returns:
        Configured PyJWKClient.
    """
    settings = get_settings()
    return PyJWKClient(
        jwks_url(),
        cache_keys=True,
        lifespan=settings.keycloak_jwks_cache_seconds,
    )


def reset_key_cache() -> None:
    """Drop the cached JWKS client. Used by tests and after a config change."""
    _jwk_client.cache_clear()


def decode_token(token: str) -> dict:
    """
    Verify a bearer token and return its claims.

    Args:
        token: Raw JWT from the Authorization header.

    Returns:
        The decoded claim set.

    Raises:
        TokenError: If the signature, issuer, audience or expiry is not valid.
    """
    settings = get_settings()
    try:
        signing_key = _jwk_client().get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256", "RS512", "ES256", "ES512"],
            audience=settings.keycloak_client_id,
            issuer=issuer_url(),
            options={"require": ["exp", "iat", "iss", "sub"]},
        )
    except jwt.PyJWTError as exc:
        # Deliberately not echoing the token or the library message back to the
        # caller - it can disclose why a forged token failed.
        logger.warning("Bearer token rejected", extra={"reason": type(exc).__name__})
        raise TokenError(str(exc)) from exc
    except Exception as exc:  # JWKS fetch failures land here
        logger.error(
            "Could not verify bearer token",
            extra={"error": str(exc), "jwks_url": jwks_url()},
            exc_info=True,
        )
        raise TokenError("Token verification unavailable") from exc


def principal_from_claims(claims: dict) -> Principal:
    """
    Map a verified claim set onto a Principal.

    Args:
        claims: Output of decode_token.

    Returns:
        Principal describing the caller.
    """
    realm_access = claims.get("realm_access") or {}
    return Principal(
        subject=claims["sub"],
        username=claims.get("preferred_username"),
        email=claims.get("email"),
        phone=claims.get("phone_number"),
        first_name=claims.get("given_name"),
        last_name=claims.get("family_name"),
        roles=frozenset(realm_access.get("roles") or ()),
        client_id=claims.get("azp"),
    )


def authenticate(token: str) -> Principal:
    """
    Verify a token and describe its bearer.

    Args:
        token: Raw JWT.

    Returns:
        Principal for the token.

    Raises:
        AuthorizationError (403): If the token cannot be trusted.
    """
    try:
        return principal_from_claims(decode_token(token))
    except TokenError as exc:
        raise access_denied(
            resource="api",
            action="access",
            message="Invalid or expired access token.",
        ) from exc
