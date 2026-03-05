"""
Item Validation Functions

Functions for validating item data and checking business rules.
"""

from typing import Any, Optional
from uuid import UUID

from app.shared.exceptions import duplicate_entry
from app.shared.logger import get_logger
from ..models import ItemDB
from ..services import ItemRepository

logger = get_logger(__name__)


async def check_duplicate_field(
    repo: ItemRepository,
    field_name: str,
    field_value: Any,
    exclude_uuid: Optional[UUID] = None,
) -> None:
    """
    Check if a field value already exists and raise exception if duplicate found.

    This is a meta function that can check any field for duplicates using the
    repository's generic field_exists() method.

    Args:
        repo: Item repository instance
        field_name: Name of the field to check (e.g., "sku", "slug", "name")
        field_value: Value to check for duplicates
        exclude_uuid: Optional UUID to exclude from the check (for updates)

    Raises:
        ValidationError: If duplicate is found (via duplicate_entry helper)
        ValueError: If field_name is not a valid model field

    Examples:
        >>> # Check for duplicate SKU
        >>> await check_duplicate_field(repo, "sku", "CHAIR-RED-001")

        >>> # Check for duplicate slug, excluding current item
        >>> await check_duplicate_field(repo, "slug", "red-chair", exclude_uuid=item_uuid)

        >>> # Can check any field on the model
        >>> await check_duplicate_field(repo, "name", "Test Product")
    """
    logger.debug(
        "Checking for duplicate field value",
        extra={"field_name": field_name, "exclude_uuid": str(exclude_uuid) if exclude_uuid else None},
    )
    # Use the repository's generic field_exists method
    # This will raise ValueError if field doesn't exist on the model
    exists = await repo.field_exists(field_name, field_value, exclude_uuid=exclude_uuid)

    if exists:
        raise duplicate_entry("Item", field_name, field_value)


async def validate_update_conflicts(
    repo: ItemRepository,
    existing_item: ItemDB,
    update_data: dict[str, Any],
    item_uuid: UUID,
) -> None:
    """
    Validate that update data doesn't create conflicts with existing items.

    Checks for SKU and slug conflicts when these fields are being updated.
    Only validates if the value is actually changing.

    Args:
        repo: Item repository instance
        existing_item: The current item being updated
        update_data: Dictionary of fields to update
        item_uuid: UUID of the item being updated

    Raises:
        ValidationError: If SKU or slug conflicts with another item

    Examples:
        >>> update_data = {"sku": "NEW-SKU", "name": "Updated Name"}
        >>> await validate_update_conflicts(repo, item, update_data, item_uuid)
    """
    # Check for SKU conflicts
    if "sku" in update_data and update_data["sku"] != existing_item.sku:
        await check_duplicate_field(
            repo, "sku", update_data["sku"], exclude_uuid=item_uuid
        )

    # Check for slug conflicts
    if "slug" in update_data and update_data["slug"] != existing_item.slug:
        await check_duplicate_field(
            repo, "slug", update_data["slug"], exclude_uuid=item_uuid
        )
