"""
Inventory Database Models

SQLAlchemy ORM models for stock levels and reservations.

Design decisions:
- inventory_items.sku is a soft reference to items.sku (no FK constraint).
  This keeps the inventory service decoupled from the item service.
  Referential integrity is enforced at the application layer.
- stock_reservations.order_id is a soft reference to orders.id for the
  same reason: avoids circular FK dependencies at the DB level.
- DB constraints enforce on_hand >= 0, reserved >= 0, on_hand >= reserved.
  These are the last line of defence against overselling.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, DateTime, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.database.base import Base, TimestampMixin


class InventoryItemDB(Base, TimestampMixin):
    """
    Inventory item database model.

    Tracks available (on_hand) and reserved stock for a single SKU.
    'reserved' counts units currently held by active StockReservations.
    'on_hand' is the physical quantity in the warehouse.

    Invariant (enforced by DB constraint): on_hand >= reserved >= 0

    Columns:
        id:         UUID primary key.
        sku:        SKU string — soft reference to items.sku.
        on_hand:    Physical units in the warehouse.
        reserved:   Units locked by active reservations (subset of on_hand).
        created_at: Inherited from TimestampMixin.
        updated_at: Inherited from TimestampMixin.
    """

    __tablename__ = "inventory_items"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        doc="Internal unique identifier",
    )

    sku: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
        doc="Stock Keeping Unit — matches items.sku",
    )

    on_hand: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
        doc="Physical stock count in the warehouse",
    )

    reserved: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
        doc="Units locked by active reservations",
    )

    __table_args__ = (
        CheckConstraint("on_hand >= 0", name="ck_inventory_items_on_hand_non_negative"),
        CheckConstraint("reserved >= 0", name="ck_inventory_items_reserved_non_negative"),
        CheckConstraint("on_hand >= reserved", name="ck_inventory_items_on_hand_gte_reserved"),
    )

    def __repr__(self) -> str:
        return (
            f"InventoryItemDB(id={self.id}, sku={self.sku!r}, "
            f"on_hand={self.on_hand}, reserved={self.reserved})"
        )


class StockReservationDB(Base, TimestampMixin):
    """
    Stock reservation database model.

    Created when a customer starts checkout. Holds stock until payment
    is confirmed (COMMITTED) or the reservation expires (EXPIRED/RELEASED).

    Lifecycle:
        ACTIVE → COMMITTED  (payment succeeded, inventory committed)
        ACTIVE → RELEASED   (payment failed or cart abandoned)
        ACTIVE → EXPIRED    (TTL exceeded, cleaned up by background job)

    Columns:
        id:                 UUID primary key.
        inventory_item_id:  FK → inventory_items.id.
        order_id:           Soft reference to orders.id (no DB FK).
        quantity:           Number of units reserved.
        expires_at:         When this reservation automatically expires.
        status:             Current lifecycle state (see ReservationStatus enum).
        created_at:         Inherited from TimestampMixin.
        updated_at:         Inherited from TimestampMixin.
    """

    __tablename__ = "stock_reservations"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        doc="Internal unique identifier",
    )

    inventory_item_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("inventory_items.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        doc="FK to the inventory item being reserved",
    )

    order_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
        index=True,
        doc="Soft reference to orders.id (no DB FK to avoid circular dependency)",
    )

    quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        doc="Number of units reserved",
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        doc="Timestamp after which this reservation is considered expired",
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="active",
        server_default=text("'active'"),
        index=True,
        doc="Reservation status: active | committed | expired | released",
    )

    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_stock_reservations_quantity_positive"),
    )

    def __repr__(self) -> str:
        return (
            f"StockReservationDB(id={self.id}, order_id={self.order_id}, "
            f"quantity={self.quantity}, status={self.status!r})"
        )
