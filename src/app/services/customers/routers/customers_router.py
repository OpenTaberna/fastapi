"""
Customers Router

FastAPI router for customer profile and address endpoints (Phase 0/1):

    GET    /customers/me                    — Get own profile (auto-create on first call)
    PATCH  /customers/me                    — Update own profile
    GET    /customers/me/addresses          — List all addresses
    POST   /customers/me/addresses          — Add a new address
    PATCH  /customers/me/addresses/{id}     — Update an address
    DELETE /customers/me/addresses/{id}     — Delete an address
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Header, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database.session import get_session_dependency
from app.shared.exceptions import entity_not_found, missing_field
from app.shared.logger import get_logger

from ..models import (
    AddressCreate,
    AddressResponse,
    AddressUpdate,
    CustomerDB,
    CustomerResponse,
    CustomerUpdate,
)
from ..responses import (
    CREATE_ADDRESS_RESPONSES,
    DELETE_ADDRESS_RESPONSES,
    GET_PROFILE_RESPONSES,
    LIST_ADDRESSES_RESPONSES,
    UPDATE_ADDRESS_RESPONSES,
    UPDATE_PROFILE_RESPONSES,
)
from ..services import get_address_repository, get_customer_repository

logger = get_logger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Auth shim
# ---------------------------------------------------------------------------
# TODO (Phase 1): Replace with Keycloak dependency once auth is wired up.
# All endpoints require only X-Keycloak-User-ID (the JWT sub claim).
# GET /me additionally accepts the profile-creation claims as optional headers;
# they are only required on the first call when the profile does not yet exist.


async def _get_keycloak_id(
    x_keycloak_user_id: str = Header(
        alias="X-Keycloak-User-ID",
        description="[Dev-only] Keycloak subject claim (sub). Replaced by JWT in production.",
    ),
) -> str:
    """Dependency for all endpoints except GET /me — only the subject claim is required."""
    return x_keycloak_user_id


# ---------------------------------------------------------------------------
# Shared helper
# ---------------------------------------------------------------------------


async def _get_customer_or_404(
    keycloak_user_id: str,
    session: AsyncSession,
) -> CustomerDB:
    """
    Look up the customer by Keycloak ID and raise 404 if not found.

    Used by all endpoints except GET /me (which auto-creates the profile).
    Callers should have previously hit GET /me to initialise the profile.
    """
    repo = get_customer_repository(session)
    customer = await repo.get_by_keycloak_id(keycloak_user_id)
    if customer is None:
        raise entity_not_found("Customer", keycloak_user_id)
    return customer


# ---------------------------------------------------------------------------
# GET /me — Get own profile (auto-create on first call)
# ---------------------------------------------------------------------------


@router.get(
    "/me",
    response_model=CustomerResponse,
    summary="Get my profile",
    description=(
        "Return the authenticated customer's profile. "
        "**Creates the profile automatically** on first call using the identity "
        "claims from the Keycloak token (dev: `X-Keycloak-User-ID` and related headers)."
    ),
    responses=GET_PROFILE_RESPONSES,
)
async def get_my_profile(
    keycloak_user_id: str = Depends(_get_keycloak_id),
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
    session: AsyncSession = Depends(get_session_dependency),
) -> CustomerResponse:
    repo = get_customer_repository(session)
    customer = await repo.get_by_keycloak_id(keycloak_user_id)
    if customer is not None:
        return CustomerResponse.model_validate(customer)
    # Profile does not exist yet — all creation fields are required.
    if not x_customer_email:
        raise missing_field("X-Customer-Email")
    if not x_customer_first_name:
        raise missing_field("X-Customer-First-Name")
    if not x_customer_last_name:
        raise missing_field("X-Customer-Last-Name")
    customer, _ = await repo.get_or_create(
        keycloak_user_id=keycloak_user_id,
        email=x_customer_email,
        first_name=x_customer_first_name,
        last_name=x_customer_last_name,
    )
    await session.commit()
    await session.refresh(customer)
    logger.info("New customer profile created", extra={"customer_id": str(customer.id)})
    return CustomerResponse.model_validate(customer)


# ---------------------------------------------------------------------------
# PATCH /me — Update own profile
# ---------------------------------------------------------------------------


@router.patch(
    "/me",
    response_model=CustomerResponse,
    summary="Update my profile",
    description=(
        "Partially update the authenticated customer's name or email. "
        "Returns **404** if the profile has not been created yet — call `GET /me` first."
    ),
    responses=UPDATE_PROFILE_RESPONSES,
)
async def update_my_profile(
    payload: CustomerUpdate,
    keycloak_user_id: str = Depends(_get_keycloak_id),
    session: AsyncSession = Depends(get_session_dependency),
) -> CustomerResponse:
    customer = await _get_customer_or_404(keycloak_user_id, session)
    repo = get_customer_repository(session)
    updated = await repo.update_customer(customer.id, payload)
    await session.commit()
    await session.refresh(updated)
    return CustomerResponse.model_validate(updated)


# ---------------------------------------------------------------------------
# GET /me/addresses — List all addresses
# ---------------------------------------------------------------------------


@router.get(
    "/me/addresses",
    response_model=list[AddressResponse],
    summary="List my addresses",
    description=(
        "Return all shipping addresses for the authenticated customer. "
        "Returns **404** if the profile has not been created yet — call `GET /me` first."
    ),
    responses=LIST_ADDRESSES_RESPONSES,
)
async def list_my_addresses(
    keycloak_user_id: str = Depends(_get_keycloak_id),
    session: AsyncSession = Depends(get_session_dependency),
) -> list[AddressResponse]:
    customer = await _get_customer_or_404(keycloak_user_id, session)
    address_repo = get_address_repository(session)
    addresses = await address_repo.get_for_customer(customer.id)
    return [AddressResponse.model_validate(a) for a in addresses]


# ---------------------------------------------------------------------------
# POST /me/addresses — Create a new address
# ---------------------------------------------------------------------------


@router.post(
    "/me/addresses",
    response_model=AddressResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an address",
    description=(
        "Add a new shipping address. "
        "If `is_default` is `true`, the existing default address is cleared first. "
        "Returns **404** if the profile has not been created yet — call `GET /me` first."
    ),
    responses=CREATE_ADDRESS_RESPONSES,
)
async def create_my_address(
    payload: AddressCreate,
    keycloak_user_id: str = Depends(_get_keycloak_id),
    session: AsyncSession = Depends(get_session_dependency),
) -> AddressResponse:
    customer = await _get_customer_or_404(keycloak_user_id, session)
    address_repo = get_address_repository(session)
    address = await address_repo.create_address(customer.id, payload)
    await session.commit()
    await session.refresh(address)
    logger.info(
        "Address created",
        extra={"address_id": str(address.id), "customer_id": str(customer.id)},
    )
    return AddressResponse.model_validate(address)


# ---------------------------------------------------------------------------
# PATCH /me/addresses/{id} — Update an address
# ---------------------------------------------------------------------------


@router.patch(
    "/me/addresses/{address_id}",
    response_model=AddressResponse,
    summary="Update an address",
    description=(
        "Partially update a shipping address. "
        "Returns **404** if the address or the customer profile does not exist, "
        "**403** if the address belongs to a different customer."
    ),
    responses=UPDATE_ADDRESS_RESPONSES,
)
async def update_my_address(
    address_id: UUID,
    payload: AddressUpdate,
    keycloak_user_id: str = Depends(_get_keycloak_id),
    session: AsyncSession = Depends(get_session_dependency),
) -> AddressResponse:
    customer = await _get_customer_or_404(keycloak_user_id, session)
    address_repo = get_address_repository(session)
    address = await address_repo.update_address(address_id, customer.id, payload)
    await session.commit()
    await session.refresh(address)
    return AddressResponse.model_validate(address)


# ---------------------------------------------------------------------------
# DELETE /me/addresses/{id} — Delete an address
# ---------------------------------------------------------------------------


@router.delete(
    "/me/addresses/{address_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an address",
    description=(
        "Delete a shipping address. "
        "Returns **404** if the address or the customer profile does not exist, "
        "**403** if the address belongs to a different customer."
    ),
    response_description="Address deleted successfully",
    responses=DELETE_ADDRESS_RESPONSES,
)
async def delete_my_address(
    address_id: UUID,
    keycloak_user_id: str = Depends(_get_keycloak_id),
    session: AsyncSession = Depends(get_session_dependency),
) -> None:
    customer = await _get_customer_or_404(keycloak_user_id, session)
    address_repo = get_address_repository(session)
    await address_repo.delete_address(address_id, customer.id)
    await session.commit()
    logger.info(
        "Address deleted",
        extra={"address_id": str(address_id), "customer_id": str(customer.id)},
    )
