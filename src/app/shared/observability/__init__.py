"""
Observability

OpenTelemetry traces and metrics, exported over OTLP.

OTLP is the seam: no application module imports a vendor SDK, so using a
different backend is a change to OTEL_EXPORTER_OTLP_ENDPOINT.
"""

from .business_metrics import QUEUE_GAUGES, collect as collect_business_metrics
from .telemetry import (
    current_trace_id,
    instrument_app,
    instrument_engine,
    setup,
)

__all__ = [
    "current_trace_id",
    "instrument_app",
    "instrument_engine",
    "QUEUE_GAUGES",
    "collect_business_metrics",
    "setup",
]
