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

Development shims:
    With no live Keycloak, X-Admin-Key and X-Keycloak-User-ID stand in for a
    token. They are honoured only while ``auth_allow_dev_headers`` is true,
    which a Settings validator forces off in production - they are trivially
    forged and would otherwise make every admin endpoint publicly writable.
    A bearer token, when present, always wins over a header.
"""

from fastapi import Depends, Header, Request

from app.shared.config import get_settings
from app.shared.exceptions import access_denied, missing_field
from app.shared.logger import get_logger

from .token import Principal, authenticate

logger = get_logger(__name__)

_BEARER_PREFIX = "bearer "


def bearer_token(request: Request) -> str | None:
    """
    Pull the raw bearer token out of the Authorization header.

    Args:
        request: Incoming request.

    Returns:
        The token, or None when no bearer credential was sent.
    """
    header = request.headers.get("Authorization", "")
    if header.lower().startswith(_BEARER_PREFIX):
        token = header[len(_BEARER_PREFIX) :].strip()
        return token or None
    return None


async def get_optional_principal(request: Request) -> Principal | None:
    """
    Identify the caller when they present a token, without requiring one.

    Args:
        request: Incoming request.

    Returns:
        Principal when a valid token was sent, otherwise None.

    Raises:
        AuthorizationError (403): If a token was sent but is not valid. An
            invalid token is a real error, not an anonymous request.
    """
    token = bearer_token(request)
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
    x_admin_key: str | None = Header(
        default=None,
        alias="X-Admin-Key",
        description="[Dev-only] Ignored in production; use a Keycloak bearer token.",
    ),
) -> Principal | None:
    """
    Enforce back-office access on an admin endpoint.

    Args:
        principal:   Verified caller, if a bearer token was sent.
        x_admin_key: Development shim, honoured outside production only.

    Returns:
        The admin Principal, or None when access was granted by the dev shim.

    Raises:
        AuthorizationError (403): If the caller is not an administrator, or is
            an administrator arriving from a non-admin client.
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

    # Any non-empty value passes, which is the contract this shim has always
    # had. Requiring a particular secret would buy nothing - the header is
    # forgeable by design and is refused outright in production.
    if settings.auth_allow_dev_headers and x_admin_key:
        logger.warning("Admin access granted via development header shim")
        return None

    raise access_denied(
        resource="admin",
        action="access",
        message="Admin access required. Send a Keycloak bearer token from the admin frontend.",
    )


async def get_keycloak_id(
    principal: Principal | None = Depends(get_optional_principal),
    x_keycloak_user_id: str | None = Header(
        default=None,
        alias="X-Keycloak-User-ID",
        description="[Dev-only] Ignored in production; use a Keycloak bearer token.",
    ),
) -> str:
    """
    Resolve the calling customer's Keycloak subject.

    A verified token always wins. The header is a development convenience and
    is refused in production, where trusting it would let anyone read and
    modify any customer's profile by guessing an id.

    Args:
        principal:          Verified caller, if a bearer token was sent.
        x_keycloak_user_id: Development shim.

    Returns:
        The Keycloak subject claim.

    Raises:
        AuthorizationError (403): When neither a token nor an accepted shim is present.
    """
    if principal is not None:
        return principal.subject

    settings = get_settings()
    if settings.auth_allow_dev_headers and x_keycloak_user_id:
        return x_keycloak_user_id

    raise access_denied(
        resource="customer profile",
        action="access",
        message="Authentication required. Send a Keycloak bearer token.",
    )


async def require_field(value: str | None, field_name: str) -> str:
    """
    Assert an identity field the caller must supply.

    Args:
        value:      Value to check.
        field_name: Name used in the error.

    Returns:
        The value.

    Raises:
        ValidationError (422): When the value is missing.
    """
    if not value:
        raise missing_field(field_name)
    return value
