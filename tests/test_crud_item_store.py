"""
Tests for CRUD Item Store Service

Following the project's testing patterns from testing.md.
Tests cover Pydantic models, validation, enums, and business rules.
"""

import pytest
from uuid import UUID, uuid4
from datetime import datetime

from app.services.crud_item_store.models import (
    DimensionUnit,
    DimensionsModel,
    IdentifiersModel,
    InventoryModel,
    ItemCreate,
    ItemStatus,
    ItemUpdate,
    MediaModel,
    PriceModel,
    ShippingClass,
    ShippingModel,
    StockStatus,
    SystemModel,
    TaxClass,
    WeightModel,
    WeightUnit,
)
from app.services.crud_item_store.responses import ItemResponse


class TestPriceModel:
    """Test PriceModel validation and transformations."""

    def test_create_price_with_required_fields(self):
        """Test creating price with minimum required fields."""
        price = PriceModel(amount=9999, currency="EUR")

        assert price.amount == 9999
        assert price.currency == "EUR"
        assert price.includes_tax is True  # Default
        assert price.tax_class == TaxClass.STANDARD  # Default

    def test_currency_uppercase_validation(self):
        """Test that currency is converted to uppercase."""
        price = PriceModel(amount=9999, currency="eur")

        assert price.currency == "EUR"

    def test_currency_mixed_case(self):
        """Test currency normalization with mixed case."""
        price = PriceModel(amount=9999, currency="uSd")

        assert price.currency == "USD"

    def test_negative_amount_rejected(self):
        """Test that negative amounts are rejected."""
        with pytest.raises(ValueError):
            PriceModel(amount=-100, currency="EUR")

    def test_zero_amount_allowed(self):
        """Test that zero amount is allowed."""
        price = PriceModel(amount=0, currency="EUR")

        assert price.amount == 0

    def test_price_with_discount(self):
        """Test price with original amount for discounts."""
        price = PriceModel(
            amount=9999, currency="EUR", original_amount=12999, includes_tax=True
        )

        assert price.amount == 9999
        assert price.original_amount == 12999

    def test_original_amount_greater_than_amount(self):
        """Test discount scenario where original > current."""
        price = PriceModel(amount=8000, currency="EUR", original_amount=10000)

        # Original amount should be higher (discount applied)
        assert price.original_amount > price.amount

    def test_tax_class_options(self):
        """Test different tax class values."""
        standard = PriceModel(amount=1000, currency="EUR", tax_class=TaxClass.STANDARD)
        reduced = PriceModel(amount=1000, currency="EUR", tax_class=TaxClass.REDUCED)
        none_tax = PriceModel(amount=1000, currency="EUR", tax_class=TaxClass.NONE)

        assert standard.tax_class == TaxClass.STANDARD
        assert reduced.tax_class == TaxClass.REDUCED
        assert none_tax.tax_class == TaxClass.NONE


class TestMediaModel:
    """Test MediaModel validation."""

    def test_empty_media(self):
        """Test creating empty media model."""
        media = MediaModel()

        assert media.main_image is None
        assert media.gallery == []

    def test_media_with_main_image(self):
        """Test media with main image only."""
        media = MediaModel(main_image="https://example.com/image.jpg")

        assert media.main_image == "https://example.com/image.jpg"
        assert media.gallery == []

    def test_media_with_gallery(self):
        """Test media with gallery images."""
        media = MediaModel(
            main_image="https://example.com/main.jpg",
            gallery=[
                "https://example.com/side.jpg",
                "https://example.com/back.jpg",
            ],
        )

        assert len(media.gallery) == 2
        assert "https://example.com/side.jpg" in media.gallery


class TestWeightModel:
    """Test WeightModel validation."""

    def test_weight_with_defaults(self):
        """Test weight with default unit."""
        weight = WeightModel(value=7.5)

        assert weight.value == 7.5
        assert weight.unit == WeightUnit.KG

    def test_weight_with_custom_unit(self):
        """Test weight with custom unit."""
        weight = WeightModel(value=16.5, unit=WeightUnit.LB)

        assert weight.value == 16.5
        assert weight.unit == WeightUnit.LB

    def test_zero_weight_rejected(self):
        """Test that zero weight is rejected."""
        with pytest.raises(ValueError):
            WeightModel(value=0)

    def test_negative_weight_rejected(self):
        """Test that negative weight is rejected."""
        with pytest.raises(ValueError):
            WeightModel(value=-5.0)


class TestDimensionsModel:
    """Test DimensionsModel validation."""

    def test_dimensions_with_defaults(self):
        """Test dimensions with default unit."""
        dims = DimensionsModel(width=45.0, height=90.0, length=50.0)

        assert dims.width == 45.0
        assert dims.height == 90.0
        assert dims.length == 50.0
        assert dims.unit == DimensionUnit.CM

    def test_dimensions_with_custom_unit(self):
        """Test dimensions with custom unit."""
        dims = DimensionsModel(
            width=18.0, height=36.0, length=20.0, unit=DimensionUnit.IN
        )

        assert dims.unit == DimensionUnit.IN

    def test_zero_dimension_rejected(self):
        """Test that zero dimensions are rejected."""
        with pytest.raises(ValueError):
            DimensionsModel(width=0, height=90.0, length=50.0)


class TestShippingModel:
    """Test ShippingModel validation."""

    def test_shipping_defaults(self):
        """Test shipping with default values."""
        shipping = ShippingModel()

        assert shipping.is_physical is True
        assert shipping.weight is None
        assert shipping.dimensions is None
        assert shipping.shipping_class == ShippingClass.STANDARD

    def test_shipping_with_weight_and_dimensions(self):
        """Test shipping with full details."""
        shipping = ShippingModel(
            is_physical=True,
            weight=WeightModel(value=7.5, unit=WeightUnit.KG),
            dimensions=DimensionsModel(width=45.0, height=90.0, length=50.0),
            shipping_class=ShippingClass.BULKY,
        )

        assert shipping.weight.value == 7.5
        assert shipping.dimensions.width == 45.0
        assert shipping.shipping_class == ShippingClass.BULKY


class TestInventoryModel:
    """Test InventoryModel validation."""

    def test_inventory_defaults(self):
        """Test inventory with default values."""
        inventory = InventoryModel()

        assert inventory.stock_quantity == 0
        assert inventory.stock_status == StockStatus.IN_STOCK
        assert inventory.allow_backorder is False

    def test_inventory_with_stock(self):
        """Test inventory with stock quantity."""
        inventory = InventoryModel(stock_quantity=25, stock_status=StockStatus.IN_STOCK)

        assert inventory.stock_quantity == 25
        assert inventory.stock_status == StockStatus.IN_STOCK

    def test_inventory_out_of_stock(self):
        """Test out of stock inventory."""
        inventory = InventoryModel(
            stock_quantity=0, stock_status=StockStatus.OUT_OF_STOCK
        )

        assert inventory.stock_quantity == 0
        assert inventory.stock_status == StockStatus.OUT_OF_STOCK

    def test_negative_stock_rejected(self):
        """Test that negative stock is rejected."""
        with pytest.raises(ValueError):
            InventoryModel(stock_quantity=-5)


class TestIdentifiersModel:
    """Test IdentifiersModel validation."""

    def test_empty_identifiers(self):
        """Test identifiers with all None values."""
        identifiers = IdentifiersModel()

        assert identifiers.barcode is None
        assert identifiers.manufacturer_part_number is None
        assert identifiers.country_of_origin is None

    def test_country_code_uppercase(self):
        """Test that country code is converted to uppercase."""
        identifiers = IdentifiersModel(country_of_origin="de")

        assert identifiers.country_of_origin == "DE"

    def test_full_identifiers(self):
        """Test identifiers with all fields."""
        identifiers = IdentifiersModel(
            barcode="4006381333931",
            manufacturer_part_number="AC-CHAIR-RED-01",
            country_of_origin="de",
        )

        assert identifiers.barcode == "4006381333931"
        assert identifiers.manufacturer_part_number == "AC-CHAIR-RED-01"
        assert identifiers.country_of_origin == "DE"


class TestItemCreate:
    """Test ItemCreate model validation."""

    def test_create_minimal_item(self):
        """Test creating item with minimal required fields."""
        item = ItemCreate(
            sku="CHAIR-RED-001",
            name="Red Wooden Chair",
            slug="red-wooden-chair",
            price=PriceModel(amount=9999, currency="EUR"),
        )

        assert item.sku == "CHAIR-RED-001"
        assert item.name == "Red Wooden Chair"
        assert item.slug == "red-wooden-chair"
        assert item.price.amount == 9999
        assert item.status == ItemStatus.DRAFT  # Default

    def test_slug_lowercase_validation(self):
        """Test that slug is converted to lowercase."""
        item = ItemCreate(
            sku="TEST-001",
            name="Test",
            slug="RED-Wooden-CHAIR",
            price=PriceModel(amount=1000, currency="EUR"),
        )

        assert item.slug == "red-wooden-chair"

    def test_slug_whitespace_stripped(self):
        """Test that slug whitespace is stripped."""
        item = ItemCreate(
            sku="TEST-001",
            name="Test",
            slug="  test-item  ",
            price=PriceModel(amount=1000, currency="EUR"),
        )

        assert item.slug == "test-item"

    def test_create_full_item(self):
        """Test creating item with all fields."""
        item = ItemCreate(
            sku="CHAIR-RED-001",
            status=ItemStatus.ACTIVE,
            name="Red Wooden Chair",
            slug="red-wooden-chair",
            short_description="Comfortable red wooden chair",
            description="Long description here...",
            categories=[uuid4(), uuid4()],
            brand="Acme Furniture",
            price=PriceModel(
                amount=9999, currency="EUR", includes_tax=True, original_amount=12999
            ),
            media=MediaModel(
                main_image="https://example.com/main.jpg",
                gallery=["https://example.com/side.jpg"],
            ),
            inventory=InventoryModel(
                stock_quantity=25, stock_status=StockStatus.IN_STOCK
            ),
            shipping=ShippingModel(
                is_physical=True,
                weight=WeightModel(value=7.5, unit=WeightUnit.KG),
                dimensions=DimensionsModel(width=45.0, height=90.0, length=50.0),
            ),
            attributes={"color": "red", "material": "wood"},
            identifiers=IdentifiersModel(
                barcode="4006381333931",
                manufacturer_part_number="AC-CHAIR-RED-01",
                country_of_origin="DE",
            ),
        )

        assert item.sku == "CHAIR-RED-001"
        assert item.status == ItemStatus.ACTIVE
        assert len(item.categories) == 2
        assert item.brand == "Acme Furniture"
        assert item.attributes["color"] == "red"
        assert item.identifiers.country_of_origin == "DE"

    def test_required_fields_validation(self):
        """Test that required fields are enforced."""
        with pytest.raises(ValueError):
            ItemCreate(
                # Missing sku, name, slug, price
            )


class TestItemUpdate:
    """Test ItemUpdate model for partial updates."""

    def test_empty_update(self):
        """Test that all fields are optional in update."""
        update = ItemUpdate()

        data = update.model_dump(exclude_unset=True)
        assert data == {}

    def test_partial_update_name_only(self):
        """Test updating only name field."""
        update = ItemUpdate(name="Updated Name")

        data = update.model_dump(exclude_unset=True)
        assert "name" in data
        assert "sku" not in data
        assert data["name"] == "Updated Name"

    def test_partial_update_price(self):
        """Test updating only price."""
        update = ItemUpdate(price=PriceModel(amount=8999, currency="EUR"))

        data = update.model_dump(exclude_unset=True)
        assert "price" in data
        assert data["price"]["amount"] == 8999

    def test_slug_validation_in_update(self):
        """Test slug normalization in updates."""
        update = ItemUpdate(slug="UPPER-CASE-SLUG")

        assert update.slug == "upper-case-slug"

    def test_update_multiple_fields(self):
        """Test updating multiple fields."""
        update = ItemUpdate(
            name="New Name",
            status=ItemStatus.ACTIVE,
            price=PriceModel(amount=7999, currency="EUR"),
        )

        data = update.model_dump(exclude_unset=True)
        assert len(data) == 3
        assert data["name"] == "New Name"
        assert data["status"] == ItemStatus.ACTIVE


class TestItemResponse:
    """Test ItemResponse model."""

    def test_item_response_includes_system_fields(self):
        """Test that response includes uuid and timestamps."""
        response = ItemResponse(
            uuid=uuid4(),
            sku="TEST-001",
            name="Test Item",
            slug="test-item",
            status=ItemStatus.ACTIVE,
            price=PriceModel(amount=1000, currency="EUR"),
            media=MediaModel(),
            inventory=InventoryModel(),
            shipping=ShippingModel(),
            categories=[],
            attributes={},
            identifiers=IdentifiersModel(),
            custom={},
            system=SystemModel(),
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

        assert isinstance(response.uuid, UUID)
        assert isinstance(response.created_at, datetime)
        assert isinstance(response.updated_at, datetime)


class TestEnums:
    """Test enum values and conversions."""

    def test_item_status_values(self):
        """Test ItemStatus enum has correct values."""
        assert ItemStatus.DRAFT.value == "draft"
        assert ItemStatus.ACTIVE.value == "active"
        assert ItemStatus.ARCHIVED.value == "archived"

    def test_stock_status_values(self):
        """Test StockStatus enum values."""
        assert StockStatus.IN_STOCK.value == "in_stock"
        assert StockStatus.OUT_OF_STOCK.value == "out_of_stock"
        assert StockStatus.PREORDER.value == "preorder"
        assert StockStatus.BACKORDER.value == "backorder"

    def test_tax_class_values(self):
        """Test TaxClass enum values."""
        assert TaxClass.STANDARD.value == "standard"
        assert TaxClass.REDUCED.value == "reduced"
        assert TaxClass.NONE.value == "none"

    def test_shipping_class_values(self):
        """Test ShippingClass enum values."""
        assert ShippingClass.STANDARD.value == "standard"
        assert ShippingClass.BULKY.value == "bulky"
        assert ShippingClass.LETTER.value == "letter"

    def test_weight_unit_values(self):
        """Test WeightUnit enum values."""
        assert WeightUnit.KG.value == "kg"
        assert WeightUnit.LB.value == "lb"
        assert WeightUnit.G.value == "g"

    def test_dimension_unit_values(self):
        """Test DimensionUnit enum values."""
        assert DimensionUnit.CM.value == "cm"
        assert DimensionUnit.M.value == "m"
        assert DimensionUnit.IN.value == "in"
        assert DimensionUnit.FT.value == "ft"


class TestValidationEdgeCases:
    """Test edge cases and validation scenarios."""

    @pytest.mark.parametrize(
        "currency,expected",
        [
            ("eur", "EUR"),
            ("usd", "USD"),
            ("gbp", "GBP"),
            ("EUR", "EUR"),
            ("UsD", "USD"),
        ],
    )
    def test_currency_normalization(self, currency, expected):
        """Test currency normalization with various inputs."""
        price = PriceModel(amount=1000, currency=currency)
        assert price.currency == expected

    @pytest.mark.parametrize(
        "slug,expected",
        [
            ("test-item", "test-item"),
            ("TEST-ITEM", "test-item"),
            ("  Test Item  ", "test item"),
            ("MiXeD-CaSe", "mixed-case"),
        ],
    )
    def test_slug_normalization(self, slug, expected):
        """Test slug normalization with various inputs."""
        item = ItemCreate(
            sku="TEST",
            name="Test",
            slug=slug,
            price=PriceModel(amount=1000, currency="EUR"),
        )
        assert item.slug == expected

    @pytest.mark.parametrize(
        "country,expected",
        [
            ("de", "DE"),
            ("us", "US"),
            ("DE", "DE"),
            ("Us", "US"),
        ],
    )
    def test_country_code_normalization(self, country, expected):
        """Test country code normalization."""
        identifiers = IdentifiersModel(country_of_origin=country)
        assert identifiers.country_of_origin == expected

    def test_custom_field_accepts_any_structure(self):
        """Test that custom field accepts any structure."""
        item = ItemCreate(
            sku="TEST",
            name="Test",
            slug="test",
            price=PriceModel(amount=1000, currency="EUR"),
            custom={
                "seo": {"meta_title": "Test", "meta_description": "Desc"},
                "reviews": {"average_rating": 4.5, "total": 127},
                "anything": {"can": {"go": ["here"]}},
            },
        )

        assert "seo" in item.custom
        assert item.custom["reviews"]["average_rating"] == 4.5

    def test_attributes_field_accepts_any_structure(self):
        """Test that attributes field accepts any structure."""
        item = ItemCreate(
            sku="TEST",
            name="Test",
            slug="test",
            price=PriceModel(amount=1000, currency="EUR"),
            attributes={
                "color": "red",
                "size": "large",
                "material": "wood",
                "count": 5,
            },
        )

        assert item.attributes["color"] == "red"
        assert item.attributes["count"] == 5
