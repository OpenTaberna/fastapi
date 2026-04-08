"""
Returns Pydantic Schemas — Phase 4.4

API-level input/output validation for the returns service.

Customer endpoints:
    POST /orders/{id}/returns — CreateReturnRequest → ReturnResponse

Admin endpoints:
    PATCH /admin/returns/{id} — AdminUpdateReturnRequest → ReturnResponse
"""

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ============================================================================
# Enums
# ============================================================================


class ReturnStatus(str, Enum):
    """
    Return request lifecycle states.

    Valid transitions (enforced by application layer):
        REQUESTED → APPROVED  (admin approves)
        REQUESTED → REJECTED  (admin rejects)
        APPROVED  → COMPLETED (physical return processed)
    """

    REQUESTED = "requested"
    APPROVED = "approved"
    REJECTED = "rejected"
    COMPLETED = "completed"


# ============================================================================
# Response schema
# ============================================================================


class ReturnResponse(BaseModel):
    """
    Return request response schema — used by both customer and admin endpoints.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Internal return UUID")
    order_id: UUID = Field(..., description="UUID of the order being returned")
    customer_id: UUID = Field(
        ..., description="UUID of the customer who filed the return"
    )
    status: ReturnStatus = Field(..., description="Current RMA status")
    reason: str = Field(..., description="Customer-provided return reason")
    admin_note: str | None = Field(default=None, description="Admin review note")
    created_at: datetime = Field(..., description="Record creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")


# ============================================================================
# Request (input) schemas
# ============================================================================


class CreateReturnRequest(BaseModel):
    """
    Request body for a customer filing a new return request.

    ``reason`` is required so admin staff always know why the item is coming
    back — avoids back-and-forth communication before the parcel arrives.
    """

    reason: str = Field(
        ...,
        min_length=10,
        max_length=1000,
        description="Reason for the return (min 10 characters)",
    )


class AdminUpdateReturnRequest(BaseModel):
    """
    Request body for an admin updating a return request.

    ``status`` is required — admins must explicitly approve, reject, or
    complete the RMA.  ``admin_note`` is optional but recommended.
    """

    status: ReturnStatus = Field(..., description="New status for the return request")
    admin_note: str | None = Field(
        default=None,
        max_length=2000,
        description="Optional admin note written during review",
    )
