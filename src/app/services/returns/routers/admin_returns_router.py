"""
Admin Returns Router — Phase 4.4

FastAPI router for admin return management:

    PATCH /admin/returns/{id} — Admin approves / rejects / completes an RMA

Business rules:
- Valid admin transitions:
    REQUESTED → APPROVED
    REQUESTED → REJECTED
    APPROVED  → COMPLETED
- Attempting any other transition raises a 400 BusinessRuleError.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.admin.dependencies import require_admin
from app.shared.database.session import get_session_dependency
from app.shared.exceptions import entity_not_found, operation_not_allowed
from app.shared.logger import get_logger

from ..models import AdminUpdateReturnRequest, ReturnResponse, ReturnStatus
from ..responses import ADMIN_UPDATE_RETURN_RESPONSES
from ..services import get_return_repository

logger = get_logger(__name__)

router = APIRouter()

# Valid admin-driven status transitions: {current: allowed_targets}
_ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    ReturnStatus.REQUESTED.value: frozenset(
        {ReturnStatus.APPROVED.value, ReturnStatus.REJECTED.value}
    ),
    ReturnStatus.APPROVED.value: frozenset({ReturnStatus.COMPLETED.value}),
}


# ---------------------------------------------------------------------------
# PATCH /admin/returns/{id} — Update return status
# ---------------------------------------------------------------------------


@router.patch(
    "/{return_id}",
    response_model=ReturnResponse,
    status_code=status.HTTP_200_OK,
    summary="Update return request (admin)",
    description=(
        "Approve, reject, or mark a return request as completed. "
        "Valid transitions:\n\n"
        "- ``REQUESTED → APPROVED``\n"
        "- ``REQUESTED → REJECTED``\n"
        "- ``APPROVED → COMPLETED``\n\n"
        "An optional ``admin_note`` is stored on the record for audit purposes."
    ),
    dependencies=[Depends(require_admin)],
    responses=ADMIN_UPDATE_RETURN_RESPONSES,
    tags=["Admin"],
)
async def update_return(
    return_id: UUID,
    payload: AdminUpdateReturnRequest,
    session: AsyncSession = Depends(get_session_dependency),
) -> ReturnResponse:
    """
    Update the status (and optionally a note) on a return request.

    Steps:
    1. Load the ReturnDB row — 404 if missing.
    2. Validate the status transition against ``_ALLOWED_TRANSITIONS``.
    3. Persist the new status and optional admin_note.

    Args:
        return_id: UUID of the return request (path parameter).
        payload:   AdminUpdateReturnRequest with new status and optional note.
        session:   Database session.

    Returns:
        Updated ReturnResponse.

    Raises:
        NotFoundError (404):     If no return exists with the given ID.
        BusinessRuleError (400): If the requested status transition is not allowed.
    """
    return_repo = get_return_repository(session)

    return_record = await return_repo.get(return_id)
    if return_record is None:
        raise entity_not_found("Return", return_id)

    _assert_valid_transition(return_record.status, payload.status.value, return_id)

    update_fields: dict = {"status": payload.status.value}
    if payload.admin_note is not None:
        update_fields["admin_note"] = payload.admin_note

    updated = await return_repo.update(return_id, **update_fields)
    # See issue #26 — the session dependency commits only after the response.
    await session.commit()

    logger.info(
        "Admin updated return status",
        extra={
            "return_id": str(return_id),
            "previous_status": return_record.status,
            "new_status": payload.status.value,
            "has_note": bool(payload.admin_note),
        },
    )
    return ReturnResponse.model_validate(updated)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _assert_valid_transition(
    current: str,
    target: str,
    return_id: UUID,
) -> None:
    """
    Raise BusinessRuleError if the requested status transition is not allowed.

    Args:
        current:   Current ReturnDB.status value.
        target:    Requested new status value.
        return_id: UUID used in the error context.

    Raises:
        BusinessRuleError (400): If the transition is not in ``_ALLOWED_TRANSITIONS``.
    """
    allowed = _ALLOWED_TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        raise operation_not_allowed(
            operation="update_return_status",
            reason=(
                f"Return '{return_id}' cannot transition from '{current}' to '{target}'"
            ),
        )
