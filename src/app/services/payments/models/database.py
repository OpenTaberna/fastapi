"""
Payments Database Models

SQLAlchemy ORM model for payment records.

Design decisions:
- One payment per order (UNIQUE on order_id). A new payment record is created
  for a retry, but the old one is retained for audit purposes.
- provider_reference is UNIQUE to ensure a single PSP transaction maps to
  exactly one payment record — critical for idempotent webhook handling.
- order_id is a hard FK to orders.id.
"""

from uuid import UUID, uuid4

from sqlalchemy import BigInteger, ForeignKey, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.database.base import Base, TimestampMixin


class PaymentDB(Base, TimestampMixin):
    """
    Payment database model.

    Tracks the payment intent/session created with the PSP and its outcome.

    Columns:
        id:                 UUID primary key.
        order_id:           FK → orders.id. UNIQUE (one payment per order).
        provider:           PSP provider name (e.g. 'stripe').
        provider_reference: PSP-side ID (e.g. Stripe PaymentIntent ID). UNIQUE.
        amount:             Charged amount in smallest currency unit (e.g. cents).
        currency:           ISO 4217 currency code (e.g. 'EUR').
        status:             Payment status (see PaymentStatus enum).
        created_at:         Inherited from TimestampMixin.
        updated_at:         Inherited from TimestampMixin.
    """

    __tablename__ = "payments"

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
        doc="FK to the associated order — one payment per order (indexed via UniqueConstraint)",
    )

    provider: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        doc="PSP provider (e.g. 'stripe')",
    )

    provider_reference: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
        doc="PSP-side transaction ID (e.g. Stripe pi_xxx) — unique for idempotency",
    )

    amount: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        doc="Charged amount in smallest currency unit (e.g. cents)",
    )

    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        doc="ISO 4217 currency code (e.g. 'EUR')",
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        server_default=text("'pending'"),
        index=True,
        doc="Payment status: pending | succeeded | failed | refunded",
    )

    __table_args__ = (
        UniqueConstraint("order_id", name="uq_payments_order_id"),
    )

    def __repr__(self) -> str:
        return (
            f"PaymentDB(id={self.id}, order_id={self.order_id}, "
            f"provider={self.provider!r}, status={self.status!r})"
        )
