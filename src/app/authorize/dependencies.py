"""
Authorization Dependencies

The single place route handlers get identity from.

Two levels, matching how the product is used:

    require_admin           - back-office endpoints. Demands a verified token
                              carrying the admin realm role AND issued to an
                              admin frontend client.
    get_optional_principal  - everything else. Uses the token when one is sent
                              and stays anonymous otherwise; no role required,
                              so any registered customer can call these.

Why admin endpoints also check the client:
    Roles alone are not enough. If an administrator is browsing the storefront,
    their storefront token still carries the admin role. Accepting it would mean
    any XSS or malicious script in the shop could drive the back office. Pinning
    admin endpoints to the admin client's ``azp`` closes that.

No development shims:
    There is deliberately no header fallback. A header naming the caller is
    forgeable by anyone who can reach the port, so any such shim makes the
    whole surface writable by whoever finds it - and a shim enabled "only in
    development" is one environment variable away from being production.
    Tests obtain real tokens from Keycloak, which also means they exercise the
    path that actually ships.
"""

from fastapi import Depends
from fastapi.security import OAuth2AuthorizationCodeBearer

from app.shared.config import get_settings
from app.shared.exceptions import access_denied
from app.shared.logger import get_logger

from .token import Principal, authenticate

logger = get_logger(__name__)


def _keycloak_url(path: str) -> str:
    """
    Build a Keycloak endpoint URL from the browser-facing base.

    The documentation page runs in a browser, so it needs the public URL rather
    than the one the API uses internally.

    Args:
        path: Endpoint path below the realm.

    Returns:
        Absolute URL.
    """
    settings = get_settings()
    base = (settings.keycloak_public_url or settings.keycloak_url).rstrip("/")
    return f"{base}/realms/{settings.keycloak_realm}/protocol/openid-connect/{path}"


# Declaring the scheme is what puts a padlock on every protected operation in
# the generated documentation, and gives the docs page a working Authorize
# button. Without it the enforcement is invisible: the endpoints still refuse
# unauthenticated callers, but nothing in the schema says so, and a reader has
# to guess which routes need a token.
#
# auto_error=False because this dependency is also used where a token is
# optional; the refusals below are raised deliberately, with our own messages.
oauth2_scheme = OAuth2AuthorizationCodeBearer(
    authorizationUrl=_keycloak_url("auth"),
    tokenUrl=_keycloak_url("token"),
    refreshUrl=_keycloak_url("token"),
    scheme_name="Keycloak",
    auto_error=False,
    description=(
        "Keycloak access token. Admin endpoints additionally require the "
        "`admin` realm role and a token issued to an admin frontend client."
    ),
)


async def get_optional_principal(
    token: str | None = Depends(oauth2_scheme),
) -> Principal | None:
    """
    Identify the caller when they present a token, without requiring one.

    Args:
        token: Bearer token extracted by the security scheme, or None.

    Returns:
        Principal when a valid token was sent, otherwise None.

    Raises:
        AuthorizationError (403): If a token was sent but is not valid. An
            invalid token is a real error, not an anonymous request.
    """
    if token is None:
        return None
    return authenticate(token)


async def require_principal(
    principal: Principal | None = Depends(get_optional_principal),
) -> Principal:
    """
    Require a verified caller.

    Args:
        principal: Result of get_optional_principal.

    Returns:
        The Principal.

    Raises:
        AuthorizationError (403): When no token was supplied.
    """
    if principal is None:
        raise access_denied(
            resource="api",
            action="access",
            message="Authentication required. Send a Keycloak bearer token.",
        )
    return principal


async def require_admin(
    principal: Principal | None = Depends(get_optional_principal),
) -> Principal:
    """
    Enforce back-office access on an admin endpoint.

    Args:
        principal: Verified caller, if a bearer token was sent.

    Returns:
        The admin Principal.

    Raises:
        AuthorizationError (403): If the caller is unauthenticated, is not an
            administrator, or is an administrator arriving from a non-admin
            client.
    """
    settings = get_settings()

    if principal is not None:
        if not principal.has_role(settings.keycloak_admin_role):
            logger.warning(
                "Admin endpoint refused - role missing",
                extra={"subject": principal.subject, "client_id": principal.client_id},
            )
            raise access_denied(
                resource="admin",
                action="access",
                message=f"Requires the '{settings.keycloak_admin_role}' role.",
            )

        if principal.client_id not in settings.keycloak_admin_client_ids:
            logger.warning(
                "Admin endpoint refused - wrong client",
                extra={"subject": principal.subject, "client_id": principal.client_id},
            )
            raise access_denied(
                resource="admin",
                action="access",
                message=(
                    "Admin endpoints are reachable only from the admin frontend. "
                    "This token was issued to a different client."
                ),
            )
        return principal

    raise access_denied(
        resource="admin",
        action="access",
        message="Admin access required. Send a Keycloak bearer token from the admin frontend.",
    )


async def get_keycloak_id(
    principal: Principal | None = Depends(get_optional_principal),
) -> str:
    """
    Resolve the calling customer's Keycloak subject.

    Args:
        principal: Verified caller, if a bearer token was sent.

    Returns:
        The Keycloak subject claim.

    Raises:
        AuthorizationError (403): When the request carries no valid token.
    """
    if principal is not None:
        return principal.subject

    raise access_denied(
        resource="customer profile",
        action="access",
        message="Authentication required. Send a Keycloak bearer token.",
    )
