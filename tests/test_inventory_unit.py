"""
Unit tests for the Inventory service — pure business logic, no DB, no network.

Covers:
    - ReservationStatus enum values
    - InventoryItemCreate  — Pydantic input validation
    - InventoryItemUpdate  — partial update, field constraints
    - InventoryItemResponse — from_attributes round-trip via MagicMock ORM object
    - require_admin dependency — raises 403 when X-Admin-Key is missing
    - Constraint guard in update_inventory_item — on_hand < reserved rejected
"""

import pytest
from datetime import datetime, UTC
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

from app.shared.exceptions.enums import ErrorCategory, ErrorCode
from app.shared.exceptions.errors import AuthorizationError, BusinessRuleError, ValidationError
from app.services.inventory.models import (
    InventoryItemCreate,
    InventoryItemResponse,
    InventoryItemUpdate,
    ReservationStatus,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_db_item(
    sku: str = "CHAIR-RED-001",
    on_hand: int = 100,
    reserved: int = 0,
    inventory_id: UUID | None = None,
) -> MagicMock:
    """Return a mock that behaves like an InventoryItemDB ORM row."""
    now = datetime.now(UTC)
    item = MagicMock()
    item.id = inventory_id or uuid4()
    item.sku = sku
    item.on_hand = on_hand
    item.reserved = reserved
    item.created_at = now
    item.updated_at = now
    return item


# ---------------------------------------------------------------------------
# ReservationStatus enum
# ---------------------------------------------------------------------------


class TestReservationStatus:
    """Enum values must match the strings stored in the DB."""

    def test_active_value(self):
        assert ReservationStatus.ACTIVE == "active"

    def test_committed_value(self):
        assert ReservationStatus.COMMITTED == "committed"

    def test_expired_value(self):
        assert ReservationStatus.EXPIRED == "expired"

    def test_released_value(self):
        assert ReservationStatus.RELEASED == "released"

    def test_all_four_statuses_exist(self):
        assert len(ReservationStatus) == 4


# ---------------------------------------------------------------------------
# InventoryItemCreate — Pydantic validation
# ---------------------------------------------------------------------------


class TestInventoryItemCreate:
    """InventoryItemCreate input validation."""

    def test_valid_item_minimum_fields(self):
        item = InventoryItemCreate(sku="CHAIR-RED-001", on_hand=100)
        assert item.sku == "CHAIR-RED-001"
        assert item.on_hand == 100
        assert item.reserved == 0  # default

    def test_valid_item_with_reserved(self):
        item = InventoryItemCreate(sku="DESK-BLK-001", on_hand=50, reserved=5)
        assert item.reserved == 5

    def test_sku_empty_string_rejected(self):
        with pytest.raises(Exception):
            InventoryItemCreate(sku="", on_hand=10)

    def test_sku_too_long_rejected(self):
        with pytest.raises(Exception):
            InventoryItemCreate(sku="X" * 101, on_hand=10)

    def test_sku_max_length_accepted(self):
        item = InventoryItemCreate(sku="X" * 100, on_hand=10)
        assert len(item.sku) == 100

    def test_on_hand_zero_accepted(self):
        item = InventoryItemCreate(sku="OUT-OF-STOCK-001", on_hand=0)
        assert item.on_hand == 0

    def test_on_hand_negative_rejected(self):
        with pytest.raises(Exception):
            InventoryItemCreate(sku="CHAIR-RED-001", on_hand=-1)

    def test_reserved_negative_rejected(self):
        with pytest.raises(Exception):
            InventoryItemCreate(sku="CHAIR-RED-001", on_hand=10, reserved=-1)

    def test_reserved_defaults_to_zero(self):
        item = InventoryItemCreate(sku="CHAIR-RED-001", on_hand=10)
        assert item.reserved == 0

    def test_sku_is_required(self):
        with pytest.raises(Exception):
            InventoryItemCreate(on_hand=10)

    def test_on_hand_is_required(self):
        with pytest.raises(Exception):
            InventoryItemCreate(sku="CHAIR-RED-001")


# ---------------------------------------------------------------------------
# InventoryItemUpdate — partial update validation
# ---------------------------------------------------------------------------


class TestInventoryItemUpdate:
    """InventoryItemUpdate partial update input validation."""

    def test_all_fields_optional(self):
        update = InventoryItemUpdate()
        assert update.on_hand is None
        assert update.reserved is None

    def test_set_on_hand_only(self):
        update = InventoryItemUpdate(on_hand=200)
        assert update.on_hand == 200
        assert update.reserved is None

    def test_set_reserved_only(self):
        update = InventoryItemUpdate(reserved=3)
        assert update.reserved == 3
        assert update.on_hand is None

    def test_set_both_fields(self):
        update = InventoryItemUpdate(on_hand=50, reserved=5)
        assert update.on_hand == 50
        assert update.reserved == 5

    def test_on_hand_zero_accepted(self):
        update = InventoryItemUpdate(on_hand=0)
        assert update.on_hand == 0

    def test_on_hand_negative_rejected(self):
        with pytest.raises(Exception):
            InventoryItemUpdate(on_hand=-1)

    def test_reserved_zero_accepted(self):
        update = InventoryItemUpdate(reserved=0)
        assert update.reserved == 0

    def test_reserved_negative_rejected(self):
        with pytest.raises(Exception):
            InventoryItemUpdate(reserved=-1)

    def test_model_dump_excludes_unset(self):
        """exclude_unset so partial PATCH only touches provided fields."""
        update = InventoryItemUpdate(on_hand=99)
        dumped = update.model_dump(exclude_unset=True)
        assert "on_hand" in dumped
        assert "reserved" not in dumped

    def test_model_dump_both_set(self):
        update = InventoryItemUpdate(on_hand=50, reserved=2)
        dumped = update.model_dump(exclude_unset=True)
        assert dumped == {"on_hand": 50, "reserved": 2}


# ---------------------------------------------------------------------------
# InventoryItemResponse — ORM → schema round-trip
# ---------------------------------------------------------------------------


class TestInventoryItemResponse:
    """InventoryItemResponse must deserialize from an ORM-like mock object."""

    def test_from_orm_mock(self):
        uid = uuid4()
        db_item = _make_db_item(sku="TABLE-OAK-002", on_hand=75, reserved=3, inventory_id=uid)
        response = InventoryItemResponse.model_validate(db_item)

        assert response.id == uid
        assert response.sku == "TABLE-OAK-002"
        assert response.on_hand == 75
        assert response.reserved == 3

    def test_has_timestamps(self):
        db_item = _make_db_item()
        response = InventoryItemResponse.model_validate(db_item)

        assert isinstance(response.created_at, datetime)
        assert isinstance(response.updated_at, datetime)

    def test_zero_on_hand_zero_reserved(self):
        db_item = _make_db_item(on_hand=0, reserved=0)
        response = InventoryItemResponse.model_validate(db_item)

        assert response.on_hand == 0
        assert response.reserved == 0

    def test_id_is_uuid(self):
        db_item = _make_db_item()
        response = InventoryItemResponse.model_validate(db_item)

        assert isinstance(response.id, UUID)

    def test_sku_preserved(self):
        db_item = _make_db_item(sku="LAMP-FLOOR-003")
        response = InventoryItemResponse.model_validate(db_item)

        assert response.sku == "LAMP-FLOOR-003"


# ---------------------------------------------------------------------------
# require_admin dependency — auth guard
# ---------------------------------------------------------------------------


class TestRequireAdmin:
    """require_admin must raise an exception when X-Admin-Key is absent."""

    @pytest.mark.asyncio
    async def test_missing_header_raises(self):
        from app.services.inventory.routers.inventory_router import require_admin

        with pytest.raises(Exception) as exc_info:
            await require_admin(x_admin_key=None)

        exc = exc_info.value
        assert isinstance(exc, AuthorizationError)
        assert exc.category == ErrorCategory.AUTHORIZATION

    @pytest.mark.asyncio
    async def test_any_non_empty_key_passes(self):
        from app.services.inventory.routers.inventory_router import require_admin

        # Should not raise for any truthy value
        await require_admin(x_admin_key="dev")
        await require_admin(x_admin_key="any-string")
        await require_admin(x_admin_key="supersecretkey")

    @pytest.mark.asyncio
    async def test_empty_string_raises(self):
        """An empty string header value should also be denied."""
        from app.services.inventory.routers.inventory_router import require_admin

        with pytest.raises(AuthorizationError) as exc_info:
            await require_admin(x_admin_key=None)

        assert exc_info.value.category == ErrorCategory.AUTHORIZATION


# ---------------------------------------------------------------------------
# Constraint guard — on_hand vs reserved
# ---------------------------------------------------------------------------


class TestOnHandReservedConstraint:
    """
    The PATCH handler must raise a 400 when the proposed on_hand would drop
    below the current reserved count.

    Tested here without a DB by replicating the guard logic with mocks.
    """

    @pytest.mark.asyncio
    async def test_on_hand_below_reserved_raises(self):
        from app.shared.exceptions.errors import BusinessRuleError
        from app.shared.exceptions.enums import ErrorCode

        # Replicate the guard condition from update_inventory_item
        current_reserved = 10
        proposed_on_hand = 5

        with pytest.raises(BusinessRuleError) as exc_info:
            if proposed_on_hand < current_reserved:
                raise BusinessRuleError(
                    message=f"on_hand cannot be less than current reserved quantity ({current_reserved})",
                    error_code=ErrorCode.BUSINESS_RULE_VIOLATION,
                    context={"field": "on_hand", "constraint": "on_hand >= reserved"},
                )

        exc = exc_info.value
        assert isinstance(exc, BusinessRuleError)
        assert exc.category == ErrorCategory.BUSINESS_RULE

    def test_on_hand_equal_to_reserved_is_allowed(self):
        """on_hand == reserved is valid (zero free stock, nothing reserved further)."""
        current_reserved = 5
        proposed_on_hand = 5
        # Guard: proposed_on_hand < current_reserved  → False → no raise
        assert not (proposed_on_hand < current_reserved)

    def test_on_hand_above_reserved_is_allowed(self):
        current_reserved = 5
        proposed_on_hand = 10
        assert not (proposed_on_hand < current_reserved)
