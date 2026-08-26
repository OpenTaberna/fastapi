"""
Integration tests for storefront analytics (S2).

Runs against the live stack with STOREFRONT_ANALYTICS_ENABLED=true:

    docker compose -f docker-compose.dev.yml up -d

Endpoints covered:
    POST /v1/analytics/events              — public ingest
    GET  /v1/admin/analytics/storefront    — the shopper funnel

Sessions are tagged with a per-run prefix and removed on teardown, so figures
are exact regardless of what else is in the database.
"""

import os
import subprocess
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import requests

from auth_helpers import admin_headers

_BASE = os.getenv("TEST_API_URL", "http://localhost:8000")
INGEST_URL = f"{_BASE}/v1/analytics/events"
FUNNEL_URL = f"{_BASE}/v1/admin/analytics/storefront"

_HEADERS = admin_headers()

RUN = uuid.uuid4().hex[:8]


def _psql(sql: str) -> str:
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


def _session(name: str) -> str:
    return f"it-{RUN}-{name}"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _post(events: list[dict]) -> requests.Response:
    return requests.post(INGEST_URL, json={"events": events})


@pytest.fixture(scope="module", autouse=True)
def enabled_or_skip():
    """These exercise collection, so a deployment with it off has nothing to test."""
    response = requests.get(FUNNEL_URL, headers=_HEADERS)
    response.raise_for_status()
    if not response.json()["enabled"]:
        pytest.skip("STOREFRONT_ANALYTICS_ENABLED is false on this deployment")
    yield
    _psql(f"DELETE FROM storefront_events WHERE session_id LIKE 'it-{RUN}-%';")


# ---------------------------------------------------------------------------
# The endpoint is public by design
# ---------------------------------------------------------------------------


def test_ingest_needs_no_authentication():
    """A shopper who has not signed in is exactly who this is measuring."""
    response = _post(
        [
            {
                "session_id": _session("anon"),
                "event_type": "page_view",
                "path": "/shop",
                "occurred_at": _now(),
            }
        ]
    )

    assert response.status_code == 202
    assert response.json()["accepted"] == 1


def test_reading_the_funnel_requires_admin():
    assert requests.get(FUNNEL_URL).status_code in (401, 403)


# ---------------------------------------------------------------------------
# What must never be stored
# ---------------------------------------------------------------------------


def test_the_table_has_no_column_that_could_identify_a_person():
    """
    The privacy promise is structural, not a policy someone remembers. If a
    column named for an address, an identity or a device ever appears, this
    fails before it can collect anything.
    """
    columns = set(
        _psql(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'storefront_events';"
        ).splitlines()
    )

    forbidden = {
        "ip",
        "ip_address",
        "remote_addr",
        "user_agent",
        "email",
        "customer_id",
        "keycloak_user_id",
        "user_id",
        "first_name",
        "last_name",
    }

    assert not (columns & forbidden), f"PII column present: {columns & forbidden}"


def test_a_query_string_carrying_an_email_is_not_stored():
    response = _post(
        [
            {
                "session_id": _session("qs"),
                "event_type": "page_view",
                "path": "/shop?email=leak@example.com&token=secret",
                "occurred_at": _now(),
            }
        ]
    )
    assert response.status_code == 202

    stored = _psql(
        f"SELECT path FROM storefront_events WHERE session_id = '{_session('qs')}';"
    )
    assert stored == "/shop"
    assert "leak@example.com" not in stored


def test_an_unknown_event_type_is_refused():
    response = _post(
        [
            {
                "session_id": _session("bad"),
                "event_type": "exfiltrate",
                "occurred_at": _now(),
            }
        ]
    )
    assert response.status_code == 422


def test_extra_fields_are_refused():
    response = _post(
        [
            {
                "session_id": _session("extra"),
                "event_type": "page_view",
                "occurred_at": _now(),
                "ip_address": "203.0.113.4",
            }
        ]
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Timestamps come from a client and are not trusted
# ---------------------------------------------------------------------------


def test_events_far_outside_the_clock_skew_window_are_discarded():
    """
    A browser clock can be wrong; it must not be able to write into a period an
    administrator has already reported on.
    """
    long_ago = (datetime.now(UTC) - timedelta(days=400)).isoformat()
    future = (datetime.now(UTC) + timedelta(days=400)).isoformat()

    response = _post(
        [
            {
                "session_id": _session("skew"),
                "event_type": "page_view",
                "occurred_at": long_ago,
            },
            {
                "session_id": _session("skew"),
                "event_type": "page_view",
                "occurred_at": future,
            },
            {
                "session_id": _session("skew"),
                "event_type": "page_view",
                "occurred_at": _now(),
            },
        ]
    )

    body = response.json()
    assert body["accepted"] == 1
    assert body["rejected"] == 2


def test_modest_clock_skew_is_tolerated():
    """Rejecting all skew would lose real events from slightly-wrong clocks."""
    recent = (datetime.now(UTC) - timedelta(hours=2)).isoformat()

    response = _post(
        [
            {
                "session_id": _session("tolerant"),
                "event_type": "page_view",
                "occurred_at": recent,
            }
        ]
    )

    assert response.json()["accepted"] == 1


# ---------------------------------------------------------------------------
# The funnel
# ---------------------------------------------------------------------------


def _steps(payload: dict) -> dict[str, int]:
    return {step["step"]: step["sessions"] for step in payload["steps"]}


def test_funnel_counts_sessions_not_events():
    """
    Ten product views from one shopper is one person considering a purchase.
    Counting events would make an indecisive browser look like a crowd.
    """
    session = _session("repeat")
    before = _steps(requests.get(FUNNEL_URL, headers=_HEADERS).json())

    _post(
        [
            {
                "session_id": session,
                "event_type": "product_view",
                "sku": "IT-SKU",
                "occurred_at": _now(),
            }
            for _ in range(5)
        ]
    )

    after = _steps(requests.get(FUNNEL_URL, headers=_HEADERS).json())

    assert after["viewed_product"] == before["viewed_product"] + 1


def test_add_to_cart_rate_is_reported_per_sku():
    sku = f"IT-RATE-{RUN}"
    _post(
        [
            {
                "session_id": _session("r1"),
                "event_type": "product_view",
                "sku": sku,
                "occurred_at": _now(),
            },
            {
                "session_id": _session("r2"),
                "event_type": "product_view",
                "sku": sku,
                "occurred_at": _now(),
            },
            {
                "session_id": _session("r1"),
                "event_type": "add_to_cart",
                "sku": sku,
                "occurred_at": _now(),
            },
        ]
    )

    payload = requests.get(FUNNEL_URL, headers=_HEADERS).json()
    row = next(p for p in payload["product_interest"] if p["sku"] == sku)

    assert row["sessions_viewed"] == 2
    assert row["sessions_added"] == 1
    assert row["add_to_cart_rate"] == 0.5


def test_the_paid_step_is_read_from_orders_not_from_the_browser():
    """
    A browser reporting "checkout started" only means a button was pressed. If
    the funnel took its word for the outcome, any client could inflate the
    conversion rate by claiming an order it never paid for.
    """
    fake_order = str(uuid.uuid4())

    _post(
        [
            {
                "session_id": _session("liar"),
                "event_type": "checkout_started",
                "order_id": fake_order,
                "occurred_at": _now(),
            }
        ]
    )

    payload = requests.get(FUNNEL_URL, headers=_HEADERS).json()
    steps = _steps(payload)

    # The claimed checkout is counted; the payment it did not make is not.
    assert steps["started_checkout"] >= 1
    assert steps["paid"] < steps["started_checkout"] or steps["paid"] == 0


def test_funnel_steps_are_ordered_and_carry_drop_off():
    payload = requests.get(FUNNEL_URL, headers=_HEADERS).json()

    assert [s["step"] for s in payload["steps"]] == [
        "sessions",
        "viewed_product",
        "added_to_cart",
        "started_checkout",
        "paid",
    ]
    assert payload["steps"][0]["drop_off_from_previous"] is None
    assert all(s["drop_off_from_previous"] is not None for s in payload["steps"][1:])
