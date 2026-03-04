"""
Shipments Database Models

SQLAlchemy ORM model for shipment records.

Design decisions:
- One shipment per order (UNIQUE on order_id).
- tracking_number and label_url are nullable — they are populated once the
  carrier label is created (either manually in Phase 2 or via DHL in Phase 3).
- The CarrierAdapter interface (Phase 3) will write to this table via the
  ShipmentRepository — the DB model does not need to change between phases.
"""

from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.database.base import Base, TimestampMixin


class ShipmentDB(Base, TimestampMixin):
    """
    Shipment database model.

    Created when an admin marks an order as ready to ship.
    Stores carrier, tracking info and label reference.

    Columns:
        id:              UUID primary key.
        order_id:        FK → orders.id. UNIQUE (one shipment per order).
        carrier:         Carrier name (see Carrier enum, e.g. 'dhl' | 'manual').
        tracking_number: Carrier tracking number — NULL until label is created.
        label_url:       URL/path to label file in storage — NULL until created.
        label_format:    Label format: 'pdf' | 'zpl' | NULL.
        status:          Shipment status (see ShipmentStatus enum).
        created_at:      Inherited from TimestampMixin.
        updated_at:      Inherited from TimestampMixin.
    """

    __tablename__ = "shipments"

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
        doc="FK to the associated order — one shipment per order (indexed via UniqueConstraint)",
    )

    carrier: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        doc="Carrier identifier: 'manual' | 'dhl'",
    )

    tracking_number: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        doc="Carrier tracking number — populated after label creation",
    )

    label_url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="URL or storage path to the label file",
    )

    label_format: Mapped[str | None] = mapped_column(
        String(10),
        nullable=True,
        doc="Label file format: 'pdf' | 'zpl' | NULL",
    )

    status: Mapped[str] = mapped_column(
        String(25),
        nullable=False,
        default="pending",
        server_default=text("'pending'"),
        index=True,
        doc="Shipment status: pending | label_created | handed_over",
    )

    __table_args__ = (UniqueConstraint("order_id", name="uq_shipments_order_id"),)

    def __repr__(self) -> str:
        return (
            f"ShipmentDB(id={self.id}, order_id={self.order_id}, "
            f"carrier={self.carrier!r}, status={self.status!r})"
        )
