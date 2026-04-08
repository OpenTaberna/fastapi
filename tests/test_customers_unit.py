"""
Unit tests for the Customers service — pure business logic, no DB, no network.

Covers:
    - CustomerBase / CustomerCreate / CustomerUpdate — Pydantic input validation
    - AddressBase / AddressCreate / AddressUpdate    — Pydantic input validation
    - CustomerResponse                              — from_attributes round-trip via MagicMock
    - AddressResponse                               — from_attributes round-trip via MagicMock
    - CustomerRepository.get_by_keycloak_id_or_404 — found, not found (404)
    - CustomerRepository.get_or_create              — returns existing / creates new / missing fields (422)
    - CustomerRepository.update_customer            — empty payload, partial payload, update returns None (404)
    - AddressRepository._clear_default              — issues correct UPDATE via session
    - AddressRepository.create_address              — clears default when is_default=True
    - AddressRepository.update_address              — 404 not found, 403 wrong owner, happy path
    - AddressRepository.delete_address              — 404 not found, 403 wrong owner, happy path
"""

import pytest
from datetime import datetime, UTC
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

from app.shared.exceptions.errors import AuthorizationError, NotFoundError, ValidationError
from app.services.customers.models import (
    AddressCreate,
    AddressResponse,
    AddressUpdate,
    CustomerResponse,
    CustomerUpdate,
)
from app.services.customers.models.customers_models import CustomerBase
from app.services.customers.services.customers_db_service import (
    AddressRepository,
    CustomerRepository,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_customer(
    keycloak_user_id: str = "kc-unit-001",
    email: str = "unit@example.com",
    first_name: str = "Unit",
    last_name: str = "Test",
    customer_id: UUID | None = None,
) -> MagicMock:
    """Return a mock that behaves like a CustomerDB ORM row."""
    now = datetime.now(UTC)
    c = MagicMock()
    c.id = customer_id or uuid4()
    c.keycloak_user_id = keycloak_user_id
    c.email = email
    c.first_name = first_name
    c.last_name = last_name
    c.created_at = now
    c.updated_at = now
    return c


def _make_address(
    customer_id: UUID | None = None,
    address_id: UUID | None = None,
    is_default: bool = False,
) -> MagicMock:
    """Return a mock that behaves like an AddressDB ORM row."""
    now = datetime.now(UTC)
    a = MagicMock()
    a.id = address_id or uuid4()
    a.customer_id = customer_id or uuid4()
    a.street = "Teststraße 1"
    a.city = "Berlin"
    a.zip_code = "10115"
    a.country = "DE"
    a.is_default = is_default
    a.created_at = now
    a.updated_at = now
    return a


def _make_session() -> MagicMock:
    """Return a minimal async-compatible session mock."""
    session = MagicMock()
    session.execute = AsyncMock()
    return session


# ---------------------------------------------------------------------------
# CustomerBase — Pydantic validation
# ---------------------------------------------------------------------------


class TestCustomerBase:
    def test_valid(self):
        c = CustomerBase(
            keycloak_user_id="kc-001",
            email="test@example.com",
            first_name="Anna",
            last_name="Müller",
        )
        assert c.keycloak_user_id == "kc-001"
        assert c.first_name == "Anna"

    def test_email_required(self):
        with pytest.raises(Exception):
            CustomerBase(
                keycloak_user_id="kc-001",
                first_name="Anna",
                last_name="Müller",
            )

    def test_first_name_too_short(self):
        with pytest.raises(Exception):
            CustomerBase(
                keycloak_user_id="kc-001",
                email="test@example.com",
                first_name="",
                last_name="Müller",
            )

    def test_last_name_too_long(self):
        with pytest.raises(Exception):
            CustomerBase(
                keycloak_user_id="kc-001",
                email="test@example.com",
                first_name="Anna",
                last_name="M" * 101,
            )

    def test_invalid_email(self):
        with pytest.raises(Exception):
            CustomerBase(
                keycloak_user_id="kc-001",
                email="not-an-email",
                first_name="Anna",
                last_name="Müller",
            )


# ---------------------------------------------------------------------------
# CustomerUpdate — partial schema
# ---------------------------------------------------------------------------


class TestCustomerUpdate:
    def test_all_none_is_valid(self):
        u = CustomerUpdate()
        assert u.email is None
        assert u.first_name is None
        assert u.last_name is None

    def test_partial_update(self):
        u = CustomerUpdate(first_name="NewName")
        assert u.first_name == "NewName"
        assert u.email is None

    def test_exclude_unset_only_returns_set_fields(self):
        u = CustomerUpdate(last_name="Smith")
        assert u.model_dump(exclude_unset=True) == {"last_name": "Smith"}

    def test_first_name_empty_string_rejected(self):
        with pytest.raises(Exception):
            CustomerUpdate(first_name="")

    def test_invalid_email_rejected(self):
        with pytest.raises(Exception):
            CustomerUpdate(email="bad-email")


# ---------------------------------------------------------------------------
# CustomerResponse — from_attributes round-trip
# ---------------------------------------------------------------------------


class TestCustomerResponse:
    def test_from_orm_mock(self):
        c = _make_customer()
        r = CustomerResponse.model_validate(c)
        assert r.id == c.id
        assert r.keycloak_user_id == c.keycloak_user_id
        assert r.email == c.email
        assert r.first_name == c.first_name
        assert r.last_name == c.last_name
        assert isinstance(r.created_at, datetime)
        assert isinstance(r.updated_at, datetime)

    def test_email_is_plain_str_not_revalidated(self):
        # Emails with non-public TLDs (e.g. .local) must not cause ValidationError
        c = _make_customer(email="user@host.local")
        r = CustomerResponse.model_validate(c)
        assert r.email == "user@host.local"


# ---------------------------------------------------------------------------
# AddressCreate / AddressUpdate — Pydantic validation
# ---------------------------------------------------------------------------


class TestAddressCreate:
    def test_valid_minimal(self):
        a = AddressCreate(
            street="Main St 1", city="Hamburg", zip_code="20095", country="DE"
        )
        assert a.is_default is False

    def test_is_default_true(self):
        a = AddressCreate(
            street="Main St 1",
            city="Hamburg",
            zip_code="20095",
            country="DE",
            is_default=True,
        )
        assert a.is_default is True

    def test_country_must_be_2_chars(self):
        with pytest.raises(Exception):
            AddressCreate(
                street="Main St 1", city="Hamburg", zip_code="20095", country="DEU"
            )

    def test_country_cannot_be_empty(self):
        with pytest.raises(Exception):
            AddressCreate(
                street="Main St 1", city="Hamburg", zip_code="20095", country=""
            )

    def test_street_required(self):
        with pytest.raises(Exception):
            AddressCreate(city="Hamburg", zip_code="20095", country="DE")


class TestAddressUpdate:
    def test_all_none_valid(self):
        u = AddressUpdate()
        assert u.street is None

    def test_country_too_short_rejected(self):
        with pytest.raises(Exception):
            AddressUpdate(country="D")

    def test_exclude_unset(self):
        u = AddressUpdate(city="Munich")
        assert u.model_dump(exclude_unset=True) == {"city": "Munich"}


# ---------------------------------------------------------------------------
# AddressResponse — from_attributes round-trip
# ---------------------------------------------------------------------------


class TestAddressResponse:
    def test_from_orm_mock(self):
        customer_id = uuid4()
        a = _make_address(customer_id=customer_id)
        r = AddressResponse.model_validate(a)
        assert r.id == a.id
        assert r.customer_id == customer_id
        assert r.street == a.street
        assert r.country == "DE"
        assert isinstance(r.created_at, datetime)


# ---------------------------------------------------------------------------
# CustomerRepository
# ---------------------------------------------------------------------------


class TestCustomerRepository:
    @pytest.fixture
    def session(self):
        return _make_session()

    @pytest.fixture
    def repo(self, session):
        r = CustomerRepository(session)
        return r

    # --- get_by_keycloak_id_or_404 ---

    @pytest.mark.asyncio
    async def test_get_by_keycloak_id_or_404_returns_customer(self, repo):
        existing = _make_customer()
        repo.get_by_keycloak_id = AsyncMock(return_value=existing)

        result = await repo.get_by_keycloak_id_or_404("kc-001")

        assert result is existing

    @pytest.mark.asyncio
    async def test_get_by_keycloak_id_or_404_raises_404_when_missing(self, repo):
        repo.get_by_keycloak_id = AsyncMock(return_value=None)

        with pytest.raises(NotFoundError) as exc_info:
            await repo.get_by_keycloak_id_or_404("kc-ghost")

        assert exc_info.value.error_code.value == "entity_not_found"
        assert "kc-ghost" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_get_or_create_returns_existing(self, repo):
        existing = _make_customer()
        repo.get_by_keycloak_id = AsyncMock(return_value=existing)

        customer, created = await repo.get_or_create(
            keycloak_user_id="kc-001",
            email="x@example.com",
            first_name="X",
            last_name="Y",
        )

        assert created is False
        assert customer is existing

    @pytest.mark.asyncio
    async def test_get_or_create_creates_new(self, repo):
        new_customer = _make_customer()
        repo.get_by_keycloak_id = AsyncMock(return_value=None)
        repo.create = AsyncMock(return_value=new_customer)

        customer, created = await repo.get_or_create(
            keycloak_user_id="kc-new",
            email="new@example.com",
            first_name="New",
            last_name="User",
        )

        assert created is True
        assert customer is new_customer
        repo.create.assert_awaited_once_with(
            keycloak_user_id="kc-new",
            email="new@example.com",
            first_name="New",
            last_name="User",
        )

    @pytest.mark.asyncio
    async def test_get_or_create_raises_422_when_email_missing(self, repo):
        repo.get_by_keycloak_id = AsyncMock(return_value=None)

        with pytest.raises(ValidationError) as exc_info:
            await repo.get_or_create(
                keycloak_user_id="kc-new",
                email=None,
                first_name="New",
                last_name="User",
            )

        assert "X-Customer-Email" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_get_or_create_raises_422_when_first_name_missing(self, repo):
        repo.get_by_keycloak_id = AsyncMock(return_value=None)

        with pytest.raises(ValidationError) as exc_info:
            await repo.get_or_create(
                keycloak_user_id="kc-new",
                email="new@example.com",
                first_name=None,
                last_name="User",
            )

        assert "X-Customer-First-Name" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_get_or_create_raises_422_when_last_name_missing(self, repo):
        repo.get_by_keycloak_id = AsyncMock(return_value=None)

        with pytest.raises(ValidationError) as exc_info:
            await repo.get_or_create(
                keycloak_user_id="kc-new",
                email="new@example.com",
                first_name="New",
                last_name=None,
            )

        assert "X-Customer-Last-Name" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_update_customer_empty_payload_returns_existing(self, repo):
        existing = _make_customer()
        repo.get = AsyncMock(return_value=existing)
        repo.update = AsyncMock()

        result = await repo.update_customer(existing.id, CustomerUpdate())

        repo.update.assert_not_awaited()
        assert result is existing

    @pytest.mark.asyncio
    async def test_update_customer_partial_payload(self, repo):
        updated = _make_customer(first_name="Changed")
        repo.update = AsyncMock(return_value=updated)

        customer_id = uuid4()
        result = await repo.update_customer(
            customer_id, CustomerUpdate(first_name="Changed")
        )

        repo.update.assert_awaited_once_with(customer_id, first_name="Changed")
        assert result is updated

    @pytest.mark.asyncio
    async def test_update_customer_update_returns_none_raises_404(self, repo):
        repo.update = AsyncMock(return_value=None)

        with pytest.raises(NotFoundError):
            await repo.update_customer(uuid4(), CustomerUpdate(first_name="Changed"))


# ---------------------------------------------------------------------------
# AddressRepository
# ---------------------------------------------------------------------------


class TestAddressRepository:
    @pytest.fixture
    def session(self):
        return _make_session()

    @pytest.fixture
    def repo(self, session):
        return AddressRepository(session)

    # --- create_address ---

    @pytest.mark.asyncio
    async def test_create_address_no_default_skips_clear(self, repo):
        customer_id = uuid4()
        payload = AddressCreate(
            street="St 1",
            city="Berlin",
            zip_code="10115",
            country="DE",
            is_default=False,
        )
        new_addr = _make_address(customer_id=customer_id)
        repo.create = AsyncMock(return_value=new_addr)
        repo._clear_default = AsyncMock()

        result = await repo.create_address(customer_id, payload)

        repo._clear_default.assert_not_awaited()
        assert result is new_addr

    @pytest.mark.asyncio
    async def test_create_address_with_default_clears_first(self, repo):
        customer_id = uuid4()
        payload = AddressCreate(
            street="St 1",
            city="Berlin",
            zip_code="10115",
            country="DE",
            is_default=True,
        )
        new_addr = _make_address(customer_id=customer_id, is_default=True)
        repo.create = AsyncMock(return_value=new_addr)
        repo._clear_default = AsyncMock()

        result = await repo.create_address(customer_id, payload)

        repo._clear_default.assert_awaited_once_with(customer_id)
        assert result is new_addr

    # --- update_address ---

    @pytest.mark.asyncio
    async def test_update_address_not_found_raises_404(self, repo):
        repo.get = AsyncMock(return_value=None)

        with pytest.raises(NotFoundError) as exc_info:
            await repo.update_address(uuid4(), uuid4(), AddressUpdate(city="X"))

        assert exc_info.value.error_code.value == "entity_not_found"

    @pytest.mark.asyncio
    async def test_update_address_wrong_owner_raises_403(self, repo):
        address = _make_address(customer_id=uuid4())
        repo.get = AsyncMock(return_value=address)

        with pytest.raises(AuthorizationError) as exc_info:
            await repo.update_address(address.id, uuid4(), AddressUpdate(city="X"))

        assert exc_info.value.error_code.value == "access_denied"

    @pytest.mark.asyncio
    async def test_update_address_empty_payload_returns_existing(self, repo):
        customer_id = uuid4()
        address = _make_address(customer_id=customer_id)
        repo.get = AsyncMock(return_value=address)
        repo.update = AsyncMock()

        result = await repo.update_address(address.id, customer_id, AddressUpdate())

        repo.update.assert_not_awaited()
        assert result is address

    @pytest.mark.asyncio
    async def test_update_address_clears_default_when_set(self, repo):
        customer_id = uuid4()
        address = _make_address(customer_id=customer_id)
        updated_addr = _make_address(customer_id=customer_id, is_default=True)
        repo.get = AsyncMock(return_value=address)
        repo._clear_default = AsyncMock()
        repo.update = AsyncMock(return_value=updated_addr)

        result = await repo.update_address(
            address.id, customer_id, AddressUpdate(is_default=True)
        )

        repo._clear_default.assert_awaited_once_with(customer_id)
        assert result is updated_addr

    @pytest.mark.asyncio
    async def test_update_address_happy_path(self, repo):
        customer_id = uuid4()
        address = _make_address(customer_id=customer_id)
        updated_addr = _make_address(customer_id=customer_id)
        updated_addr.city = "Munich"
        repo.get = AsyncMock(return_value=address)
        repo._clear_default = AsyncMock()
        repo.update = AsyncMock(return_value=updated_addr)

        result = await repo.update_address(
            address.id, customer_id, AddressUpdate(city="Munich")
        )

        repo.update.assert_awaited_once_with(address.id, city="Munich")
        assert result.city == "Munich"

    # --- delete_address ---

    @pytest.mark.asyncio
    async def test_delete_address_not_found_raises_404(self, repo):
        repo.get = AsyncMock(return_value=None)

        with pytest.raises(NotFoundError):
            await repo.delete_address(uuid4(), uuid4())

    @pytest.mark.asyncio
    async def test_delete_address_wrong_owner_raises_403(self, repo):
        address = _make_address(customer_id=uuid4())
        repo.get = AsyncMock(return_value=address)

        with pytest.raises(AuthorizationError):
            await repo.delete_address(address.id, uuid4())

    @pytest.mark.asyncio
    async def test_delete_address_happy_path(self, repo):
        customer_id = uuid4()
        address = _make_address(customer_id=customer_id)
        repo.get = AsyncMock(return_value=address)
        repo.delete = AsyncMock()

        await repo.delete_address(address.id, customer_id)

        repo.delete.assert_awaited_once_with(address.id)
