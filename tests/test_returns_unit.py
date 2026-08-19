"""
Unit tests for Phase 4.4 — Returns (RMA) service.

No network, no database.

Covers:
    - ReturnStatus enum
    - CreateReturnRequest / AdminUpdateReturnRequest validation
    - ReturnResponse ORM round-trip
    - ReturnRepository.get_by_order_id
    - _assert_valid_transition   — admin status state machine
    - _assert_order_returnable   — which order states accept a return
    - _assert_order_owned_by_customer
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.services.orders.models.orders_models import OrderStatus
from app.services.returns.models.returns_models import (
    AdminUpdateReturnRequest,
    CreateReturnRequest,
    ReturnResponse,
    ReturnStatus,
)
from app.services.returns.routers.admin_returns_router import _assert_valid_transition
from app.services.returns.routers.returns_router import (
    _assert_order_owned_by_customer,
    _assert_order_returnable,
)
from app.services.returns.services.returns_db_service import (
    ReturnRepository,
    get_return_repository,
)
from app.shared.exceptions.errors import AuthorizationError, BusinessRuleError


def _make_return(status: str = ReturnStatus.REQUESTED.value) -> MagicMock:
    """Return a mock that behaves like a ReturnDB row."""
    now = datetime.now(UTC)
    r = MagicMock()
    r.id = uuid4()
    r.order_id = uuid4()
    r.customer_id = uuid4()
    r.status = status
    r.reason = "Item arrived damaged in transit"
    r.admin_note = None
    r.created_at = now
    r.updated_at = now
    return r


def _make_order(status: str, customer_id=None) -> MagicMock:
    o = MagicMock()
    o.id = uuid4()
    o.customer_id = customer_id or uuid4()
    o.status = status
    o.deleted_at = None
    return o


# ---------------------------------------------------------------------------
# ReturnStatus
# ---------------------------------------------------------------------------


class TestReturnStatus:
    def test_requested_value(self):
        assert ReturnStatus.REQUESTED == "requested"

    def test_approved_value(self):
        assert ReturnStatus.APPROVED == "approved"

    def test_rejected_value(self):
        assert ReturnStatus.REJECTED == "rejected"

    def test_completed_value(self):
        assert ReturnStatus.COMPLETED == "completed"

    def test_all_four_members_exist(self):
        assert len(ReturnStatus) == 4


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class TestCreateReturnRequest:
    def test_accepts_a_valid_reason(self):
        req = CreateReturnRequest(reason="Item arrived damaged")
        assert req.reason == "Item arrived damaged"

    def test_rejects_reason_shorter_than_ten_chars(self):
        # A one-word reason gives admin staff nothing to act on.
        with pytest.raises(PydanticValidationError):
            CreateReturnRequest(reason="broken")

    def test_rejects_missing_reason(self):
        with pytest.raises(PydanticValidationError):
            CreateReturnRequest()

    def test_rejects_reason_over_1000_chars(self):
        with pytest.raises(PydanticValidationError):
            CreateReturnRequest(reason="x" * 1001)

    def test_accepts_reason_at_exactly_ten_chars(self):
        assert CreateReturnRequest(reason="x" * 10).reason == "x" * 10


class TestAdminUpdateReturnRequest:
    def test_status_is_required(self):
        with pytest.raises(PydanticValidationError):
            AdminUpdateReturnRequest(admin_note="looks fine")

    def test_admin_note_is_optional(self):
        req = AdminUpdateReturnRequest(status=ReturnStatus.APPROVED)
        assert req.admin_note is None

    def test_rejects_unknown_status(self):
        with pytest.raises(PydanticValidationError):
            AdminUpdateReturnRequest(status="banana")

    def test_rejects_admin_note_over_2000_chars(self):
        with pytest.raises(PydanticValidationError):
            AdminUpdateReturnRequest(
                status=ReturnStatus.APPROVED, admin_note="x" * 2001
            )


class TestReturnResponse:
    def test_validates_from_orm_row(self):
        row = _make_return()
        resp = ReturnResponse.model_validate(row)
        assert resp.id == row.id
        assert resp.status == ReturnStatus.REQUESTED

    def test_admin_note_may_be_null(self):
        row = _make_return()
        row.admin_note = None
        assert ReturnResponse.model_validate(row).admin_note is None


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------


class TestReturnRepository:
    async def test_get_by_order_id_returns_the_row(self):
        session = AsyncMock()
        existing = _make_return()
        result = MagicMock()
        result.scalar_one_or_none = MagicMock(return_value=existing)
        session.execute = AsyncMock(return_value=result)

        repo = ReturnRepository(session)
        assert await repo.get_by_order_id(existing.order_id) is existing

    async def test_get_by_order_id_returns_none_when_absent(self):
        session = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none = MagicMock(return_value=None)
        session.execute = AsyncMock(return_value=result)

        repo = ReturnRepository(session)
        assert await repo.get_by_order_id(uuid4()) is None

    def test_factory_returns_repository_bound_to_session(self):
        session = AsyncMock()
        repo = get_return_repository(session)
        assert isinstance(repo, ReturnRepository)
        assert repo.session is session


# ---------------------------------------------------------------------------
# Admin status state machine
# ---------------------------------------------------------------------------


class TestAssertValidTransition:
    def test_requested_to_approved_is_allowed(self):
        _assert_valid_transition("requested", "approved", uuid4())

    def test_requested_to_rejected_is_allowed(self):
        _assert_valid_transition("requested", "rejected", uuid4())

    def test_approved_to_completed_is_allowed(self):
        _assert_valid_transition("approved", "completed", uuid4())

    def test_requested_cannot_jump_straight_to_completed(self):
        with pytest.raises(BusinessRuleError):
            _assert_valid_transition("requested", "completed", uuid4())

    def test_rejected_is_terminal(self):
        with pytest.raises(BusinessRuleError):
            _assert_valid_transition("rejected", "approved", uuid4())

    def test_completed_is_terminal(self):
        with pytest.raises(BusinessRuleError):
            _assert_valid_transition("completed", "requested", uuid4())

    def test_approved_cannot_go_back_to_requested(self):
        with pytest.raises(BusinessRuleError):
            _assert_valid_transition("approved", "requested", uuid4())

    def test_error_names_both_states(self):
        with pytest.raises(BusinessRuleError) as exc:
            _assert_valid_transition("completed", "approved", uuid4())
        assert "completed" in exc.value.message and "approved" in exc.value.message


# ---------------------------------------------------------------------------
# Customer-side guards
# ---------------------------------------------------------------------------


class TestAssertOrderReturnable:
    def test_shipped_order_is_returnable(self):
        _assert_order_returnable(_make_order(OrderStatus.SHIPPED.value), uuid4())

    def test_refunded_order_is_returnable(self):
        # A refunded order may still need the goods sent back.
        _assert_order_returnable(_make_order(OrderStatus.REFUNDED.value), uuid4())

    def test_paid_order_is_not_returnable(self):
        # Nothing has been shipped yet — cancel, do not return.
        with pytest.raises(BusinessRuleError):
            _assert_order_returnable(_make_order(OrderStatus.PAID.value), uuid4())

    def test_draft_order_is_not_returnable(self):
        with pytest.raises(BusinessRuleError):
            _assert_order_returnable(_make_order(OrderStatus.DRAFT.value), uuid4())

    def test_cancelled_order_is_not_returnable(self):
        with pytest.raises(BusinessRuleError):
            _assert_order_returnable(_make_order(OrderStatus.CANCELLED.value), uuid4())


class TestAssertOrderOwnedByCustomer:
    def test_owner_passes(self):
        cid = uuid4()
        _assert_order_owned_by_customer(_make_order("shipped", cid), cid, uuid4())

    def test_non_owner_is_denied(self):
        order = _make_order("shipped", uuid4())
        with pytest.raises(AuthorizationError):
            _assert_order_owned_by_customer(order, uuid4(), uuid4())
