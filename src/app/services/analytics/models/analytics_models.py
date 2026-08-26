"""
Analytics Pydantic Schemas

Response shapes for the admin analytics endpoints.

Two conventions run through all of them:

**Money is minor units.** Every amount is an integer in the currency's smallest
unit, matching ``orders.total_amount``. No floats touch money anywhere in this
service.

**Money is grouped by currency.** ``orders.currency`` permits more than one, and
a total summed across currencies is not wrong by a little — it is meaningless.
Every money-bearing response is therefore a list keyed by currency rather than a
single figure, which collapses to one entry for the common single-currency shop.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.shared.responses import BaseResponse


# ============================================================================
# Shared
# ============================================================================


class PeriodInfo(BaseModel):
    """The window a figure was computed over."""

    model_config = ConfigDict(from_attributes=True)

    start: datetime = Field(description="Start of the window, inclusive (UTC)")
    end: datetime = Field(description="End of the window, exclusive (UTC)")
    timezone: str = Field(description="Timezone the window's days were cut in")
    days: int = Field(description="Length of the window in days")


class Change(BaseModel):
    """
    Movement against the previous equivalent period.

    Every field is nullable: percentage change from a baseline of zero is
    undefined, and reporting a number there would invite trust in nothing.
    """

    net_revenue_pct: float | None = Field(default=None)
    gross_revenue_pct: float | None = Field(default=None)
    orders_pct: float | None = Field(default=None)
    units_pct: float | None = Field(default=None)
    average_order_value_pct: float | None = Field(default=None)


# ============================================================================
# Summary
# ============================================================================


class CurrencyTotals(BaseModel):
    """Headline figures for one currency."""

    model_config = ConfigDict(from_attributes=True)

    currency: str = Field(description="ISO 4217 code")

    gross_revenue: int = Field(
        description="Money taken: orders paid, ready to ship or shipped"
    )
    refunded_revenue: int = Field(
        description="Value of orders refunded in full. Partial refunds are not modelled"
    )
    net_revenue: int = Field(description="Gross revenue less refunds")

    orders: int = Field(description="Orders that produced revenue")
    units: int = Field(description="Units across those orders")
    average_order_value: int = Field(
        description="Gross revenue divided by revenue-producing orders"
    )

    previous: "CurrencyTotalsPrevious | None" = Field(
        default=None, description="The same figures for the preceding window"
    )
    change: Change | None = Field(
        default=None, description="Movement against the preceding window"
    )


class CurrencyTotalsPrevious(BaseModel):
    """Prior-period figures, without their own comparison."""

    gross_revenue: int
    refunded_revenue: int
    net_revenue: int
    orders: int
    units: int
    average_order_value: int


class AnalyticsSummaryResponse(BaseResponse):
    """Headline commercial figures, one entry per currency."""

    period: PeriodInfo
    previous_period: PeriodInfo
    currencies: list[CurrencyTotals] = Field(default_factory=list)


# ============================================================================
# Time series
# ============================================================================


class SeriesPoint(BaseModel):
    """One bucket of a time series."""

    bucket: date = Field(description="First day of the bucket, in shop timezone")
    gross_revenue: int
    refunded_revenue: int
    net_revenue: int
    orders: int
    units: int


class CurrencySeries(BaseModel):
    """A complete series for one currency, gap-filled."""

    currency: str
    points: list[SeriesPoint] = Field(default_factory=list)


class AnalyticsTimeseriesResponse(BaseResponse):
    """
    Revenue and volume over time.

    Buckets with no orders are present with zeroes rather than absent, so a
    chart shows a real trough instead of silently joining across the gap.
    """

    period: PeriodInfo
    interval: str
    series: list[CurrencySeries] = Field(default_factory=list)


# ============================================================================
# Products
# ============================================================================


class ProductPerformance(BaseModel):
    """How one SKU sold over the window."""

    sku: str
    name: str | None = Field(
        default=None, description="Catalogue name, absent if the item was deleted"
    )
    currency: str

    units_sold: int
    gross_revenue: int
    orders: int = Field(description="Revenue-producing orders containing this SKU")

    orders_with_return: int = Field(
        description=(
            "Orders containing this SKU where a return was raised. Returns are "
            "recorded per order, not per line, so this attributes a return to "
            "every SKU on the order — an upper bound, not a per-item rate"
        )
    )
    return_rate: float | None = Field(
        default=None,
        description="orders_with_return divided by orders, or null when unsold",
    )


class NeverSoldItem(BaseModel):
    """An active catalogue item with no sales in the window."""

    sku: str
    name: str
    status: str
    on_hand: int | None = Field(
        default=None, description="Units in stock, absent if untracked"
    )


class AnalyticsProductsResponse(BaseResponse):
    """Per-SKU performance, plus catalogue items that did not sell."""

    period: PeriodInfo
    sort: str
    products: list[ProductPerformance] = Field(default_factory=list)
    never_sold: list[NeverSoldItem] = Field(default_factory=list)


# ============================================================================
# Funnel
# ============================================================================


class FunnelStep(BaseModel):
    """One stage of the order lifecycle."""

    step: str
    label: str
    orders: int
    conversion_from_start: float | None = Field(
        default=None, description="Share of orders created that reached this step"
    )
    drop_off_from_previous: int | None = Field(
        default=None, description="Orders lost between the previous step and this one"
    )


class AnalyticsFunnelResponse(BaseResponse):
    """
    Where orders stop.

    This is an **order** funnel, not a visitor funnel. It begins at order
    creation, so it cannot see shoppers who browsed and never started one.
    Visitor conversion needs session data the API does not collect.

    Checkout is read from the payments table rather than from order status:
    a payment row is written when checkout starts, and unlike ``orders.status``
    — which only records where an order is now — it still exists after the
    order moves on or is cancelled.
    """

    period: PeriodInfo
    steps: list[FunnelStep] = Field(default_factory=list)

    never_checked_out: int = Field(
        description="Orders created that never started checkout"
    )
    payment_failed: int = Field(description="Checkouts whose payment failed")
    payment_unresolved: int = Field(
        description="Checkouts still pending: abandoned, or awaiting a webhook"
    )
    cancelled: int = Field(description="Orders cancelled in the window")


CurrencyTotals.model_rebuild()
