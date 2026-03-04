"""
Orders Database Models

SQLAlchemy ORM models for orders and order line items.

Design decisions:
- OrderItemDB.unit_price is a price SNAPSHOT taken at checkout time.
  It deliberately does NOT reference items.price — prices can change
  after an order is placed and the order must reflect what the customer paid.
- OrderDB.customer_id is a hard FK to customers.id (CASCADE on delete).
- OrderItemDB.order_id is a hard FK to orders.id (CASCADE on delete).
- Orders support soft deletion via SoftDeleteMixin (deleted_at field).
"""

from uuid import UUID, uuid4

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Integer, String, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.database.base import Base, SoftDeleteMixin, TimestampMixin


class OrderDB(Base, TimestampMixin, SoftDeleteMixin):
    """
    Order database model.

    Represents the lifecycle of a single customer purchase.

    Status transitions (enforced by application layer, not DB):
        DRAFT → PENDING_PAYMENT → PAID → READY_TO_SHIP → SHIPPED
        PENDING_PAYMENT / DRAFT → CANCELLED

    Columns:
        id:           UUID primary key.
        customer_id:  FK → customers.id.
        status:       Current order status (see OrderStatus enum).
        total_amount: Order total in smallest currency unit (e.g. cents).
        currency:     ISO 4217 currency code (e.g. 'EUR').
        deleted_at:   Soft delete timestamp — inherited from SoftDeleteMixin.
        created_at:   Inherited from TimestampMixin.
        updated_at:   Inherited from TimestampMixin.
    """

    __tablename__ = "orders"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        doc="Internal unique identifier",
    )

    customer_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="FK to the customer who placed this order",
    )

    status: Mapped[str] = mapped_column(
        String(25),
        nullable=False,
        default="draft",
        server_default=text("'draft'"),
        index=True,
        doc="Order status: draft | pending_payment | paid | ready_to_ship | shipped | cancelled",
    )

    total_amount: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        doc="Order total in smallest currency unit (e.g. cents)",
    )

    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        doc="ISO 4217 currency code (e.g. 'EUR')",
    )

    __table_args__ = (
        CheckConstraint("total_amount >= 0", name="ck_orders_total_amount_non_negative"),
    )

    def __repr__(self) -> str:
        return (
            f"OrderDB(id={self.id}, customer_id={self.customer_id}, "
            f"status={self.status!r}, total_amount={self.total_amount})"
        )


class OrderItemDB(Base, TimestampMixin):
    """
    Order item database model.

    Represents a single line item (SKU + quantity + snapshot price) within an order.

    Columns:
        id:         UUID primary key.
        order_id:   FK → orders.id.
        sku:        SKU string — price snapshot, NOT a FK to items.
        quantity:   Number of units ordered.
        unit_price: Price per unit at time of order (in smallest currency unit).
        created_at: Inherited from TimestampMixin.
        updated_at: Inherited from TimestampMixin.
    """

    __tablename__ = "order_items"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        doc="Internal unique identifier",
    )

    order_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="FK to the parent order",
    )

    sku: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        doc="SKU at time of order — price snapshot, not a live FK",
    )

    quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        doc="Number of units ordered",
    )

    unit_price: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        doc="Price per unit at checkout time (in smallest currency unit)",
    )

    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_order_items_quantity_positive"),
        CheckConstraint("unit_price >= 0", name="ck_order_items_unit_price_non_negative"),
    )

    def __repr__(self) -> str:
        return (
            f"OrderItemDB(id={self.id}, order_id={self.order_id}, "
            f"sku={self.sku!r}, quantity={self.quantity}, unit_price={self.unit_price})"
        )
