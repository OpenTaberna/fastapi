"""
Item Store Pydantic Models

This module defines all Pydantic models for the item-store service.
"""

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ============================================================================
# Enums
# ============================================================================


class ItemStatus(str, Enum):
    """Item lifecycle status."""

    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class StockStatus(str, Enum):
    """Inventory stock status."""

    IN_STOCK = "in_stock"
    OUT_OF_STOCK = "out_of_stock"
    PREORDER = "preorder"
    BACKORDER = "backorder"


class TaxClass(str, Enum):
    """Tax classification."""

    STANDARD = "standard"
    REDUCED = "reduced"
    NONE = "none"


class ShippingClass(str, Enum):
    """Shipping classification."""

    STANDARD = "standard"
    BULKY = "bulky"
    LETTER = "letter"


class WeightUnit(str, Enum):
    """Weight measurement units."""

    KG = "kg"
    LB = "lb"
    G = "g"


class DimensionUnit(str, Enum):
    """Dimension measurement units."""

    CM = "cm"
    M = "m"
    IN = "in"
    FT = "ft"


# ============================================================================
# Nested Models
# ============================================================================


class PriceModel(BaseModel):
    """Price information for an item."""

    amount: int = Field(
        ..., description="Price in smallest currency unit (e.g., cents)", ge=0
    )
    currency: str = Field(
        ..., min_length=3, max_length=3, description="ISO 4217 currency code"
    )
    includes_tax: bool = Field(default=True, description="Whether price includes tax")
    original_amount: int | None = Field(
        default=None, description="Original price before discount (in cents)", ge=0
    )
    tax_class: TaxClass = Field(
        default=TaxClass.STANDARD, description="Tax classification"
    )

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v: str) -> str:
        """Ensure currency is uppercase."""
        return v.upper()


class MediaModel(BaseModel):
    """Media assets for an item."""

    main_image: str | None = Field(default=None, description="Main product image URL")
    gallery: list[str] = Field(
        default_factory=list, description="Additional product images"
    )


class WeightModel(BaseModel):
    """Weight specification."""

    value: float = Field(..., description="Weight value", gt=0)
    unit: WeightUnit = Field(default=WeightUnit.KG, description="Weight unit")


class DimensionsModel(BaseModel):
    """Physical dimensions specification."""

    width: float = Field(..., description="Width", gt=0)
    height: float = Field(..., description="Height", gt=0)
    length: float = Field(..., description="Length/Depth", gt=0)
    unit: DimensionUnit = Field(default=DimensionUnit.CM, description="Dimension unit")


class ShippingModel(BaseModel):
    """Shipping information for an item."""

    is_physical: bool = Field(
        default=True, description="Whether item requires physical shipping"
    )
    weight: WeightModel | None = Field(default=None, description="Item weight")
    dimensions: DimensionsModel | None = Field(
        default=None, description="Item dimensions"
    )
    shipping_class: ShippingClass = Field(
        default=ShippingClass.STANDARD, description="Shipping classification"
    )


class InventoryModel(BaseModel):
    """Inventory tracking information."""

    stock_quantity: int = Field(default=0, description="Available stock quantity", ge=0)
    stock_status: StockStatus = Field(
        default=StockStatus.IN_STOCK, description="Stock availability status"
    )
    allow_backorder: bool = Field(
        default=False, description="Allow ordering when out of stock"
    )


class IdentifiersModel(BaseModel):
    """Product identification codes."""

    barcode: str | None = Field(
        default=None, description="Product barcode (EAN, UPC, etc.)"
    )
    manufacturer_part_number: str | None = Field(
        default=None, description="Manufacturer's part number"
    )
    country_of_origin: str | None = Field(
        default=None,
        min_length=2,
        max_length=2,
        description="ISO 3166-1 alpha-2 country code",
    )

    @field_validator("country_of_origin")
    @classmethod
    def validate_country_code(cls, v: str | None) -> str | None:
        """Ensure country code is uppercase."""
        return v.upper() if v else None


class SystemModel(BaseModel):
    """System-level metadata."""

    log_table: str | None = Field(
        default=None, description="Reference to conversation log in different table"
    )


# ============================================================================
# Main Item Models
# ============================================================================


class ItemBase(BaseModel):
    """Base item model with common fields."""

    sku: str = Field(
        ..., min_length=1, max_length=100, description="Stock Keeping Unit"
    )
    status: ItemStatus = Field(
        default=ItemStatus.DRAFT, description="Item lifecycle status"
    )
    name: str = Field(
        ..., min_length=1, max_length=255, description="Item display name"
    )
    slug: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="URL-friendly identifier (e.g., red-wooden-chair)",
    )
    short_description: str | None = Field(
        default=None, max_length=500, description="Brief item description"
    )
    description: str | None = Field(
        default=None, description="Full HTML/Markdown description"
    )
    categories: list[UUID] = Field(
        default_factory=list, description="Category UUID references"
    )
    brand: str | None = Field(default=None, max_length=100, description="Brand name")
    price: PriceModel = Field(..., description="Pricing information")
    media: MediaModel = Field(default_factory=MediaModel, description="Media assets")
    inventory: InventoryModel = Field(
        default_factory=InventoryModel, description="Inventory data"
    )
    shipping: ShippingModel = Field(
        default_factory=ShippingModel, description="Shipping data"
    )
    attributes: dict[str, Any] = Field(
        default_factory=dict, description="Custom attributes (e.g., color, material)"
    )
    identifiers: IdentifiersModel = Field(
        default_factory=IdentifiersModel, description="Product identification codes"
    )
    custom: dict[str, Any] = Field(
        default_factory=dict, description="Custom plugin data (extensibility)"
    )
    system: SystemModel = Field(
        default_factory=SystemModel, description="System metadata"
    )

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str) -> str:
        """Ensure slug is lowercase and URL-friendly."""
        return v.lower().strip()


class ItemCreate(ItemBase):
    """Schema for creating a new item."""

    pass


class ItemUpdate(BaseModel):
    """Schema for updating an existing item (all fields optional)."""

    sku: str | None = Field(default=None, min_length=1, max_length=100)
    status: ItemStatus | None = None
    name: str | None = Field(default=None, min_length=1, max_length=255)
    slug: str | None = Field(default=None, min_length=1, max_length=255)
    short_description: str | None = Field(default=None, max_length=500)
    description: str | None = None
    categories: list[UUID] | None = None
    brand: str | None = Field(default=None, max_length=100)
    price: PriceModel | None = None
    media: MediaModel | None = None
    inventory: InventoryModel | None = None
    shipping: ShippingModel | None = None
    attributes: dict[str, Any] | None = None
    identifiers: IdentifiersModel | None = None
    custom: dict[str, Any] | None = None
    system: SystemModel | None = None

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str | None) -> str | None:
        """Ensure slug is lowercase and URL-friendly."""
        return v.lower().strip() if v else None
