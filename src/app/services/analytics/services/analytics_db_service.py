"""
Analytics Database Service

Aggregation queries over orders, order items, payments, returns and inventory.

Everything here is read-only and computed live rather than from a rollup table.
That keeps the figures current and adds no moving parts, at the cost of scanning
the order history per request — see the indexes noted in ``orders_db_models``.

Three rules hold throughout:

**Soft-deleted orders never count.** ``orders.deleted_at`` is set on records that
must survive as history but must not appear in a total.

**Order money and line money are queried separately.** Joining orders to their
items and summing ``orders.total_amount`` multiplies each order's value by its
line count. The two are therefore computed in separate statements and merged in
Python — the join is only ever used for quantities and line revenue.

**Days are cut in the shop's timezone**, via ``timezone(tz, created_at)``, which
is Postgres' ``AT TIME ZONE``. Bucketing on raw UTC would move evening orders
into the following day for any shop east of Greenwich.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import Select, and_, case, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.crud_item_store.models.item_db_models import ItemDB
from app.services.inventory.models.inventory_db_models import InventoryItemDB
from app.services.orders.models.orders_db_models import OrderDB, OrderItemDB
from app.services.payments.models.payments_db_models import PaymentDB
from app.services.returns.models.returns_db_models import ReturnDB
from app.services.shipments.models.shipments_db_models import ShipmentDB
from app.shared.logger import get_logger

from ..functions import Interval, Period

logger = get_logger(__name__)

# Statuses whose order value counts as money actually taken. Mirrors the
# admin dashboard's definition so the two never disagree.
EARNED_STATUSES: tuple[str, ...] = ("paid", "ready_to_ship", "shipped")
REFUNDED_STATUS = "refunded"
CANCELLED_STATUS = "cancelled"


class AnalyticsRepository:
    """Read-only aggregation queries for the admin analytics endpoints."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Shared predicates
    # ------------------------------------------------------------------

    @staticmethod
    def _in_period(period: Period):
        """Live orders created inside the half-open window."""
        return and_(
            OrderDB.deleted_at.is_(None),
            OrderDB.created_at >= period.start,
            OrderDB.created_at < period.end,
        )

    @staticmethod
    def _earned() -> tuple:
        return (OrderDB.status.in_(EARNED_STATUSES),)

    @staticmethod
    def _gross_expr():
        return func.coalesce(
            func.sum(
                case(
                    (OrderDB.status.in_(EARNED_STATUSES), OrderDB.total_amount),
                    else_=0,
                )
            ),
            0,
        )

    @staticmethod
    def _refunded_expr():
        return func.coalesce(
            func.sum(
                case((OrderDB.status == REFUNDED_STATUS, OrderDB.total_amount), else_=0)
            ),
            0,
        )

    @staticmethod
    def _earned_orders_expr():
        return func.count(distinct(OrderDB.id)).filter(
            OrderDB.status.in_(EARNED_STATUSES)
        )

    def _bucket_expr(self, interval: Interval, timezone_name: str):
        """
        Truncate ``created_at`` to a bucket, in the shop's local time.

        ``timezone(zone, timestamptz)`` is the function form of AT TIME ZONE and
        takes the zone as a bind parameter, so the shop's configured timezone
        never reaches SQL as interpolated text.
        """
        local = func.timezone(timezone_name, OrderDB.created_at)
        return func.date_trunc(interval.value, local)

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    async def order_totals_by_currency(
        self, period: Period
    ) -> dict[str, dict[str, int]]:
        """
        Order-level money and counts, grouped by currency.

        Deliberately does not join order_items — see the module docstring.
        """
        statement: Select = (
            select(
                OrderDB.currency,
                self._gross_expr().label("gross_revenue"),
                self._refunded_expr().label("refunded_revenue"),
                self._earned_orders_expr().label("orders"),
            )
            .where(self._in_period(period))
            .group_by(OrderDB.currency)
        )

        result = await self._session.execute(statement)
        return {
            row.currency: {
                "gross_revenue": int(row.gross_revenue or 0),
                "refunded_revenue": int(row.refunded_revenue or 0),
                "orders": int(row.orders or 0),
            }
            for row in result
        }

    async def units_by_currency(self, period: Period) -> dict[str, int]:
        """Units sold on revenue-producing orders, grouped by currency."""
        statement: Select = (
            select(
                OrderDB.currency,
                func.coalesce(func.sum(OrderItemDB.quantity), 0).label("units"),
            )
            .join(OrderItemDB, OrderItemDB.order_id == OrderDB.id)
            .where(self._in_period(period), *self._earned())
            .group_by(OrderDB.currency)
        )

        result = await self._session.execute(statement)
        return {row.currency: int(row.units or 0) for row in result}

    # ------------------------------------------------------------------
    # Time series
    # ------------------------------------------------------------------

    async def series_by_currency(
        self, period: Period, interval: Interval
    ) -> dict[str, dict[date, dict[str, int]]]:
        """
        Bucketed money and counts per currency.

        Returns only buckets that have orders; gap filling is the caller's job,
        since it needs the full window to know which buckets are missing.
        """
        bucket = self._bucket_expr(interval, period.timezone)

        statement: Select = (
            select(
                OrderDB.currency,
                bucket.label("bucket"),
                self._gross_expr().label("gross_revenue"),
                self._refunded_expr().label("refunded_revenue"),
                self._earned_orders_expr().label("orders"),
            )
            .where(self._in_period(period))
            .group_by(OrderDB.currency, bucket)
            .order_by(bucket)
        )

        result = await self._session.execute(statement)
        buckets: dict[str, dict[date, dict[str, int]]] = defaultdict(dict)
        for row in result:
            bucket_day = (
                row.bucket.date() if hasattr(row.bucket, "date") else row.bucket
            )
            buckets[row.currency][bucket_day] = {
                "gross_revenue": int(row.gross_revenue or 0),
                "refunded_revenue": int(row.refunded_revenue or 0),
                "orders": int(row.orders or 0),
                "units": 0,
            }

        for currency, units_by_bucket in (
            await self._series_units(period, interval)
        ).items():
            for bucket_day, units in units_by_bucket.items():
                buckets.setdefault(currency, {}).setdefault(
                    bucket_day,
                    {
                        "gross_revenue": 0,
                        "refunded_revenue": 0,
                        "orders": 0,
                        "units": 0,
                    },
                )["units"] = units

        return buckets

    async def _series_units(
        self, period: Period, interval: Interval
    ) -> dict[str, dict[date, int]]:
        """Units per bucket per currency, joined separately to avoid fan-out."""
        bucket = self._bucket_expr(interval, period.timezone)

        statement: Select = (
            select(
                OrderDB.currency,
                bucket.label("bucket"),
                func.coalesce(func.sum(OrderItemDB.quantity), 0).label("units"),
            )
            .join(OrderItemDB, OrderItemDB.order_id == OrderDB.id)
            .where(self._in_period(period), *self._earned())
            .group_by(OrderDB.currency, bucket)
        )

        result = await self._session.execute(statement)
        units: dict[str, dict[date, int]] = defaultdict(dict)
        for row in result:
            bucket_day = (
                row.bucket.date() if hasattr(row.bucket, "date") else row.bucket
            )
            units[row.currency][bucket_day] = int(row.units or 0)
        return units

    # ------------------------------------------------------------------
    # Products
    # ------------------------------------------------------------------

    async def product_performance(self, period: Period) -> list[dict]:
        """
        Per-SKU units, line revenue and order count over the window.

        Revenue here is the sum of line values (``quantity * unit_price``),
        which need not equal the order totals used elsewhere — an order total
        may carry shipping or adjustments that belong to no line.
        """
        statement: Select = (
            select(
                OrderDB.currency,
                OrderItemDB.sku,
                func.coalesce(func.sum(OrderItemDB.quantity), 0).label("units_sold"),
                func.coalesce(
                    func.sum(OrderItemDB.quantity * OrderItemDB.unit_price), 0
                ).label("gross_revenue"),
                func.count(distinct(OrderDB.id)).label("orders"),
            )
            .join(OrderItemDB, OrderItemDB.order_id == OrderDB.id)
            .where(self._in_period(period), *self._earned())
            .group_by(OrderDB.currency, OrderItemDB.sku)
        )

        result = await self._session.execute(statement)
        return [
            {
                "currency": row.currency,
                "sku": row.sku,
                "units_sold": int(row.units_sold or 0),
                "gross_revenue": int(row.gross_revenue or 0),
                "orders": int(row.orders or 0),
            }
            for row in result
        ]

    async def returns_by_sku(self, period: Period) -> dict[str, int]:
        """
        Orders containing each SKU where a return was raised.

        Returns are recorded per order, so a return on a two-line order counts
        against both SKUs. This is an upper bound per SKU, not a per-item rate,
        and is labelled as such in the response schema.
        """
        statement: Select = (
            select(
                OrderItemDB.sku,
                func.count(distinct(OrderDB.id)).label("orders_with_return"),
            )
            .join(OrderItemDB, OrderItemDB.order_id == OrderDB.id)
            .join(ReturnDB, ReturnDB.order_id == OrderDB.id)
            .where(self._in_period(period))
            .group_by(OrderItemDB.sku)
        )

        result = await self._session.execute(statement)
        return {row.sku: int(row.orders_with_return or 0) for row in result}

    async def item_names(self, skus: list[str]) -> dict[str, str]:
        """Catalogue names for the given SKUs. Missing SKUs are simply absent."""
        if not skus:
            return {}
        result = await self._session.execute(
            select(ItemDB.sku, ItemDB.name).where(ItemDB.sku.in_(skus))
        )
        return {row.sku: row.name for row in result}

    async def never_sold(self, sold_skus: list[str], limit: int = 50) -> list[dict]:
        """
        Active catalogue items with no sales in the window.

        Stock is joined optionally: an item without an inventory record is dead
        stock worth surfacing too, so a missing row must not drop it.
        """
        statement: Select = (
            select(
                ItemDB.sku,
                ItemDB.name,
                ItemDB.status,
                InventoryItemDB.on_hand,
            )
            .outerjoin(InventoryItemDB, InventoryItemDB.sku == ItemDB.sku)
            .where(ItemDB.status == "active")
            .order_by(ItemDB.name)
            .limit(limit)
        )
        if sold_skus:
            statement = statement.where(ItemDB.sku.notin_(sold_skus))

        result = await self._session.execute(statement)
        return [
            {
                "sku": row.sku,
                "name": row.name,
                "status": row.status,
                "on_hand": int(row.on_hand) if row.on_hand is not None else None,
            }
            for row in result
        ]

    # ------------------------------------------------------------------
    # Funnel
    # ------------------------------------------------------------------

    async def funnel_counts(self, period: Period) -> dict[str, int]:
        """
        Order lifecycle counts.

        Checkout is read from ``payments`` rather than from ``orders.status``.
        Status records only where an order is now, so a cancelled order is
        indistinguishable from one that never reached checkout. A payment row is
        written when checkout starts and survives whatever happens next.
        """
        created = await self._scalar(
            select(func.count(OrderDB.id)).where(self._in_period(period))
        )

        checkout_started = await self._scalar(
            select(func.count(distinct(OrderDB.id)))
            .join(PaymentDB, PaymentDB.order_id == OrderDB.id)
            .where(self._in_period(period))
        )

        paid = await self._scalar(
            select(func.count(distinct(OrderDB.id)))
            .join(PaymentDB, PaymentDB.order_id == OrderDB.id)
            .where(self._in_period(period), PaymentDB.status == "succeeded")
        )

        payment_failed = await self._scalar(
            select(func.count(distinct(OrderDB.id)))
            .join(PaymentDB, PaymentDB.order_id == OrderDB.id)
            .where(self._in_period(period), PaymentDB.status == "failed")
        )

        # Counted from shipments rather than order status: an order that shipped
        # and was later refunded no longer says "shipped", but it did ship.
        shipped = await self._scalar(
            select(func.count(distinct(OrderDB.id)))
            .join(ShipmentDB, ShipmentDB.order_id == OrderDB.id)
            .where(self._in_period(period), ShipmentDB.status == "handed_over")
        )

        cancelled = await self._scalar(
            select(func.count(OrderDB.id)).where(
                self._in_period(period), OrderDB.status == CANCELLED_STATUS
            )
        )

        return {
            "created": created,
            "checkout_started": checkout_started,
            "paid": paid,
            "shipped": shipped,
            "payment_failed": payment_failed,
            "payment_unresolved": max(checkout_started - paid - payment_failed, 0),
            "never_checked_out": max(created - checkout_started, 0),
            "cancelled": cancelled,
        }

    async def count_paid_orders(self, order_ids: list) -> int:
        """
        How many of these orders were actually paid.

        Used to close the storefront funnel. A browser reporting "checkout
        started" only means a button was pressed; whether money arrived is
        knowable solely from the orders table, so the last step of a funnel
        built from browser events is deliberately not taken from browser events.
        """
        if not order_ids:
            return 0
        return await self._scalar(
            select(func.count(distinct(OrderDB.id))).where(
                OrderDB.id.in_(order_ids),
                OrderDB.deleted_at.is_(None),
                OrderDB.status.in_(EARNED_STATUSES),
            )
        )

    async def _scalar(self, statement: Select) -> int:
        result = await self._session.execute(statement)
        return int(result.scalar_one_or_none() or 0)


def get_analytics_repository(session: AsyncSession) -> AnalyticsRepository:
    """Factory used by the router's dependency wiring."""
    return AnalyticsRepository(session)


def fill_series_gaps(
    buckets: dict[date, dict[str, int]],
    period: Period,
    interval: Interval,
) -> list[dict]:
    """
    Return one point per bucket in the window, zero-filled where there were none.

    A chart drawn from present-only buckets joins straight across a quiet week,
    which reads as steady trade rather than none. Absent days must be visible.
    """
    step = {
        Interval.DAY: timedelta(days=1),
        Interval.WEEK: timedelta(weeks=1),
    }.get(interval)

    points: list[dict] = []

    def zero(day: date) -> dict:
        return {
            "bucket": day,
            "gross_revenue": 0,
            "refunded_revenue": 0,
            "net_revenue": 0,
            "orders": 0,
            "units": 0,
        }

    def emit(day: date) -> None:
        found = buckets.get(day)
        if found is None:
            points.append(zero(day))
            return
        points.append(
            {
                "bucket": day,
                "gross_revenue": found["gross_revenue"],
                "refunded_revenue": found["refunded_revenue"],
                "net_revenue": found["gross_revenue"] - found["refunded_revenue"],
                "orders": found["orders"],
                "units": found["units"],
            }
        )

    start_day = period.start.date()
    last_day = (period.end - timedelta(seconds=1)).date()

    if interval is Interval.MONTH:
        # Months are not a fixed timedelta, so walk them by calendar.
        cursor = start_day.replace(day=1)
        while cursor <= last_day:
            emit(cursor)
            cursor = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
        return points

    if interval is Interval.WEEK:
        # date_trunc('week') anchors to Monday; align so keys match.
        cursor = start_day - timedelta(days=start_day.weekday())
    else:
        cursor = start_day

    while cursor <= last_day:
        emit(cursor)
        cursor = cursor + step

    return points
