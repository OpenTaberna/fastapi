"""
Admin Functions Package

Business logic and transformation functions for the admin service.
"""

from .admin_transformations import (
    db_to_admin_order_detail_response,
    db_to_order_response,
)
from .order_context import OrderContext, fetch_order_context
from .packing_documents import (
    build_pick_list,
    render_packing_slip,
    render_pick_list_html,
)
from .send_tracking_email import send_tracking_email
from .shipment_functions import create_shipment, mark_order_shipped

__all__ = [
    # Transformations
    "db_to_order_response",
    "db_to_admin_order_detail_response",
    # Order context loader
    "OrderContext",
    "fetch_order_context",
    # Packing documents
    "render_packing_slip",
    "build_pick_list",
    "render_pick_list_html",
    # Shipment lifecycle
    "create_shipment",
    "mark_order_shipped",
    # Email
    "send_tracking_email",
]
