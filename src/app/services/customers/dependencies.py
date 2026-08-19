"""
Customers Dependencies

Identity for customer-facing endpoints.

``get_keycloak_id`` comes from ``app.authorize``: a verified bearer token wins,
and the X-Keycloak-User-ID shim is honoured only outside production.

``get_creation_claims`` gathers the profile fields used when ``GET /me``
auto-creates a customer on first call. With a token those come from verified
claims - e-mail, name and the optional phone number the user supplied during
registration. Without one (development) they fall back to headers.

Keycloak owns e-mail and phone; shipping addresses stay in this service,
because orders reference an address row by foreign key and labels are printed
from it. No field is stored in both places.
"""

from dataclasses import dataclass

from fastapi import Depends, Header

from app.authorize import Principal, get_keycloak_id, get_optional_principal
from app.shared.logger import get_logger

logger = get_logger(__name__)

__all__ = ["CreationClaims", "get_creation_claims", "get_keycloak_id"]


@dataclass(frozen=True)
class CreationClaims:
    """
    Identity details used to create a profile on first contact.

    Every field is optional here because they are only consulted when no
    profile exists yet. Which of them are mandatory is a business rule, so it
    is enforced in ``CustomerRepository.create_from_claims`` rather than in
    this transport-level dependency.
    """

    email: str | None
    first_name: str | None
    last_name: str | None
    phone: str | None = None


async def get_creation_claims(
    principal: Principal | None = Depends(get_optional_principal),
    x_customer_email: str | None = Header(
        default=None,
        alias="X-Customer-Email",
        description="[Dev-only] Ignored when a bearer token is present.",
    ),
    x_customer_first_name: str | None = Header(
        default=None,
        alias="X-Customer-First-Name",
        description="[Dev-only] Ignored when a bearer token is present.",
    ),
    x_customer_last_name: str | None = Header(
        default=None,
        alias="X-Customer-Last-Name",
        description="[Dev-only] Ignored when a bearer token is present.",
    ),
    x_customer_phone: str | None = Header(
        default=None,
        alias="X-Customer-Phone",
        description="[Dev-only] Ignored when a bearer token is present.",
    ),
) -> CreationClaims:
    """
    Collect the profile-creation claims for the calling customer.

    Args:
        principal:             Verified caller, when a bearer token was sent.
        x_customer_email:      Development fallback.
        x_customer_first_name: Development fallback.
        x_customer_last_name:  Development fallback.
        x_customer_phone:      Development fallback.

    Returns:
        CreationClaims from the token when one is present, otherwise from headers.
    """
    if principal is not None:
        return CreationClaims(
            email=principal.email,
            first_name=principal.first_name,
            last_name=principal.last_name,
            phone=principal.phone,
        )

    return CreationClaims(
        email=x_customer_email,
        first_name=x_customer_first_name,
        last_name=x_customer_last_name,
        phone=x_customer_phone,
    )
