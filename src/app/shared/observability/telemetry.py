"""
OpenTelemetry Wiring

Traces and metrics for the API and the worker, exported over OTLP.

**OTLP is the seam.** Nothing in application code imports a vendor SDK, and no
module outside this package knows telemetry exists beyond calling `setup()`.
Sending data to a different backend is a change to
`OTEL_EXPORTER_OTLP_ENDPOINT`, not a change to any service.

**Off by default.** `setup()` returns immediately unless `OTEL_ENABLED` is set,
so a deployment that has not opted in creates no exporter, opens no connection
and sends nothing.

**It must never take the application down.** Every step is wrapped: a collector
that is absent, unreachable or misconfigured produces a warning and a running
API, not a failed start. Observability that can cause the outage it exists to
diagnose is a bad trade.
"""

from __future__ import annotations

from typing import Any

from app.shared.logger import get_logger

logger = get_logger(__name__)

_configured = False


def _resource(settings: Any):
    from opentelemetry.sdk.resources import Resource

    return Resource.create(
        {
            "service.name": settings.otel_service_name,
            "service.version": settings.app_version,
            "deployment.environment": str(
                getattr(settings.environment, "value", settings.environment)
            ),
        }
    )


def _setup_tracing(settings: Any, resource) -> None:
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    provider = TracerProvider(resource=resource)
    provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(
                endpoint=f"{settings.otel_exporter_otlp_endpoint}/v1/traces"
            )
        )
    )
    trace.set_tracer_provider(provider)


def _setup_metrics(settings: Any, resource) -> None:
    from opentelemetry import metrics
    from opentelemetry.exporter.otlp.proto.http.metric_exporter import (
        OTLPMetricExporter,
    )
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

    reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(
            endpoint=f"{settings.otel_exporter_otlp_endpoint}/v1/metrics"
        ),
        export_interval_millis=settings.otel_metric_export_interval_seconds * 1000,
    )
    metrics.set_meter_provider(
        MeterProvider(resource=resource, metric_readers=[reader])
    )


def setup(settings: Any) -> bool:
    """
    Configure tracing and metrics.

    Safe to call more than once; only the first call does anything, because the
    API and the worker share this module and a second provider would silently
    replace the first.

    Returns:
        True when telemetry is now running, False when disabled or unavailable.
    """
    global _configured

    if not settings.otel_enabled:
        logger.debug("OpenTelemetry disabled (OTEL_ENABLED is false)")
        return False

    if _configured:
        return True

    try:
        resource = _resource(settings)
        _setup_tracing(settings, resource)
        _setup_metrics(settings, resource)
    except Exception as exc:  # noqa: BLE001 — see the module docstring
        logger.warning(
            "OpenTelemetry could not be configured; continuing without it",
            extra={"error": str(exc), "error_type": type(exc).__name__},
        )
        return False

    _configured = True
    logger.info(
        "OpenTelemetry configured",
        extra={
            "endpoint": settings.otel_exporter_otlp_endpoint,
            "service": settings.otel_service_name,
        },
    )
    return True


def instrument_app(app: Any, settings: Any) -> None:
    """
    Instrument the FastAPI application and its clients.

    Health endpoints are excluded. A liveness probe every few seconds would
    otherwise dominate the trace volume and the request-rate metric, burying
    real traffic under a heartbeat.
    """
    if not settings.otel_enabled or not _configured:
        return

    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app, excluded_urls="health,health/ready")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not instrument FastAPI", extra={"error": str(exc)})

    _instrument_clients(settings)


def _instrument_clients(settings: Any) -> None:
    """Instrument Redis and outbound HTTP. Each failure is isolated."""
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    from opentelemetry.instrumentation.redis import RedisInstrumentor

    for name, instrumentor in (
        ("redis", RedisInstrumentor),
        ("httpx", HTTPXClientInstrumentor),
    ):
        try:
            instrumentor().instrument()
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Could not instrument {name}", extra={"error": str(exc)})


def instrument_engine(engine: Any, settings: Any) -> None:
    """
    Instrument SQLAlchemy.

    Takes the sync engine behind an async one: the instrumentation hooks
    SQLAlchemy's own events, which live on the underlying engine rather than on
    the async facade.
    """
    if not settings.otel_enabled or not _configured:
        return

    try:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

        SQLAlchemyInstrumentor().instrument(
            engine=getattr(engine, "sync_engine", engine)
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not instrument SQLAlchemy", extra={"error": str(exc)})


def current_trace_id() -> str | None:
    """
    The active trace id as hex, or None.

    Logged alongside the correlation ID so a trace found in Grafana leads to the
    log lines for that request. Without it the two systems describe the same
    request and cannot be joined.
    """
    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        context = span.get_span_context()
        if not context.is_valid:
            return None
        return format(context.trace_id, "032x")
    except Exception:  # noqa: BLE001
        return None
