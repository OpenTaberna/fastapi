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

    This is a meta function that can check any field for duplicates by dispatching
    to the appropriate repository method.

    Args:
        repo: Item repository instance
        field_name: Name of the field to check (e.g., "sku", "slug")
        field_value: Value to check for duplicates
        exclude_uuid: Optional UUID to exclude from the check (for updates)

    Raises:
        ValidationError: If duplicate is found (via duplicate_entry helper)
        ValueError: If field_name is not supported for duplicate checking

    Examples:
        >>> # Check for duplicate SKU
        >>> await check_duplicate_field(repo, "sku", "CHAIR-RED-001")
        
        >>> # Check for duplicate slug, excluding current item
        >>> await check_duplicate_field(repo, "slug", "red-chair", exclude_uuid=item_uuid)
    """
    # Map field names to repository methods
    field_checks = {
        "sku": repo.sku_exists,
        "slug": repo.slug_exists,
    }

    if field_name not in field_checks:
        raise ValueError(
            f"Duplicate check not implemented for field: {field_name}. "
            f"Supported fields: {', '.join(field_checks.keys())}"
        )

    # Call the appropriate repository method
    exists_method = field_checks[field_name]
    exists = await exists_method(field_value, exclude_uuid=exclude_uuid)

    if exists:
        raise duplicate_entry("Item", field_name, field_value)
