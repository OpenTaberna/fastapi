"""
Item Transformations

Functions for converting between different item representations.
"""

from uuid import UUID

from ..models import ItemStatus
from ..models.database import ItemDB
from ..responses import ItemResponse


def db_to_response(item: ItemDB) -> ItemResponse:
    """
    Convert database model to response model.

    Args:
        item: Database item instance

    Returns:
        ItemResponse with all fields
    """
    return ItemResponse(
        uuid=item.uuid,
        sku=item.sku,
        status=ItemStatus(item.status),
        name=item.name,
        slug=item.slug,
        short_description=item.short_description,
        description=item.description,
        categories=[UUID(cat) for cat in item.categories],
        brand=item.brand,
        price=item.price,
        media=item.media,
        inventory=item.inventory,
        shipping=item.shipping,
        attributes=item.attributes,
        identifiers=item.identifiers,
        custom=item.custom,
        system=item.system,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )
