"""
Item Transformations

Functions for converting between different item representations.
"""

from typing import Any

from ..models import ItemStatus, ItemDB
from ..responses import ItemResponse


def db_to_response(item: ItemDB) -> ItemResponse:
    """
    Convert database model to response model.

    Uses Pydantic's model_validate with from_attributes=True (set in ItemResponse's
    model_config) so all field coercions (str→ItemStatus, list[str]→list[UUID], etc.)
    are handled automatically. Adding a new field to ItemDB/ItemResponse no longer
    requires a manual update here.

    Args:
        item: Database item instance

    Returns:
        ItemResponse with all fields
    """
    return ItemResponse.model_validate(item)


def prepare_item_update_data(update_data: dict[str, Any]) -> dict[str, Any]:
    """
    Convert update data to database-ready format.

    Transforms enums to their string values, UUIDs to strings,
    and nested Pydantic models to dictionaries for JSONB storage.

    Args:
        update_data: Raw update data from Pydantic model

    Returns:
        Transformed data ready for database storage

    Examples:
        >>> data = {"status": ItemStatus.ACTIVE, "price": PriceModel(...)}
        >>> prepared = prepare_item_update_data(data)
        >>> # Returns: {"status": "active", "price": {...}}
    """
    for key, value in update_data.items():
        if key == "status" and isinstance(value, ItemStatus):
            update_data[key] = value.value
        elif key == "categories" and value is not None:
            update_data[key] = [str(cat) for cat in value]
        elif hasattr(value, "model_dump"):
            update_data[key] = value.model_dump()

    return update_data
