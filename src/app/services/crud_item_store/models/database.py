"""
Item Store Database Models

SQLAlchemy ORM models for the item-store service.
These models map to PostgreSQL tables and use JSONB for nested structures.
"""

from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.database.base import Base, TimestampMixin


class ItemDB(Base, TimestampMixin):
    """
    Item database model.

    Stores item information with nested JSON structures for complex data.
    Inherits created_at and updated_at from TimestampMixin.

    Table Structure:
        - Core fields (uuid, sku, name, etc.) as columns
        - Complex nested structures (price, media, shipping, etc.) as JSONB
        - JSONB allows efficient querying and indexing of nested data
    """

    __tablename__ = "items"

    # Primary key
    uuid: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        doc="Unique item identifier",
    )

    # Core fields
    sku: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
        doc="Stock Keeping Unit (unique identifier)",
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="draft",
        index=True,
        doc="Item status: draft, active, archived",
    )

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        doc="Item display name",
    )

    slug: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
        doc="URL-friendly identifier",
    )

    short_description: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        doc="Brief item description",
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Full HTML/Markdown description",
    )

    brand: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
        doc="Brand name",
    )

    # JSONB fields for nested structures (efficiently queryable in PostgreSQL)
    categories: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        doc="List of category UUIDs (JSONB for efficient querying)",
    )

    price: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        doc="Price information (amount, currency, tax, etc.)",
    )

    media: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        doc="Media assets (main_image, gallery)",
    )

    inventory: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        doc="Inventory data (stock_quantity, stock_status, allow_backorder)",
    )

    shipping: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        doc="Shipping data (weight, dimensions, shipping_class)",
    )

    attributes: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        doc="Custom attributes (color, material, etc.)",
    )

    identifiers: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        doc="Product identification codes (barcode, MPN, country)",
    )

    custom: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        doc="Custom plugin data for extensibility",
    )

    system: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        doc="System metadata (log references, etc.)",
    )

    def __repr__(self) -> str:
        """String representation of Item."""
        return f"ItemDB(uuid={self.uuid}, sku={self.sku!r}, name={self.name!r}, status={self.status!r})"

    # Indexes for common query patterns
    __table_args__ = (
        # Add GIN index for JSONB fields to enable efficient querying
        # Example: WHERE price->>'currency' = 'EUR'
        # These would be added in migrations:
        # CREATE INDEX idx_items_price ON items USING GIN (price);
        # CREATE INDEX idx_items_categories ON items USING GIN (categories);
        # CREATE INDEX idx_items_attributes ON items USING GIN (attributes);
    )
