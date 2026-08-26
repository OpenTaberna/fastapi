"""
Integration tests for observability (S3).

Runs against the live stack with OTEL_ENABLED=true:

    docker compose -f docker-compose.dev.yml up -d

Asserts against the collector's Prometheus endpoint and Prometheus itself,
because "the SDK was configured" is not the same claim as "a number an operator
can alert on actually arrived".
"""

import os

import pytest
import requests

COLLECTOR = os.getenv("TEST_COLLECTOR_URL", "http://localhost:8889")
PROMETHEUS = os.getenv("TEST_PROMETHEUS_URL", "http://localhost:9090")
API = os.getenv("TEST_API_URL", "http://localhost:8000")


def _collector_metrics() -> str:
    response = requests.get(f"{COLLECTOR}/metrics", timeout=10)
    response.raise_for_status()
    return response.text


def _promql(query: str) -> list:
    response = requests.get(
        f"{PROMETHEUS}/api/v1/query", params={"query": query}, timeout=10
    )
    response.raise_for_status()
    return response.json()["data"]["result"]


@pytest.fixture(scope="module", autouse=True)
def stack_or_skip():
    """Nothing to assert on a deployment that has not opted into telemetry."""
    try:
        requests.get(f"{COLLECTOR}/metrics", timeout=5).raise_for_status()
        requests.get(f"{PROMETHEUS}/-/healthy", timeout=5).raise_for_status()
    except Exception:
        pytest.skip("collector or Prometheus not running")

    # Give the pipeline something to measure.
    for _ in range(5):
        requests.get(f"{API}/v1/items/", timeout=10)
    yield


# ---------------------------------------------------------------------------
# The pipeline actually carries data
# ---------------------------------------------------------------------------


def test_http_request_metrics_reach_the_collector():
    """
    This is the one that caught a real bug: instrumenting the app before
    configuring telemetry produced a clean startup log and no HTTP metrics at
    all. Asserting on the pipeline's output catches that; asserting on the
    setup call would not.
    """
    assert "http_server_duration_milliseconds" in _collector_metrics()


def test_both_services_report():
    """The worker matters as much as the API — fulfillment happens there."""
    metrics = _collector_metrics()
    assert 'job="opentaberna-api"' in metrics
    assert 'job="opentaberna-worker"' in metrics


def test_prometheus_is_scraping_the_collector():
    targets = requests.get(f"{PROMETHEUS}/api/v1/targets", timeout=10).json()
    jobs = {
        t["labels"].get("job"): t["health"] for t in targets["data"]["activeTargets"]
    }
    assert jobs.get("opentaberna") == "up"


# ---------------------------------------------------------------------------
# The gauges an operator alerts on
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "metric",
    [
        "opentaberna_outbox_pending",
        "opentaberna_outbox_failed",
        "opentaberna_outbox_dead",
        "opentaberna_webhooks_unprocessed",
        "opentaberna_orders_awaiting_shipment",
    ],
)
def test_each_documented_alert_query_has_a_live_metric(metric):
    """
    Deployment.md tells operators to watch these. Each must be queryable, or
    the documented alert cannot be built.
    """
    assert _promql(metric), f"{metric} is not in Prometheus"


def test_awaiting_shipment_matches_the_database():
    """
    A gauge that is exported but wrong is worse than one that is missing. This
    checks the number against the query it claims to represent.
    """
    import subprocess

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
            "SELECT count(*) FROM orders WHERE deleted_at IS NULL "
            "AND status IN ('paid', 'ready_to_ship');",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    expected = int(result.stdout.strip())

    series = _promql("opentaberna_orders_awaiting_shipment")
    assert series
    assert int(float(series[0]["value"][1])) == expected


# ---------------------------------------------------------------------------
# Noise control
# ---------------------------------------------------------------------------


def test_health_probes_are_not_traced_as_traffic():
    """
    A liveness probe every few seconds would dominate the request-rate metric
    and bury real traffic under a heartbeat.
    """
    for _ in range(5):
        requests.get(f"{API}/health", timeout=10)

    metrics = _collector_metrics()
    health_lines = [
        line
        for line in metrics.splitlines()
        if line.startswith("http_server_duration_milliseconds_count")
        and 'http_target="/health"' in line
    ]
    assert not health_lines, "health checks are being counted as traffic"
