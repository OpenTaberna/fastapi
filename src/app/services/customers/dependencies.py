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
from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.authorize import Principal, get_keycloak_id, get_optional_principal
from app.shared.database.session import get_session_dependency
from app.shared.logger import get_logger

from .services import get_customer_repository

logger = get_logger(__name__)

__all__ = [
    "CreationClaims",
    "get_creation_claims",
    "get_current_customer_id",
    "get_keycloak_id",
]


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
) -> CreationClaims:
    """
    Collect the profile-creation claims for the calling customer.

    Taken solely from the verified token. There is no header fallback: a caller
    able to state their own e-mail and name could otherwise claim any identity.

    Args:
        principal: Verified caller, when a bearer token was sent.

    Returns:
        CreationClaims from the token, or empty when unauthenticated.
    """
    if principal is None:
        return CreationClaims(email=None, first_name=None, last_name=None, phone=None)

    return CreationClaims(
        email=principal.email,
        first_name=principal.first_name,
        last_name=principal.last_name,
        phone=principal.phone,
    )


async def get_current_customer_id(
    keycloak_user_id: str = Depends(get_keycloak_id),
    claims: CreationClaims = Depends(get_creation_claims),
    session: AsyncSession = Depends(get_session_dependency),
) -> UUID:
    """
    Resolve the caller's internal customer id from their token.

    Orders, returns and anything else customer-scoped reference
    ``customers.id``, while a token carries the Keycloak subject. This maps one
    to the other, creating the profile on first contact exactly as ``GET /me``
    does, so a shopper's first action does not fail because they have never
    opened their profile page.

    Args:
        keycloak_user_id: Subject claim of the verified token.
        claims:           Identity claims used if the profile must be created.
        session:          Database session.

    Returns:
        The internal customer UUID.

    Raises:
        AuthorizationError (403): If the request carries no valid token.
        ValidationError (422):    If a profile must be created but the token
            lacks the required claims.
    """
    repo = get_customer_repository(session)
    customer = await repo.get_by_keycloak_id(keycloak_user_id)
    if customer is None:
        customer = await repo.create_from_claims(
            keycloak_user_id=keycloak_user_id,
            email=claims.email,
            first_name=claims.first_name,
            last_name=claims.last_name,
            phone=claims.phone,
        )
        await session.commit()
        logger.info(
            "Customer profile created on first authenticated call",
            extra={"customer_id": str(customer.id)},
        )
    return customer.id
