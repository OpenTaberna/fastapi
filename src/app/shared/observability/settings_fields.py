"""
Observability configuration fields.

Kept beside the telemetry code rather than inline in Settings so the whole
feature — its switches, its wiring and its meters — reads as one thing.
"""

from pydantic import Field

OTEL_FIELDS = {
    "otel_enabled": Field(
        default=False,
        description=(
            "Export traces and metrics over OTLP. Off by default: a deployment "
            "that has not opted in must send nothing anywhere."
        ),
    ),
    "otel_exporter_otlp_endpoint": Field(
        default="http://opentaberna-otel-collector:4318",
        description=(
            "OTLP/HTTP endpoint. This is the seam: pointing it at a vendor's "
            "collector is the whole change needed to use one, because no "
            "application code imports a vendor SDK."
        ),
    ),
    "otel_service_name": Field(
        default="opentaberna-api",
        description="service.name on every span and metric",
    ),
    "otel_metric_export_interval_seconds": Field(
        default=30,
        description="Seconds between metric exports",
    ),
}
