"""
Integration tests for frontend error reporting (S4).

Runs against the live stack with FRONTEND_ERRORS_ENABLED=true.

    POST /v1/telemetry/errors
    GET  /v1/admin/telemetry/errors
"""

import os
import subprocess
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import requests

from auth_helpers import admin_headers

_BASE = os.getenv("TEST_API_URL", "http://localhost:8000")
REPORT_URL = f"{_BASE}/v1/telemetry/errors"
ADMIN_URL = f"{_BASE}/v1/admin/telemetry/errors"

_HEADERS = admin_headers()
RUN = uuid.uuid4().hex[:8]

SAFARI = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/18.3 Safari/605.1.15"
)


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


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _report(errors: list[dict], user_agent: str = SAFARI) -> requests.Response:
    return requests.post(
        REPORT_URL, json={"errors": errors}, headers={"User-Agent": user_agent}
    )


def _message(suffix: str) -> str:
    return f"it-{RUN}-{suffix}"


@pytest.fixture(scope="module", autouse=True)
def enabled_or_skip():
    response = requests.get(ADMIN_URL, headers=_HEADERS)
    response.raise_for_status()
    if not response.json()["enabled"]:
        pytest.skip("FRONTEND_ERRORS_ENABLED is false on this deployment")
    yield
    _psql(f"DELETE FROM frontend_errors WHERE message LIKE 'it-{RUN}-%';")


# ---------------------------------------------------------------------------
# Access
# ---------------------------------------------------------------------------


def test_reporting_needs_no_authentication():
    """Storefront visitors are not signed in; their errors matter most."""
    response = _report(
        [
            {
                "app": "storefront",
                "name": "TypeError",
                "message": _message("anon"),
                "occurred_at": _now(),
            }
        ]
    )
    assert response.status_code == 202
    assert response.json()["accepted"] == 1


def test_reading_errors_requires_admin():
    assert requests.get(ADMIN_URL).status_code in (401, 403)


# ---------------------------------------------------------------------------
# What must never be stored
# ---------------------------------------------------------------------------


def test_the_table_cannot_hold_an_ip_or_a_raw_user_agent():
    """
    The privacy posture is structural. `browser` holds a reduced label; there is
    nowhere to put a fingerprint.
    """
    columns = set(
        _psql(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'frontend_errors';"
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
    }
    assert not (columns & forbidden), f"PII column present: {columns & forbidden}"
    assert "browser" in columns


def test_the_raw_user_agent_is_reduced_before_storage():
    message = _message("ua")
    _report(
        [
            {
                "app": "storefront",
                "name": "TypeError",
                "message": message,
                "occurred_at": _now(),
            }
        ],
        user_agent=SAFARI,
    )

    stored = _psql(f"SELECT browser FROM frontend_errors WHERE message = '{message}';")
    assert stored == "Safari 18"
    assert "AppleWebKit" not in stored
    assert "Macintosh" not in stored


def test_a_query_string_carrying_a_token_is_not_stored():
    message = _message("qs")
    _report(
        [
            {
                "app": "storefront",
                "name": "TypeError",
                "message": message,
                "path": "/checkout?token=supersecret",
                "occurred_at": _now(),
            }
        ]
    )

    stored = _psql(f"SELECT path FROM frontend_errors WHERE message = '{message}';")
    assert stored == "/checkout"
    assert "supersecret" not in stored


# ---------------------------------------------------------------------------
# Hostile and merely broken input
# ---------------------------------------------------------------------------


def test_an_unknown_app_is_refused():
    response = _report(
        [
            {
                "app": "wordpress",
                "name": "TypeError",
                "message": _message("bad"),
                "occurred_at": _now(),
            }
        ]
    )
    assert response.status_code == 422


def test_stale_timestamps_are_discarded():
    old = (datetime.now(UTC) - timedelta(days=400)).isoformat()
    response = _report(
        [
            {
                "app": "storefront",
                "name": "TypeError",
                "message": _message("stale"),
                "occurred_at": old,
            },
            {
                "app": "storefront",
                "name": "TypeError",
                "message": _message("fresh"),
                "occurred_at": _now(),
            },
        ]
    )
    body = response.json()
    assert body["accepted"] == 1
    assert body["rejected"] == 1


# ---------------------------------------------------------------------------
# Grouping
# ---------------------------------------------------------------------------


def test_the_same_fault_on_two_routes_is_one_group():
    """
    One bug produces thousands of identical rows. Reading them ungrouped is
    useless, and grouping by stack would split one bug into many.
    """
    message = _message("grouped")
    _report(
        [
            {
                "app": "storefront",
                "name": "TypeError",
                "message": message,
                "path": "/shop/1",
                "stack": "at Product.render",
                "occurred_at": _now(),
            },
            {
                "app": "storefront",
                "name": "TypeError",
                "message": message,
                "path": "/shop/2",
                "stack": "at Product.render (other frame)",
                "occurred_at": _now(),
            },
        ]
    )

    payload = requests.get(ADMIN_URL, headers=_HEADERS, params={"limit": 200}).json()
    group = next(g for g in payload["groups"] if g["message"] == message)

    assert group["occurrences"] == 2
    assert group["affected_paths"] == 2
    assert group["browsers"] == ["Safari 18"]
    assert group["sample_stack"]


def test_groups_are_ordered_by_how_often_they_happen():
    payload = requests.get(ADMIN_URL, headers=_HEADERS, params={"limit": 200}).json()
    counts = [g["occurrences"] for g in payload["groups"]]
    assert counts == sorted(counts, reverse=True)


def test_errors_can_be_filtered_to_one_application():
    _report(
        [
            {
                "app": "admin",
                "name": "HttpErrorResponse",
                "message": _message("adminonly"),
                "occurred_at": _now(),
            }
        ]
    )

    payload = requests.get(
        ADMIN_URL, headers=_HEADERS, params={"app": "admin", "limit": 200}
    ).json()

    assert payload["groups"]
    assert all(g["app"] == "admin" for g in payload["groups"])
