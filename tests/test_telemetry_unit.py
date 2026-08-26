"""
Unit tests for the observability wiring — no collector, no network.

Two properties matter more than the plumbing and are pinned here:

    - telemetry stays off unless the operator opts in
    - telemetry can never take the application down
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.shared.observability import telemetry
from app.shared.observability.business_metrics import QUEUE_GAUGES


def _settings(**overrides) -> SimpleNamespace:
    base = {
        "otel_enabled": True,
        "otel_exporter_otlp_endpoint": "http://collector:4318",
        "otel_service_name": "test-service",
        "otel_metric_export_interval_seconds": 30,
        "app_version": "0.0.0",
        "environment": "testing",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.fixture(autouse=True)
def _reset_module_state():
    """setup() is idempotent by design, so tests must reset the latch."""
    telemetry._configured = False
    yield
    telemetry._configured = False


# ---------------------------------------------------------------------------
# Off unless opted in
# ---------------------------------------------------------------------------


def test_setup_does_nothing_when_disabled():
    """
    A deployment that has not opted in must create no exporter and open no
    connection — not merely send nothing useful.
    """
    with (
        patch.object(telemetry, "_setup_tracing") as tracing,
        patch.object(telemetry, "_setup_metrics") as metrics,
    ):
        assert telemetry.setup(_settings(otel_enabled=False)) is False

    tracing.assert_not_called()
    metrics.assert_not_called()


def test_instrument_app_does_nothing_when_disabled():
    app = object()
    with patch.object(telemetry, "_instrument_clients") as clients:
        telemetry.instrument_app(app, _settings(otel_enabled=False))
    clients.assert_not_called()


def test_instrument_engine_does_nothing_before_setup():
    """
    Instrumenting before setup silently produced no metrics at all once. The
    guard makes that a no-op rather than a half-configured pipeline.
    """
    engine = object()
    telemetry._configured = False
    # Must not raise, and must not reach the instrumentation library.
    telemetry.instrument_engine(engine, _settings())


# ---------------------------------------------------------------------------
# Never take the application down
# ---------------------------------------------------------------------------


def test_an_unreachable_collector_does_not_stop_startup():
    """
    Observability that can cause the outage it exists to diagnose is a bad
    trade. A broken exporter must degrade to "no telemetry", not "no API".
    """
    with patch.object(
        telemetry, "_setup_tracing", side_effect=OSError("connection refused")
    ):
        assert telemetry.setup(_settings()) is False


def test_a_broken_metrics_pipeline_does_not_stop_startup():
    with (
        patch.object(telemetry, "_setup_tracing"),
        patch.object(
            telemetry, "_setup_metrics", side_effect=RuntimeError("bad endpoint")
        ),
    ):
        assert telemetry.setup(_settings()) is False


def test_setup_is_idempotent():
    """
    The API and the worker share this module. A second provider would silently
    replace the first, so the second call must be a no-op.
    """
    with (
        patch.object(telemetry, "_setup_tracing") as tracing,
        patch.object(telemetry, "_setup_metrics"),
    ):
        assert telemetry.setup(_settings()) is True
        assert telemetry.setup(_settings()) is True

    assert tracing.call_count == 1


def test_current_trace_id_returns_none_outside_a_span():
    """Callers log this unconditionally, so it must never raise."""
    assert telemetry.current_trace_id() is None


# ---------------------------------------------------------------------------
# The gauges an operator alerts on
# ---------------------------------------------------------------------------


def test_every_queue_state_deployment_docs_name_has_a_gauge():
    """
    Deployment.md tells operators to watch these four. If a gauge is dropped,
    the documented alert quietly stops being possible.
    """
    assert "opentaberna.outbox.pending" in QUEUE_GAUGES
    assert "opentaberna.outbox.failed" in QUEUE_GAUGES
    assert "opentaberna.outbox.dead" in QUEUE_GAUGES
    assert "opentaberna.webhooks.unprocessed" in QUEUE_GAUGES


def test_each_gauge_carries_sql_and_a_description():
    for name, (sql, description) in QUEUE_GAUGES.items():
        assert sql.lower().startswith("select count(*)"), name
        # The description is what an operator reads at 3am; an empty one makes
        # the panel a number with no meaning.
        assert len(description) > 20, name


def test_gauge_queries_exclude_soft_deleted_orders():
    """A cancelled order must not be reported as work waiting to be done."""
    sql, _ = QUEUE_GAUGES["opentaberna.orders.awaiting_shipment"]
    assert "deleted_at IS NULL" in sql
