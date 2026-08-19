"""
Customers Dependencies

FastAPI dependency functions for the customers service.

Keeping these in a dedicated module (matching the pattern of
services/admin/dependencies.py and services/payments/dependencies.py) keeps
the router free of identity handling, makes the dependencies independently
testable, and gives the Keycloak integration a single place to land: when
JWT auth replaces the dev shim, only this module changes and no route
handler is touched.
"""

from dataclasses import dataclass

from fastapi import Header

from app.shared.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Auth shim
# ---------------------------------------------------------------------------
# TODO (Phase 1): Replace with a Keycloak JWT dependency once auth is wired
# up. The subject claim currently arrives as a header; in production it will
# be read from the validated token instead. Call sites do not change.


async def get_keycloak_id(
    x_keycloak_user_id: str = Header(
        alias="X-Keycloak-User-ID",
        description="[Dev-only] Keycloak subject claim (sub). Replaced by JWT in production.",
    ),
) -> str:
    """
    Resolve the caller's Keycloak subject claim.

    Required by every customer endpoint — it is the identity the profile and
    all addresses hang off.

    Args:
        x_keycloak_user_id: Value of the X-Keycloak-User-ID request header.

    Returns:
        The Keycloak subject claim as a string.
    """
    return x_keycloak_user_id


# ---------------------------------------------------------------------------
# Profile-creation claims
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CreationClaims:
    """
    Identity claims needed to auto-create a profile on first GET /me.

    Every field is optional here because they are only consulted when no
    profile exists yet.  Whether a given field is actually required is a
    business rule, so it is enforced in CustomerRepository.create_from_claims
    rather than in this transport-level dependency.

    In production these values come from the Keycloak token rather than
    headers; only this module changes when that happens.
    """

    email: str | None
    first_name: str | None
    last_name: str | None


async def get_creation_claims(
    x_customer_email: str | None = Header(
        default=None,
        alias="X-Customer-Email",
        description="[Dev-only] Required only on first call (profile creation). Customer email address.",
    ),
    x_customer_first_name: str | None = Header(
        default=None,
        alias="X-Customer-First-Name",
        description="[Dev-only] Required only on first call (profile creation). Customer given name.",
    ),
    x_customer_last_name: str | None = Header(
        default=None,
        alias="X-Customer-Last-Name",
        description="[Dev-only] Required only on first call (profile creation). Customer family name.",
    ),
) -> CreationClaims:
    """
    Collect the optional profile-creation claims from the request headers.

    Args:
        x_customer_email:      X-Customer-Email header, if sent.
        x_customer_first_name: X-Customer-First-Name header, if sent.
        x_customer_last_name:  X-Customer-Last-Name header, if sent.

    Returns:
        CreationClaims holding whatever was supplied. Validation of which
        fields are mandatory belongs to the service layer.
    """
    return CreationClaims(
        email=x_customer_email,
        first_name=x_customer_first_name,
        last_name=x_customer_last_name,
    )
