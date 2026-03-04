"""
Integration tests for crud-item-store API endpoints.

These tests run against the actual running API and database.
Make sure Docker containers are running before executing these tests.
"""

import uuid
import pytest
import requests

# API base URL - adjust if your API is on a different host/port
API_BASE_URL = "http://172.20.20.21:8001/v1/items"


@pytest.fixture
def valid_item_data():
    """Return valid item creation data."""
    unique_id = uuid.uuid4().hex[:8]
    return {
        "sku": f"TEST-{unique_id.upper()}",
        "status": "active",
        "name": "Integration Test Product",
        "slug": f"integration-test-product-{unique_id}",
        "short_description": "A short description",
        "description": "A product for integration testing",
        "brand": "TestBrand",
        "categories": [str(uuid.uuid4())],
        "price": {
            "amount": 9999,
            "currency": "USD",
            "includes_tax": True,
            "original_amount": None,
            "tax_class": "standard",
        },
        "media": {"main_image": None, "gallery": []},
        "inventory": {
            "stock_quantity": 100,
            "stock_status": "in_stock",
            "allow_backorder": False,
        },
        "shipping": {
            "is_physical": True,
            "shipping_class": "standard",
            "weight": None,
            "dimensions": None,
        },
        "attributes": {},
        "identifiers": {
            "barcode": None,
            "manufacturer_part_number": None,
            "country_of_origin": None,
        },
        "custom": {},
        "system": {"version": 1, "source": "api", "locale": "en_US"},
    }


@pytest.fixture
def created_item(valid_item_data):
    """Create an item and return its UUID for cleanup."""
    response = requests.post(API_BASE_URL + "/", json=valid_item_data)
    assert response.status_code == 201
    item = response.json()
    yield item
    # Cleanup: delete the item after test
    requests.delete(f"{API_BASE_URL}/{item['uuid']}")


class TestItemCRUD:
    """Test CRUD operations on items."""

    def test_create_item_success(self, valid_item_data):
        """Test creating a new item."""
        response = requests.post(API_BASE_URL + "/", json=valid_item_data)

        assert response.status_code == 201
        data = response.json()
        assert data["sku"] == valid_item_data["sku"]
        assert data["name"] == valid_item_data["name"]
        assert "uuid" in data
        assert "created_at" in data
        assert "updated_at" in data

        # Cleanup
        requests.delete(f"{API_BASE_URL}/{data['uuid']}")

    def test_create_item_duplicate_sku(self, created_item):
        """Test creating item with duplicate SKU fails."""
        duplicate_data = {
            "sku": created_item["sku"],
            "name": "Duplicate",
            "slug": "duplicate-slug",
            "brand": "Test",
            "categories": [str(uuid.uuid4())],
            "price": {"amount": 1000, "currency": "USD"},
        }

        response = requests.post(API_BASE_URL + "/", json=duplicate_data)
        assert response.status_code == 422
        assert "already exists" in response.json()["message"]

    def test_get_item_by_uuid(self, created_item):
        """Test retrieving an item by UUID."""
        response = requests.get(f"{API_BASE_URL}/{created_item['uuid']}")

        assert response.status_code == 200
        data = response.json()
        assert data["uuid"] == created_item["uuid"]
        assert data["sku"] == created_item["sku"]

    def test_get_item_not_found(self):
        """Test retrieving non-existent item returns 404."""
        fake_uuid = str(uuid.uuid4())
        response = requests.get(f"{API_BASE_URL}/{fake_uuid}")

        assert response.status_code == 404
        assert "not found" in response.json()["message"]

    def test_get_item_by_sku(self, created_item):
        """Test retrieving an item by SKU."""
        response = requests.get(f"{API_BASE_URL}/by-sku/{created_item['sku']}")

        assert response.status_code == 200
        data = response.json()
        assert data["uuid"] == created_item["uuid"]
        assert data["sku"] == created_item["sku"]

    def test_list_items(self, created_item):
        """Test listing items with pagination."""
        response = requests.get(API_BASE_URL + "/")

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "page_info" in data
        assert data["page_info"]["total"] >= 1
        assert isinstance(data["items"], list)
        assert data["success"] is True

    def test_list_items_pagination(self, created_item):
        """Test pagination parameters."""
        response = requests.get(API_BASE_URL + "/?skip=0&limit=10")

        assert response.status_code == 200
        data = response.json()
        assert data["page_info"]["size"] == 10
        assert len(data["items"]) <= 10

    def test_update_item(self, created_item):
        """Test updating an item."""
        update_data = {
            "name": "Updated Product Name",
            "price": {"amount": 15999, "currency": "EUR"},
        }

        response = requests.patch(
            f"{API_BASE_URL}/{created_item['uuid']}", json=update_data
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Product Name"
        assert data["price"]["amount"] == 15999
        assert data["price"]["currency"] == "EUR"
        # SKU should not change
        assert data["sku"] == created_item["sku"]

    def test_update_item_not_found(self):
        """Test updating non-existent item returns 404."""
        fake_uuid = str(uuid.uuid4())
        update_data = {"name": "Updated"}

        response = requests.patch(f"{API_BASE_URL}/{fake_uuid}", json=update_data)
        assert response.status_code == 404

    def test_delete_item(self, valid_item_data):
        """Test deleting an item."""
        # Create item
        create_response = requests.post(API_BASE_URL + "/", json=valid_item_data)
        assert create_response.status_code == 201, (
            f"Failed to create item: {create_response.json()}"
        )
        item_uuid = create_response.json()["uuid"]

        # Delete item
        delete_response = requests.delete(f"{API_BASE_URL}/{item_uuid}")
        assert delete_response.status_code == 204

        # Verify deleted
        get_response = requests.get(f"{API_BASE_URL}/{item_uuid}")
        assert get_response.status_code == 404

    def test_delete_item_not_found(self):
        """Test deleting non-existent item returns 404."""
        fake_uuid = str(uuid.uuid4())
        response = requests.delete(f"{API_BASE_URL}/{fake_uuid}")
        assert response.status_code == 404


class TestValidation:
    """Test API validation."""

    def test_invalid_price_amount(self):
        """Test that float price amounts are rejected."""
        invalid_data = {
            "sku": "TEST-001",
            "name": "Test",
            "slug": "test",
            "brand": "Test",
            "categories": [str(uuid.uuid4())],
            "price": {"amount": 99.99, "currency": "USD"},  # Should be int
        }

        response = requests.post(API_BASE_URL + "/", json=invalid_data)
        assert response.status_code == 422

    def test_invalid_category_uuid(self):
        """Test that invalid UUIDs in categories are rejected."""
        invalid_data = {
            "sku": "TEST-001",
            "name": "Test",
            "slug": "test",
            "brand": "Test",
            "categories": ["not-a-uuid"],
            "price": {"amount": 9999, "currency": "USD"},
        }

        response = requests.post(API_BASE_URL + "/", json=invalid_data)
        assert response.status_code == 422

    def test_missing_required_fields(self):
        """Test that missing required fields are rejected."""
        invalid_data = {
            "name": "Test"
            # Missing sku, slug, brand, categories, price
        }

        response = requests.post(API_BASE_URL + "/", json=invalid_data)
        assert response.status_code == 422


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
