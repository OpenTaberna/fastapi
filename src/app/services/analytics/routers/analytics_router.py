"""
Analytics Router

Admin-only commercial reporting:

    GET /admin/analytics/summary     — headline figures vs the previous period
    GET /admin/analytics/timeseries  — the same figures bucketed over time
    GET /admin/analytics/products    — per-SKU performance and dead stock
    GET /admin/analytics/funnel      — where orders stop

Every endpoint takes the same optional ``from``/``to`` calendar dates,
interpreted in the shop's timezone and defaulting to the last 30 days.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.config import get_settings
from app.shared.database.session import get_session_dependency
from app.shared.logger import get_logger

from ..dependencies import require_admin
from ..functions import Interval, Period, build_period, percent_change
from ..models import (
    AnalyticsFunnelResponse,
    AnalyticsStorefrontResponse,
    AnalyticsProductsResponse,
    AnalyticsSummaryResponse,
    AnalyticsTimeseriesResponse,
    Change,
    CurrencySeries,
    CurrencyTotals,
    CurrencyTotalsPrevious,
    FunnelStep,
    NeverSoldItem,
    PathViews,
    PeriodInfo,
    ProductInterest,
    ProductPerformance,
    SeriesPoint,
    StorefrontStep,
)
from ..responses import (
    FUNNEL_RESPONSES,
    PRODUCTS_RESPONSES,
    SUMMARY_RESPONSES,
    TIMESERIES_RESPONSES,
)
from app.services.storefront_analytics.services import StorefrontEventRepository

from ..services import AnalyticsRepository, fill_series_gaps

logger = get_logger(__name__)

router = APIRouter()

# Cap on rows returned by the products endpoint. A catalogue can be large and
# this is a dashboard table, not an export.
_MAX_PRODUCT_ROWS = 200


def _period_info(period: Period) -> PeriodInfo:
    return PeriodInfo(
        start=period.start,
        end=period.end,
        timezone=period.timezone,
        days=period.days,
    )


def _average(total: int, count: int) -> int:
    return round(total / count) if count else 0


async def _resolve_period(
    date_from: date | None,
    date_to: date | None,
) -> Period:
    settings = get_settings()
    return build_period(
        date_from=date_from,
        date_to=date_to,
        timezone_name=settings.shop_timezone,
    )


# ---------------------------------------------------------------------------
# GET /admin/analytics/summary
# ---------------------------------------------------------------------------


@router.get(
    "/summary",
    response_model=AnalyticsSummaryResponse,
    summary="Commercial summary (admin)",
    description=(
        "Revenue, refunds, order count, units and average order value for the "
        "requested window, each compared against the immediately preceding "
        "window of equal length.\n\n"
        "Figures are grouped by currency because `orders.currency` permits more "
        "than one and a cross-currency total would be meaningless. Revenue is "
        "gross (paid, ready to ship, shipped) less refunds; refunds are "
        "whole-order only, as partial refunds are not modelled."
    ),
    responses=SUMMARY_RESPONSES,
    dependencies=[Depends(require_admin)],
)
async def get_summary(
    date_from: date | None = Query(
        None, alias="from", description="First day, inclusive"
    ),
    date_to: date | None = Query(None, alias="to", description="Last day, inclusive"),
    session: AsyncSession = Depends(get_session_dependency),
) -> AnalyticsSummaryResponse:
    period = await _resolve_period(date_from, date_to)
    previous = period.previous()
    repository = AnalyticsRepository(session)

    current_totals = await repository.order_totals_by_currency(period)
    current_units = await repository.units_by_currency(period)
    previous_totals = await repository.order_totals_by_currency(previous)
    previous_units = await repository.units_by_currency(previous)

    currencies: list[CurrencyTotals] = []
    # A currency present only in the prior window still deserves a row — its
    # disappearance is exactly the kind of thing a dashboard should show.
    for currency in sorted(set(current_totals) | set(previous_totals)):
        now = current_totals.get(
            currency, {"gross_revenue": 0, "refunded_revenue": 0, "orders": 0}
        )
        then = previous_totals.get(
            currency, {"gross_revenue": 0, "refunded_revenue": 0, "orders": 0}
        )

        now_units = current_units.get(currency, 0)
        then_units = previous_units.get(currency, 0)

        now_net = now["gross_revenue"] - now["refunded_revenue"]
        then_net = then["gross_revenue"] - then["refunded_revenue"]
        now_aov = _average(now["gross_revenue"], now["orders"])
        then_aov = _average(then["gross_revenue"], then["orders"])

        currencies.append(
            CurrencyTotals(
                currency=currency,
                gross_revenue=now["gross_revenue"],
                refunded_revenue=now["refunded_revenue"],
                net_revenue=now_net,
                orders=now["orders"],
                units=now_units,
                average_order_value=now_aov,
                previous=CurrencyTotalsPrevious(
                    gross_revenue=then["gross_revenue"],
                    refunded_revenue=then["refunded_revenue"],
                    net_revenue=then_net,
                    orders=then["orders"],
                    units=then_units,
                    average_order_value=then_aov,
                ),
                change=Change(
                    net_revenue_pct=percent_change(now_net, then_net),
                    gross_revenue_pct=percent_change(
                        now["gross_revenue"], then["gross_revenue"]
                    ),
                    orders_pct=percent_change(now["orders"], then["orders"]),
                    units_pct=percent_change(now_units, then_units),
                    average_order_value_pct=percent_change(now_aov, then_aov),
                ),
            )
        )

    return AnalyticsSummaryResponse(
        success=True,
        message="Analytics summary retrieved successfully",
        period=_period_info(period),
        previous_period=_period_info(previous),
        currencies=currencies,
    )


# ---------------------------------------------------------------------------
# GET /admin/analytics/timeseries
# ---------------------------------------------------------------------------


@router.get(
    "/timeseries",
    response_model=AnalyticsTimeseriesResponse,
    summary="Revenue and volume over time (admin)",
    description=(
        "The summary figures bucketed by day, week or month, in the shop's "
        "timezone.\n\n"
        "Buckets with no orders are returned with zeroes rather than omitted, so "
        "a chart shows a real trough instead of joining across the gap."
    ),
    responses=TIMESERIES_RESPONSES,
    dependencies=[Depends(require_admin)],
)
async def get_timeseries(
    date_from: date | None = Query(
        None, alias="from", description="First day, inclusive"
    ),
    date_to: date | None = Query(None, alias="to", description="Last day, inclusive"),
    interval: Interval = Query(Interval.DAY, description="Bucket width"),
    session: AsyncSession = Depends(get_session_dependency),
) -> AnalyticsTimeseriesResponse:
    period = await _resolve_period(date_from, date_to)
    repository = AnalyticsRepository(session)

    raw = await repository.series_by_currency(period, interval)

    series = [
        CurrencySeries(
            currency=currency,
            points=[
                SeriesPoint(**point)
                for point in fill_series_gaps(buckets, period, interval)
            ],
        )
        for currency, buckets in sorted(raw.items())
    ]

    return AnalyticsTimeseriesResponse(
        success=True,
        message="Analytics time series retrieved successfully",
        period=_period_info(period),
        interval=interval.value,
        series=series,
    )


# ---------------------------------------------------------------------------
# GET /admin/analytics/products
# ---------------------------------------------------------------------------


@router.get(
    "/products",
    response_model=AnalyticsProductsResponse,
    summary="Product performance (admin)",
    description=(
        "Units, revenue, order count and return rate per SKU, plus active "
        "catalogue items that sold nothing in the window.\n\n"
        "Revenue here sums line values (quantity x unit price) and need not "
        "equal the order totals in the summary, which may carry shipping or "
        "adjustments belonging to no line. Return rate attributes an order's "
        "return to every SKU on that order, so it is an upper bound per SKU."
    ),
    responses=PRODUCTS_RESPONSES,
    dependencies=[Depends(require_admin)],
)
async def get_products(
    date_from: date | None = Query(
        None, alias="from", description="First day, inclusive"
    ),
    date_to: date | None = Query(None, alias="to", description="Last day, inclusive"),
    sort: str = Query("revenue", pattern="^(revenue|units|orders|return_rate)$"),
    limit: int = Query(20, ge=1, le=_MAX_PRODUCT_ROWS),
    session: AsyncSession = Depends(get_session_dependency),
) -> AnalyticsProductsResponse:
    period = await _resolve_period(date_from, date_to)
    repository = AnalyticsRepository(session)

    rows = await repository.product_performance(period)
    returns = await repository.returns_by_sku(period)
    names = await repository.item_names([row["sku"] for row in rows])

    products: list[ProductPerformance] = []
    for row in rows:
        orders = row["orders"]
        with_return = returns.get(row["sku"], 0)
        products.append(
            ProductPerformance(
                sku=row["sku"],
                name=names.get(row["sku"]),
                currency=row["currency"],
                units_sold=row["units_sold"],
                gross_revenue=row["gross_revenue"],
                orders=orders,
                orders_with_return=with_return,
                return_rate=round(with_return / orders, 4) if orders else None,
            )
        )

    sort_keys = {
        "revenue": lambda p: p.gross_revenue,
        "units": lambda p: p.units_sold,
        "orders": lambda p: p.orders,
        "return_rate": lambda p: p.return_rate or 0.0,
    }
    products.sort(key=sort_keys[sort], reverse=True)

    never_sold = await repository.never_sold([row["sku"] for row in rows])

    return AnalyticsProductsResponse(
        success=True,
        message="Product performance retrieved successfully",
        period=_period_info(period),
        sort=sort,
        products=products[:limit],
        never_sold=[NeverSoldItem(**item) for item in never_sold],
    )


# ---------------------------------------------------------------------------
# GET /admin/analytics/funnel
# ---------------------------------------------------------------------------


@router.get(
    "/funnel",
    response_model=AnalyticsFunnelResponse,
    summary="Order funnel (admin)",
    description=(
        "Where orders stop, from creation through checkout and payment to "
        "handover.\n\n"
        "This is an **order** funnel, not a visitor funnel: it starts at order "
        "creation and cannot see shoppers who browsed without creating one. "
        "Checkout is read from the payments table rather than order status, "
        "because status records only where an order is now and cannot "
        "distinguish a cancelled checkout from one that never happened."
    ),
    responses=FUNNEL_RESPONSES,
    dependencies=[Depends(require_admin)],
)
async def get_funnel(
    date_from: date | None = Query(
        None, alias="from", description="First day, inclusive"
    ),
    date_to: date | None = Query(None, alias="to", description="Last day, inclusive"),
    session: AsyncSession = Depends(get_session_dependency),
) -> AnalyticsFunnelResponse:
    period = await _resolve_period(date_from, date_to)
    repository = AnalyticsRepository(session)

    counts = await repository.funnel_counts(period)
    created = counts["created"]

    definitions = [
        ("created", "Order created"),
        ("checkout_started", "Checkout started"),
        ("paid", "Payment confirmed"),
        ("shipped", "Handed to carrier"),
    ]

    steps: list[FunnelStep] = []
    previous_count: int | None = None
    for key, label in definitions:
        count = counts[key]
        steps.append(
            FunnelStep(
                step=key,
                label=label,
                orders=count,
                conversion_from_start=(round(count / created, 4) if created else None),
                drop_off_from_previous=(
                    None if previous_count is None else max(previous_count - count, 0)
                ),
            )
        )
        previous_count = count

    return AnalyticsFunnelResponse(
        success=True,
        message="Order funnel retrieved successfully",
        period=_period_info(period),
        steps=steps,
        never_checked_out=counts["never_checked_out"],
        payment_failed=counts["payment_failed"],
        payment_unresolved=counts["payment_unresolved"],
        cancelled=counts["cancelled"],
    )


# ---------------------------------------------------------------------------
# GET /admin/analytics/storefront
# ---------------------------------------------------------------------------


@router.get(
    "/storefront",
    response_model=AnalyticsStorefrontResponse,
    summary="Shopper funnel (admin)",
    description=(
        "The journey before an order exists: sessions, product views, carts, "
        "checkouts and paid orders.\n\n"
        "Sessions are counted distinctly, so ten product views by one shopper "
        "count once.\n\n"
        "The pre-order steps come from what browsers reported and are a **floor**, "
        "not an exact count — blocked scripts and closed tabs lose events. The "
        "paid step is read from the orders table and is exact. Returns "
        "`enabled: false` with zeroes when the deployment is not collecting."
    ),
    responses=FUNNEL_RESPONSES,
    dependencies=[Depends(require_admin)],
)
async def get_storefront_funnel(
    date_from: date | None = Query(
        None, alias="from", description="First day, inclusive"
    ),
    date_to: date | None = Query(None, alias="to", description="Last day, inclusive"),
    limit: int = Query(
        10,
        ge=1,
        le=_MAX_PRODUCT_ROWS,
        description="Rows returned in top_paths and product_interest",
    ),
    session: AsyncSession = Depends(get_session_dependency),
) -> AnalyticsStorefrontResponse:
    period = await _resolve_period(date_from, date_to)
    settings = get_settings()

    events = StorefrontEventRepository(session)
    counts = await events.browse_funnel(period.start, period.end)
    page_views = await events.page_views(period.start, period.end)

    # The final step is not taken from the browser's word for it. A reported
    # checkout says the shopper pressed the button; only the orders table knows
    # whether money arrived.
    checkout_orders = await events.checkout_order_ids(period.start, period.end)
    paid = await AnalyticsRepository(session).count_paid_orders(checkout_orders)

    definitions = [
        ("sessions", "Visited the shop", counts["sessions"]),
        ("viewed_product", "Viewed a product", counts["viewed_product"]),
        ("added_to_cart", "Added to cart", counts["added_to_cart"]),
        ("started_checkout", "Started checkout", counts["started_checkout"]),
        ("paid", "Paid", paid),
    ]

    total = counts["sessions"]
    steps: list[StorefrontStep] = []
    previous: int | None = None
    for key, label, value in definitions:
        steps.append(
            StorefrontStep(
                step=key,
                label=label,
                sessions=value,
                conversion_from_start=round(value / total, 4) if total else None,
                drop_off_from_previous=(
                    None if previous is None else max(previous - value, 0)
                ),
            )
        )
        previous = value

    interest = await events.product_interest(period.start, period.end, limit=limit)
    names = await AnalyticsRepository(session).item_names(
        [row["sku"] for row in interest]
    )

    return AnalyticsStorefrontResponse(
        success=True,
        message="Storefront funnel retrieved successfully",
        period=_period_info(period),
        enabled=settings.storefront_analytics_enabled,
        page_views=page_views,
        steps=steps,
        top_paths=[
            PathViews(**row)
            for row in await events.top_paths(period.start, period.end, limit=limit)
        ],
        product_interest=[
            ProductInterest(**row, name=names.get(row["sku"])) for row in interest
        ],
    )
