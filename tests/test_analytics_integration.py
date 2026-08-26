"""
Integration tests for the Analytics API (S1).

Runs against the live stack:

    docker compose -f docker-compose.dev.yml up -d

Endpoints covered:
    GET /v1/admin/analytics/summary
    GET /v1/admin/analytics/timeseries
    GET /v1/admin/analytics/products
    GET /v1/admin/analytics/funnel

The fixture seeds a deterministic dataset inside **March 2025**, a window no
other fixture or seed touches, and every assertion queries exactly that window.
Figures are therefore exact regardless of whatever else is in the database —
which matters, because the dev database accumulates orders from other suites.

The dataset is built to exercise the things that are quietly easy to get wrong:

    - two currencies, which must never be summed together
    - a soft-deleted order, which must vanish from every figure
    - a draft and a cancelled order, which are not revenue
    - a refunded order, which reduces net but not gross
    - a multi-line order, which must not multiply its own value by its line count
    - an order at 23:30 UTC, which belongs to the *next* day in Berlin
"""

import os
import subprocess
import uuid

import pytest
import requests

from auth_helpers import admin_headers

_BASE = os.getenv("TEST_API_URL", "http://localhost:8000")
ANALYTICS_URL = f"{_BASE}/v1/admin/analytics"

_HEADERS = admin_headers()

# The isolated reporting window. Chosen far from any other fixture's data.
WINDOW = {"from": "2025-03-01", "to": "2025-03-31"}

# Marks every row this module creates, so teardown can remove exactly those.
TAG = "analytics-it"


def _psql(sql: str) -> str:
    """Run SQL inside the Postgres container and return stdout."""
    result = subprocess.run(
        [
            "docker",
            "exec",
            "opentaberna-db",
            "psql",
            "-U",
            "opentaberna",
            "-d",
            "opentaberna",
            "-t",
            "-A",
            "-c",
            sql,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _get(path: str, **params) -> dict:
    response = requests.get(f"{ANALYTICS_URL}/{path}", headers=_HEADERS, params=params)
    response.raise_for_status()
    return response.json()


def _currency(payload: dict, code: str) -> dict | None:
    for entry in payload["currencies"]:
        if entry["currency"] == code:
            return entry
    return None


@pytest.fixture(scope="module", autouse=True)
def seeded_dataset():
    """Insert the fixture dataset, yield, then remove exactly what was inserted."""
    customer = uuid.uuid4()
    orders = {name: uuid.uuid4() for name in "ABCDEFGH"}
    suffix = uuid.uuid4().hex[:8]

    def order_row(
        key: str,
        status: str,
        amount: int,
        currency: str,
        when: str,
        deleted: str = "NULL",
    ) -> str:
        return (
            f"('{orders[key]}', '{customer}', '{status}', {amount}, '{currency}', "
            f"'{when}'::timestamptz, '{when}'::timestamptz, {deleted})"
        )

    _psql(
        f"""
        INSERT INTO customers (id, keycloak_user_id, email, first_name, last_name,
                               created_at, updated_at)
        VALUES ('{customer}', '{TAG}-{suffix}', '{TAG}-{suffix}@example.test',
                'Analytics', 'Fixture', now(), now());

        INSERT INTO orders (id, customer_id, status, total_amount, currency,
                            created_at, updated_at, deleted_at)
        VALUES
          {order_row("A", "paid", 10000, "EUR", "2025-03-05T12:00:00Z")},
          {order_row("B", "shipped", 5000, "EUR", "2025-03-14T12:00:00Z")},
          {order_row("C", "refunded", 3000, "EUR", "2025-03-12T12:00:00Z")},
          {order_row("D", "draft", 9999, "EUR", "2025-03-15T12:00:00Z")},
          {order_row("E", "paid", 7000, "USD", "2025-03-06T12:00:00Z")},
          {order_row("F", "paid", 4000, "EUR", "2025-03-20T12:00:00Z", "now()")},
          {order_row("G", "cancelled", 2000, "EUR", "2025-03-22T12:00:00Z")},
          {order_row("H", "paid", 1000, "EUR", "2025-03-09T23:30:00Z")};

        INSERT INTO order_items (id, order_id, sku, quantity, unit_price,
                                 created_at, updated_at)
        VALUES
          ('{uuid.uuid4()}', '{orders["A"]}', '{TAG}-SKU-A', 2, 2500, now(), now()),
          ('{uuid.uuid4()}', '{orders["A"]}', '{TAG}-SKU-B', 1, 5000, now(), now()),
          ('{uuid.uuid4()}', '{orders["B"]}', '{TAG}-SKU-A', 1, 5000, now(), now()),
          ('{uuid.uuid4()}', '{orders["E"]}', '{TAG}-SKU-C', 1, 7000, now(), now()),
          ('{uuid.uuid4()}', '{orders["F"]}', '{TAG}-SKU-A', 9, 9999, now(), now()),
          ('{uuid.uuid4()}', '{orders["D"]}', '{TAG}-SKU-A', 9, 9999, now(), now());

        INSERT INTO payments (id, order_id, provider, provider_reference, amount,
                              currency, status, created_at, updated_at)
        VALUES
          ('{uuid.uuid4()}', '{orders["A"]}', 'stripe', '{TAG}-{suffix}-a', 10000,
           'EUR', 'succeeded', now(), now()),
          ('{uuid.uuid4()}', '{orders["B"]}', 'stripe', '{TAG}-{suffix}-b',  5000,
           'EUR', 'succeeded', now(), now()),
          ('{uuid.uuid4()}', '{orders["D"]}', 'stripe', '{TAG}-{suffix}-d',  9999,
           'EUR', 'pending',   now(), now()),
          ('{uuid.uuid4()}', '{orders["G"]}', 'stripe', '{TAG}-{suffix}-g',  2000,
           'EUR', 'failed',    now(), now());

        INSERT INTO shipments (id, order_id, carrier, status, created_at, updated_at)
        VALUES ('{uuid.uuid4()}', '{orders["B"]}', 'dhl', 'handed_over', now(), now());

        INSERT INTO returns (id, order_id, customer_id, status, reason,
                             created_at, updated_at)
        VALUES ('{uuid.uuid4()}', '{orders["A"]}', '{customer}', 'requested',
                'fixture', now(), now());
        """
    )

    yield

    # customers cascades to orders, which cascades to order_items; payments,
    # shipments and returns are RESTRICT so they go first.
    ids = ", ".join(f"'{value}'" for value in orders.values())
    _psql(
        f"""
        DELETE FROM returns   WHERE order_id IN ({ids});
        DELETE FROM shipments WHERE order_id IN ({ids});
        DELETE FROM payments  WHERE order_id IN ({ids});
        DELETE FROM orders    WHERE id IN ({ids});
        DELETE FROM customers WHERE id = '{customer}';
        """
    )


# ---------------------------------------------------------------------------
# Authorization
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("endpoint", ["summary", "timeseries", "products", "funnel"])
def test_analytics_requires_admin(endpoint):
    """Commercial figures are admin-only on every endpoint, without exception."""
    response = requests.get(f"{ANALYTICS_URL}/{endpoint}")
    assert response.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


def test_summary_reports_revenue_per_currency_without_mixing_them():
    """
    EUR and USD are reported separately. Summing them would produce a number
    that means nothing, so the schema makes it impossible.
    """
    payload = _get("summary", **WINDOW)

    eur = _currency(payload, "EUR")
    usd = _currency(payload, "USD")

    assert eur is not None and usd is not None

    # A(10000) + B(5000) + H(1000). C is refunded, D draft, G cancelled,
    # F soft-deleted — none of them are gross revenue.
    assert eur["gross_revenue"] == 16000
    assert eur["refunded_revenue"] == 3000
    assert eur["net_revenue"] == 13000
    assert eur["orders"] == 3

    assert usd["gross_revenue"] == 7000
    assert usd["orders"] == 1


def test_soft_deleted_orders_are_excluded_from_every_figure():
    """
    Order F is paid, worth 4000, and carries nine units — and is soft-deleted.
    None of it may reach a total.
    """
    payload = _get("summary", **WINDOW)
    eur = _currency(payload, "EUR")

    assert eur["gross_revenue"] == 16000, "a soft-deleted order leaked into revenue"
    assert eur["units"] == 4, "a soft-deleted order's units leaked into the count"


def test_multi_line_orders_are_not_counted_once_per_line():
    """
    Order A has two lines. Joining orders to items and summing total_amount
    would count its 10000 twice. Order money and line money are queried apart
    precisely to stop that.
    """
    payload = _get("summary", **WINDOW)
    eur = _currency(payload, "EUR")

    assert eur["gross_revenue"] == 16000
    # A contributes 3 units across 2 lines, B contributes 1, H none.
    assert eur["units"] == 4


def test_average_order_value_divides_by_revenue_producing_orders_only():
    payload = _get("summary", **WINDOW)
    eur = _currency(payload, "EUR")

    assert eur["average_order_value"] == round(16000 / 3)


def test_previous_period_abuts_the_requested_one():
    payload = _get("summary", **WINDOW)

    assert payload["previous_period"]["end"] == payload["period"]["start"]
    assert payload["previous_period"]["days"] == payload["period"]["days"]


def test_percentage_change_is_null_when_there_is_no_baseline():
    """February 2025 is empty, so growth into March is undefined, not infinite."""
    payload = _get("summary", **WINDOW)
    eur = _currency(payload, "EUR")

    assert eur["previous"]["gross_revenue"] == 0
    assert eur["change"]["gross_revenue_pct"] is None


def test_inverted_period_is_rejected():
    response = requests.get(
        f"{ANALYTICS_URL}/summary",
        headers=_HEADERS,
        params={"from": "2025-03-31", "to": "2025-03-01"},
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Time series
# ---------------------------------------------------------------------------


def test_series_buckets_days_in_the_shop_timezone_not_utc():
    """
    Order H is at 23:30 UTC on 9 March, which is 00:30 on the 10th in Berlin.
    A UTC bucket would file it under the 9th and show the operator a day's
    takings on the wrong day.
    """
    payload = _get("timeseries", **WINDOW, interval="day")
    eur = next(s for s in payload["series"] if s["currency"] == "EUR")
    by_day = {point["bucket"]: point for point in eur["points"]}

    # Nothing else is seeded on either day, so this isolates the boundary.
    assert by_day["2025-03-10"]["gross_revenue"] == 1000
    assert by_day["2025-03-09"]["gross_revenue"] == 0


def test_quiet_days_are_present_as_zero_rather_than_missing():
    """A chart must show a trough on a day with no orders, not skip over it."""
    payload = _get("timeseries", **WINDOW, interval="day")
    eur = next(s for s in payload["series"] if s["currency"] == "EUR")

    assert len(eur["points"]) == 31, "March has 31 days; every one needs a point"

    by_day = {point["bucket"]: point for point in eur["points"]}
    assert by_day["2025-03-01"]["orders"] == 0
    assert by_day["2025-03-05"]["gross_revenue"] == 10000


def test_series_net_revenue_subtracts_refunds_in_the_right_bucket():
    payload = _get("timeseries", **WINDOW, interval="day")
    eur = next(s for s in payload["series"] if s["currency"] == "EUR")
    by_day = {point["bucket"]: point for point in eur["points"]}

    assert by_day["2025-03-12"]["refunded_revenue"] == 3000
    assert by_day["2025-03-12"]["net_revenue"] == -3000


# ---------------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------------


def test_product_performance_aggregates_a_sku_across_orders():
    payload = _get("products", **WINDOW, limit=200)
    by_sku = {p["sku"]: p for p in payload["products"]}

    sku_a = by_sku[f"{TAG}-SKU-A"]
    # 2 units at 2500 on order A, 1 at 5000 on order B. Order F's 9 units are
    # soft-deleted and order D's are a draft.
    assert sku_a["units_sold"] == 3
    assert sku_a["gross_revenue"] == 10000
    assert sku_a["orders"] == 2


def test_return_rate_is_reported_per_sku_on_the_returned_order():
    """
    Returns are recorded per order, so a return on the two-line order A counts
    against both its SKUs. That is an upper bound, and the schema says so.
    """
    payload = _get("products", **WINDOW, limit=200)
    by_sku = {p["sku"]: p for p in payload["products"]}

    assert by_sku[f"{TAG}-SKU-A"]["orders_with_return"] == 1
    assert by_sku[f"{TAG}-SKU-B"]["orders_with_return"] == 1
    assert by_sku[f"{TAG}-SKU-B"]["return_rate"] == 1.0


def test_products_can_be_sorted_by_units():
    payload = _get("products", **WINDOW, sort="units", limit=200)
    units = [p["units_sold"] for p in payload["products"]]
    assert units == sorted(units, reverse=True)


# ---------------------------------------------------------------------------
# Funnel
# ---------------------------------------------------------------------------


def _step(payload: dict, name: str) -> dict:
    return next(s for s in payload["steps"] if s["step"] == name)


def test_funnel_counts_checkout_from_payments_not_order_status():
    """
    Orders A, B, D and G have payment rows; C, E and H do not. Order status
    could not tell them apart — G is cancelled and D is a draft, yet both
    reached checkout.
    """
    payload = _get("funnel", **WINDOW)

    assert _step(payload, "created")["orders"] == 7  # F is soft-deleted
    assert _step(payload, "checkout_started")["orders"] == 4
    assert _step(payload, "paid")["orders"] == 2
    assert _step(payload, "shipped")["orders"] == 1


def test_funnel_separates_failed_payments_from_unresolved_ones():
    """
    A payment that failed and one still pending are different problems: one is
    a lost sale, the other may still complete.
    """
    payload = _get("funnel", **WINDOW)

    assert payload["payment_failed"] == 1  # order G
    assert payload["payment_unresolved"] == 1  # order D, still pending
    assert payload["never_checked_out"] == 3  # C, E, H
    assert payload["cancelled"] == 1  # order G


def test_funnel_drop_off_is_the_loss_from_the_previous_step():
    payload = _get("funnel", **WINDOW)

    assert _step(payload, "created")["drop_off_from_previous"] is None
    assert _step(payload, "checkout_started")["drop_off_from_previous"] == 3
    assert _step(payload, "paid")["drop_off_from_previous"] == 2
