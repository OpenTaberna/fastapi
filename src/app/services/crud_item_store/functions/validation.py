"""
Item Validation Functions

Functions for validating item data and checking business rules.
"""

from typing import Any, Optional
from uuid import UUID

from app.shared.exceptions import duplicate_entry
from ..services.database import ItemRepository


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
    # Use the repository's generic field_exists method
    # This will raise ValueError if field doesn't exist on the model
    exists = await repo.field_exists(field_name, field_value, exclude_uuid=exclude_uuid)

    if exists:
        raise duplicate_entry("Item", field_name, field_value)
