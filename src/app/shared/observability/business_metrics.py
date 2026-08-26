"""
Business Metrics

Gauges for the queue states that mean the shop has quietly stopped working.

`Deployment.md` names the queries worth alerting on. Until now they were
something an operator had to remember to run by hand, which means nobody ran
them and the first sign of a stalled fulfillment pipeline was a customer asking
where their parcel was. These export the same figures on a schedule.

**Collected by the worker, not by the metrics SDK.** An observable gauge's
callback runs on the SDK's own thread, and the only database engine this
application has is asynchronous — driving it from outside the event loop fails,
which is exactly what the first version of this module did. The worker already
runs a scheduler, already holds an async session, and is the process that most
needs to be alive for these numbers to matter. So it computes them on a cron and
sets synchronous gauges.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.logger import get_logger

logger = get_logger(__name__)

# name -> (SQL, description). Each of these being non-zero and staying non-zero
# means something is wrong that no HTTP status code will reveal.
QUEUE_GAUGES: dict[str, tuple[str, str]] = {
    "opentaberna.outbox.pending": (
        "SELECT count(*) FROM outbox_events WHERE status = 'pending'",
        "Outbox events awaiting enqueue. Rising means the worker is not running.",
    ),
    "opentaberna.outbox.failed": (
        "SELECT count(*) FROM outbox_events WHERE status = 'failed'",
        "Events that never reached the queue. Points at Redis or the poller.",
    ),
    "opentaberna.outbox.dead": (
        "SELECT count(*) FROM outbox_events WHERE status = 'dead'",
        "Jobs that ran and exhausted their retries. Usually the carrier API.",
    ),
    "opentaberna.webhooks.unprocessed": (
        "SELECT count(*) FROM webhook_events WHERE processed_at IS NULL",
        "Payments arriving but not handled. Money is at stake here.",
    ),
    "opentaberna.orders.awaiting_shipment": (
        "SELECT count(*) FROM orders WHERE deleted_at IS NULL "
        "AND status IN ('paid', 'ready_to_ship')",
        "Paid orders not yet handed to a carrier. The work queue.",
    ),
}

_gauges: dict[str, Any] = {}


def _ensure_gauges() -> dict[str, Any]:
    """Create the gauge instruments once, on first collection."""
    global _gauges

    if _gauges:
        return _gauges

    from opentelemetry import metrics

    meter = metrics.get_meter("opentaberna.business")
    _gauges = {
        name: meter.create_gauge(name, description=description)
        for name, (_, description) in QUEUE_GAUGES.items()
    }
    logger.info("Business gauges created", extra={"count": len(_gauges)})
    return _gauges


async def collect(session: AsyncSession, settings: Any) -> dict[str, int]:
    """
    Read the queue counts and publish them as gauges.

    Returns the values, so the caller can log them and a test can assert on
    them without reaching into the metrics SDK.

    A failure here is logged and swallowed: a metrics collection that raises
    would take down the scheduler it runs on, turning an observability problem
    into a fulfillment one.
    """
    if not settings.otel_enabled:
        return {}

    values: dict[str, int] = {}

    try:
        gauges = _ensure_gauges()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Business gauges unavailable", extra={"error": str(exc)})
        return {}

    for name, (sql, _) in QUEUE_GAUGES.items():
        try:
            result = await session.execute(text(sql))
            value = int(result.scalar() or 0)
            values[name] = value
            gauges[name].set(value)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Business metric could not be collected",
                extra={"metric": name, "error": str(exc)},
            )

    return values
