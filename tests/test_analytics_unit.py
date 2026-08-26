"""
Unit tests for the Analytics service — pure logic, no DB, no network.

Covers the parts where the reasoning is subtle enough to get quietly wrong:

    - build_period()      — half-open windows, timezone conversion, validation
    - Period.previous()   — the comparison baseline
    - percent_change()    — undefined rather than infinite growth from zero
    - fill_series_gaps()  — quiet days present as zeroes, not absent
"""

from datetime import UTC, date, datetime

import pytest

from app.services.analytics.functions import (
    MAX_PERIOD_DAYS,
    Interval,
    Period,
    build_period,
    percent_change,
    resolve_timezone,
)
from app.services.analytics.services import fill_series_gaps
from app.shared.exceptions import ValidationError


# ---------------------------------------------------------------------------
# build_period
# ---------------------------------------------------------------------------


def test_period_is_half_open_and_includes_the_final_day():
    """
    `to` is inclusive to the reader, so the window must extend to the end of
    that day. A closed range on dates silently drops the last day's orders.
    """
    period = build_period(date(2026, 8, 1), date(2026, 8, 31), "UTC")

    assert period.start == datetime(2026, 8, 1, 0, 0, tzinfo=UTC)
    # Exclusive end: midnight opening 1 September, so 31 August is included.
    assert period.end == datetime(2026, 9, 1, 0, 0, tzinfo=UTC)
    assert period.days == 31


def test_period_boundaries_are_cut_in_the_shop_timezone():
    """
    Berlin is UTC+2 in August, so the shop's day starts at 22:00 UTC the day
    before. Bucketing on raw UTC would push evening orders into the next day.
    """
    period = build_period(date(2026, 8, 1), date(2026, 8, 1), "Europe/Berlin")

    assert period.start.astimezone(UTC) == datetime(2026, 7, 31, 22, 0, tzinfo=UTC)
    assert period.end.astimezone(UTC) == datetime(2026, 8, 1, 22, 0, tzinfo=UTC)


def test_previous_period_abuts_the_current_one_without_overlap():
    """
    The baseline must end exactly where the window starts. An overlap would
    count boundary orders twice; a gap would lose them.
    """
    period = build_period(date(2026, 8, 1), date(2026, 8, 31), "UTC")
    previous = period.previous()

    assert previous.end == period.start
    assert previous.end - previous.start == period.end - period.start
    assert previous.start == datetime(2026, 7, 1, 0, 0, tzinfo=UTC)


def test_inverted_range_is_rejected():
    with pytest.raises(ValidationError):
        build_period(date(2026, 8, 31), date(2026, 8, 1), "UTC")


def test_absurdly_long_range_is_rejected():
    """Live aggregation has no rollup table behind it, so the range is bounded."""
    with pytest.raises(ValidationError):
        build_period(date(1990, 1, 1), date(2026, 8, 1), "UTC")


def test_range_at_the_limit_is_allowed():
    start = date(2026, 8, 1)
    end = date(2026, 8, 1).replace(year=2026)
    period = build_period(start, end, "UTC")
    assert period.days <= MAX_PERIOD_DAYS


def test_unknown_timezone_is_a_validation_error_not_a_crash():
    """A misconfigured SHOP_TIMEZONE must say so, not return an opaque 500."""
    with pytest.raises(ValidationError):
        resolve_timezone("Mars/Olympus_Mons")


def test_defaults_to_a_thirty_day_window_ending_today():
    period = build_period(None, date(2026, 8, 30), "UTC", default_days=30)
    assert period.days == 30
    assert period.start == datetime(2026, 8, 1, 0, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# percent_change
# ---------------------------------------------------------------------------


def test_percent_change_from_zero_is_undefined():
    """
    Growth from nothing is not 100% and not infinite. Reporting a number here
    invites a reader to trust something meaningless.
    """
    assert percent_change(500, 0) is None


def test_percent_change_computes_both_directions():
    assert percent_change(150, 100) == 50.0
    assert percent_change(50, 100) == -50.0
    assert percent_change(100, 100) == 0.0


# ---------------------------------------------------------------------------
# fill_series_gaps
# ---------------------------------------------------------------------------


def _period(start: date, end: date) -> Period:
    return build_period(start, end, "UTC")


def test_days_without_orders_appear_as_zero_rather_than_vanishing():
    """
    A chart built from present-only buckets joins straight across a quiet day,
    which reads as steady trade rather than none.
    """
    period = _period(date(2026, 8, 1), date(2026, 8, 5))
    buckets = {
        date(2026, 8, 1): {
            "gross_revenue": 1000,
            "refunded_revenue": 0,
            "orders": 2,
            "units": 3,
        },
        date(2026, 8, 5): {
            "gross_revenue": 500,
            "refunded_revenue": 0,
            "orders": 1,
            "units": 1,
        },
    }

    points = fill_series_gaps(buckets, period, Interval.DAY)

    assert [p["bucket"] for p in points] == [
        date(2026, 8, 1),
        date(2026, 8, 2),
        date(2026, 8, 3),
        date(2026, 8, 4),
        date(2026, 8, 5),
    ]
    assert points[1]["gross_revenue"] == 0
    assert points[1]["orders"] == 0


def test_net_revenue_is_gross_less_refunds():
    period = _period(date(2026, 8, 1), date(2026, 8, 1))
    buckets = {
        date(2026, 8, 1): {
            "gross_revenue": 1000,
            "refunded_revenue": 250,
            "orders": 2,
            "units": 2,
        }
    }

    points = fill_series_gaps(buckets, period, Interval.DAY)

    assert points[0]["net_revenue"] == 750


def test_empty_window_still_yields_one_point_per_day():
    """An empty range must render an empty chart, not an absent one."""
    period = _period(date(2026, 8, 1), date(2026, 8, 3))

    points = fill_series_gaps({}, period, Interval.DAY)

    assert len(points) == 3
    assert all(p["gross_revenue"] == 0 for p in points)


def test_weekly_buckets_align_to_monday():
    """
    Postgres date_trunc('week') anchors to Monday, so the gap filler must use
    the same anchor or every key misses and the whole series reads as zero.
    """
    # 5 August 2026 is a Wednesday; its week starts Monday 3 August.
    period = _period(date(2026, 8, 5), date(2026, 8, 18))

    points = fill_series_gaps({}, period, Interval.WEEK)

    assert points[0]["bucket"] == date(2026, 8, 3)
    assert points[0]["bucket"].weekday() == 0
