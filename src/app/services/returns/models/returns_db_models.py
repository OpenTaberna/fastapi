"""
Returns Database Models — Phase 4.4

SQLAlchemy ORM models for customer return requests (RMA — Return Merchandise
Authorization).

Design decisions:
- ReturnDB holds one return per order.  A second return request on the same
  order is rejected at the service layer (UNIQUE constraint on order_id).
- Status transitions are enforced by the application layer:
    REQUESTED → APPROVED | REJECTED → COMPLETED
- admin_note is optional and only written by admin endpoints.
- order_id is a hard FK to orders.id (RESTRICT on delete so we never lose
  a return record when an order is soft-deleted).
"""

from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.database.base import Base, TimestampMixin


class ReturnDB(Base, TimestampMixin):
    """
    Return request (RMA) database model.

    Tracks the lifecycle of a customer's return request from initial submission
    through admin review to completion.

    Status transitions:
        REQUESTED → APPROVED  (admin approves)
        REQUESTED → REJECTED  (admin rejects)
        APPROVED  → COMPLETED (physical return received and processed)

    Columns:
        id:          UUID primary key.
        order_id:    FK → orders.id (UNIQUE — one active return per order).
        customer_id: FK → customers.id (denormalised for fast customer queries).
        status:      Current RMA status (see ReturnStatus in returns_models.py).
        reason:      Customer-supplied explanation for the return.
        admin_note:  Optional note added by admin during review.
        created_at:  Inherited from TimestampMixin.
        updated_at:  Inherited from TimestampMixin.
    """

    __tablename__ = "returns"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        doc="Internal unique identifier",
    )

    order_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("orders.id", ondelete="RESTRICT"),
        nullable=False,
        doc="FK to the order being returned — one return per order",
    )

    customer_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        doc="FK to the customer who filed the return",
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="requested",
        server_default=text("'requested'"),
        index=True,
        doc="RMA status: requested | approved | rejected | completed",
    )

    reason: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="Customer-provided reason for the return",
    )

    admin_note: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Optional note written by admin during review",
    )

    __table_args__ = (UniqueConstraint("order_id", name="uq_returns_order_id"),)

    def __repr__(self) -> str:
        return (
            f"ReturnDB(id={self.id}, order_id={self.order_id}, status={self.status!r})"
        )
