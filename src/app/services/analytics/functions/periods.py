"""
Reporting Period Helpers

Turns the ``from``/``to`` query parameters into a validated window, and derives
the immediately preceding window of equal length so every figure can be shown
against a comparable baseline.

Buckets are cut in the shop's timezone rather than UTC. A German shop closing
at 23:00 local would otherwise see that evening's orders land on the following
day for half the year, which makes daily revenue look wrong in a way that is
hard to spot and easy to disbelieve.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from enum import Enum
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.shared.exceptions import ValidationError

# A window longer than this is refused. The aggregates are computed live rather
# than from a rollup table, so an unbounded range is a slow query waiting to
# happen; five years is far beyond any dashboard use and still a clear ceiling.
MAX_PERIOD_DAYS = 366 * 5


class Interval(str, Enum):
    """Bucket width for time series."""

    DAY = "day"
    WEEK = "week"
    MONTH = "month"


@dataclass(frozen=True)
class Period:
    """
    A half-open reporting window ``[start, end)`` in UTC.

    Half-open matters: an order placed at 23:59:59.999 on the last day belongs
    to the period, and one placed at 00:00:00 the next day does not. A closed
    range on dates either drops the final day or double-counts a boundary
    order when two periods are compared.
    """

    start: datetime
    end: datetime
    timezone: str

    @property
    def days(self) -> int:
        return max((self.end - self.start).days, 1)

    def previous(self) -> "Period":
        """The window of equal length ending where this one starts."""
        length = self.end - self.start
        return Period(
            start=self.start - length,
            end=self.start,
            timezone=self.timezone,
        )


def resolve_timezone(name: str) -> ZoneInfo:
    """
    Look up a timezone, failing with a useful message rather than a 500.

    A misconfigured SHOP_TIMEZONE should say so plainly — the alternative is
    every analytics endpoint returning an opaque internal error.
    """
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValidationError(
            message=f"Unknown shop timezone {name!r}",
            context={"timezone": name},
            original_exception=exc,
        ) from exc


def build_period(
    date_from: date | None,
    date_to: date | None,
    timezone_name: str,
    default_days: int = 30,
) -> Period:
    """
    Build a reporting window from inclusive calendar dates.

    Both bounds are interpreted in the shop's timezone and converted to UTC,
    because that is what the database stores. ``date_to`` is inclusive to the
    reader — asking for the 1st to the 31st should include the 31st — so the
    exclusive end is midnight at the start of the following day.

    Args:
        date_from: First day to include. Defaults to ``default_days`` before
            ``date_to``.
        date_to: Last day to include. Defaults to today in the shop timezone.
        timezone_name: IANA timezone the operator runs the shop in.
        default_days: Window length used when ``date_from`` is omitted.

    Returns:
        The resolved window, in UTC.

    Raises:
        ValidationError: If the timezone is unknown, the range is inverted, or
            the range exceeds MAX_PERIOD_DAYS.
    """
    tz = resolve_timezone(timezone_name)

    last_day = date_to or datetime.now(tz).date()
    first_day = date_from or (last_day - timedelta(days=default_days - 1))

    if first_day > last_day:
        raise ValidationError(
            message="The start of the period is after its end",
            context={"from": first_day.isoformat(), "to": last_day.isoformat()},
        )

    span = (last_day - first_day).days + 1
    if span > MAX_PERIOD_DAYS:
        raise ValidationError(
            message=(
                f"Requested period spans {span} days, "
                f"more than the {MAX_PERIOD_DAYS} day maximum"
            ),
            context={"days": span, "maximum": MAX_PERIOD_DAYS},
        )

    start = datetime.combine(first_day, time.min, tzinfo=tz)
    # Exclusive end: midnight opening the day after the last requested day.
    end = datetime.combine(last_day + timedelta(days=1), time.min, tzinfo=tz)

    return Period(start=start, end=end, timezone=timezone_name)


def percent_change(current: int | float, previous: int | float) -> float | None:
    """
    Percentage change from ``previous`` to ``current``.

    Returns None when there is no baseline to compare against. Growth from zero
    is not "infinite percent" or "100%" — it is undefined, and reporting a
    number there invites a reader to trust something meaningless.
    """
    if previous == 0:
        return None
    return round(((current - previous) / previous) * 100, 1)
