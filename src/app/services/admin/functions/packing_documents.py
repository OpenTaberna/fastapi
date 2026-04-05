"""
Packing Documents

Pure functions that produce printable HTML documents for warehouse operations:

  - render_packing_slip  — single-order pick & pack sheet
  - render_pick_list     — aggregated SKU list across a batch of PAID orders

Both functions return raw HTML strings (no file I/O). The calling router
streams the result directly to the browser with Content-Type: text/html.
All formatting is inline CSS so the documents print correctly without an
external stylesheet.
"""

from collections import defaultdict
from datetime import UTC, datetime
from uuid import UUID

from app.services.customers.models.customers_db_models import AddressDB, CustomerDB
from app.services.orders.models.orders_db_models import OrderDB, OrderItemDB
from app.services.shipments.models.shipments_db_models import ShipmentDB
from app.shared.logger import get_logger

from ..models.admin_models import PickListItem, PickListResponse

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Packing slip
# ---------------------------------------------------------------------------


def render_packing_slip(
    order: OrderDB,
    items: list[OrderItemDB],
    customer: CustomerDB | None,
    shipping_address: AddressDB | None,
    shipment: ShipmentDB | None,
) -> str:
    """
    Render a printable HTML packing slip for a single order.

    The returned HTML includes inline CSS so it renders correctly when
    opened directly in a browser or printed via the browser's print dialog.
    No external assets are required.

    Args:
        order:            The OrderDB row for the order being packed.
        items:            All OrderItemDB line items for this order.
        customer:         The CustomerDB who placed the order, or None.
        shipping_address: The customer's shipping AddressDB, or None.
        shipment:         The ShipmentDB record if a shipment exists, or None.

    Returns:
        A complete, self-contained HTML document as a string.
    """
    logger.debug(
        "Rendering packing slip",
        extra={"order_id": str(order.id), "item_count": len(items)},
    )
    customer_name = f"{customer.first_name} {customer.last_name}" if customer else "—"
    customer_email = customer.email if customer else "—"

    address_lines = _format_address(shipping_address)
    tracking = (
        shipment.tracking_number if shipment and shipment.tracking_number else "—"
    )
    carrier = shipment.carrier if shipment else "—"
    generated = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

    rows = "\n".join(
        f"<tr>"
        f"<td>{item.sku}</td>"
        f"<td style='text-align:center'>{item.quantity}</td>"
        f"<td style='text-align:right'>{item.unit_price / 100:.2f} {order.currency}</td>"
        f"<td style='text-align:right'>{(item.quantity * item.unit_price) / 100:.2f} {order.currency}</td>"
        f"</tr>"
        for item in items
    )

    total_formatted = f"{order.total_amount / 100:.2f} {order.currency}"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Packing Slip — Order {order.id}</title>
  <style>
    body {{ font-family: Arial, sans-serif; font-size: 12px; margin: 20px; color: #222; }}
    h1 {{ font-size: 18px; border-bottom: 2px solid #000; padding-bottom: 6px; }}
    .meta {{ display: flex; gap: 40px; margin-bottom: 20px; }}
    .meta div {{ flex: 1; }}
    .meta h2 {{ font-size: 13px; margin: 0 0 6px; text-transform: uppercase; color: #555; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
    th {{ background: #f0f0f0; text-align: left; padding: 6px 8px; border-bottom: 1px solid #ccc; }}
    td {{ padding: 5px 8px; border-bottom: 1px solid #eee; }}
    .total-row td {{ font-weight: bold; border-top: 2px solid #000; }}
    .footer {{ margin-top: 30px; font-size: 10px; color: #888; }}
    @media print {{ .no-print {{ display: none; }} }}
  </style>
</head>
<body>
  <h1>Packing Slip</h1>

  <div class="meta">
    <div>
      <h2>Order</h2>
      <p><strong>ID:</strong> {order.id}</p>
      <p><strong>Status:</strong> {order.status}</p>
      <p><strong>Date:</strong> {order.created_at.strftime("%Y-%m-%d") if order.created_at else "—"}</p>
      <p><strong>Carrier:</strong> {carrier}</p>
      <p><strong>Tracking:</strong> {tracking}</p>
    </div>
    <div>
      <h2>Ship To</h2>
      <p><strong>{customer_name}</strong></p>
      <p>{customer_email}</p>
      {address_lines}
    </div>
  </div>

  <table>
    <thead>
      <tr>
        <th>SKU</th>
        <th style="text-align:center">Qty</th>
        <th style="text-align:right">Unit Price</th>
        <th style="text-align:right">Line Total</th>
      </tr>
    </thead>
    <tbody>
      {rows}
    </tbody>
    <tfoot>
      <tr class="total-row">
        <td colspan="3">Order Total</td>
        <td style="text-align:right">{total_formatted}</td>
      </tr>
    </tfoot>
  </table>

  <div class="footer">Generated {generated}</div>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Pick list
# ---------------------------------------------------------------------------


def build_pick_list(
    orders: list[OrderDB],
    all_items: list[OrderItemDB],
) -> PickListResponse:
    """
    Aggregate order items across a batch of orders into a pick list.

    Groups items by SKU and sums the quantity and order count so a warehouse
    worker can pick all units for the batch in a single warehouse pass.

    Args:
        orders:    List of OrderDB rows included in the batch (typically all PAID).
        all_items: All OrderItemDB rows belonging to those orders (pre-fetched).

    Returns:
        PickListResponse with items sorted by SKU ascending.
    """
    logger.debug(
        "Building pick list",
        extra={"order_count": len(orders), "item_count": len(all_items)},
    )
    sku_qty: dict[str, int] = defaultdict(int)
    sku_orders: dict[str, set[UUID]] = defaultdict(set)

    for item in all_items:
        sku_qty[item.sku] += item.quantity
        sku_orders[item.sku].add(item.order_id)

    pick_items = sorted(
        [
            PickListItem(
                sku=sku,
                total_quantity=sku_qty[sku],
                order_count=len(sku_orders[sku]),
            )
            for sku in sku_qty
        ],
        key=lambda x: x.sku,
    )

    return PickListResponse(
        items=pick_items,
        order_ids=[order.id for order in orders],
        generated_at=datetime.now(UTC),
    )


def render_pick_list_html(pick_list: PickListResponse) -> str:
    """
    Render a printable HTML pick list from a PickListResponse.

    Args:
        pick_list: Pre-built PickListResponse (from build_pick_list).

    Returns:
        A complete, self-contained HTML document as a string.
    """
    generated = pick_list.generated_at.strftime("%Y-%m-%d %H:%M UTC")
    order_count = len(pick_list.order_ids)

    rows = "\n".join(
        f"<tr>"
        f"<td>{item.sku}</td>"
        f"<td style='text-align:center'>{item.total_quantity}</td>"
        f"<td style='text-align:center'>{item.order_count}</td>"
        f"<td><input type='checkbox' /></td>"
        f"</tr>"
        for item in pick_list.items
    )

    total_units = sum(item.total_quantity for item in pick_list.items)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Pick List — {generated}</title>
  <style>
    body {{ font-family: Arial, sans-serif; font-size: 12px; margin: 20px; color: #222; }}
    h1 {{ font-size: 18px; border-bottom: 2px solid #000; padding-bottom: 6px; }}
    .summary {{ margin-bottom: 16px; color: #555; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
    th {{ background: #f0f0f0; text-align: left; padding: 6px 8px; border-bottom: 1px solid #ccc; }}
    td {{ padding: 5px 8px; border-bottom: 1px solid #eee; }}
    .total-row td {{ font-weight: bold; border-top: 2px solid #000; }}
    .footer {{ margin-top: 30px; font-size: 10px; color: #888; }}
    @media print {{ input[type=checkbox] {{ width: 14px; height: 14px; }} }}
  </style>
</head>
<body>
  <h1>Pick List</h1>
  <div class="summary">
    <strong>{len(pick_list.items)}</strong> SKUs &nbsp;|&nbsp;
    <strong>{total_units}</strong> total units &nbsp;|&nbsp;
    <strong>{order_count}</strong> orders &nbsp;|&nbsp;
    Generated {generated}
  </div>

  <table>
    <thead>
      <tr>
        <th>SKU</th>
        <th style="text-align:center">Total Qty</th>
        <th style="text-align:center">Orders</th>
        <th style="text-align:center">Picked ✓</th>
      </tr>
    </thead>
    <tbody>
      {rows}
    </tbody>
    <tfoot>
      <tr class="total-row">
        <td>Total</td>
        <td style="text-align:center">{total_units}</td>
        <td style="text-align:center">{order_count}</td>
        <td></td>
      </tr>
    </tfoot>
  </table>

  <div class="footer">Generated {generated}</div>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _format_address(address: AddressDB | None) -> str:
    """
    Render an AddressDB as an HTML snippet for embedding in a packing slip.

    Args:
        address: The AddressDB to format, or None.

    Returns:
        HTML paragraph tags with address lines, or a dash if address is None.
    """
    if address is None:
        return "<p>—</p>"
    return (
        f"<p>{address.street}</p>"
        f"<p>{address.zip_code} {address.city}</p>"
        f"<p>{address.country}</p>"
    )
