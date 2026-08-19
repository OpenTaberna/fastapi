"""
Expire Reservations ARQ Job — Phase 4.2

Scheduled ARQ job that releases all stock reservations whose TTL has passed.

The ``expire_reservations`` business-logic function already existed from
Phase 1.2.  This module wraps it as an ARQ cron-compatible async function
and wires it into the worker's ``cron_jobs`` list.

Scheduling:
    Add ``expire_reservations_sweep`` to ``WorkerSettings.cron_jobs`` using
    ``arq.cron``.  Run every 5 minutes by default — adjust with the
    ``reservation_ttl_minutes`` setting.
"""

from app.services.orders.functions.inventory_functions import expire_reservations
from app.shared.logger import get_logger

logger = get_logger(__name__)


async def expire_reservations_sweep(ctx: dict) -> int:
    """
    Release all ACTIVE stock reservations that have exceeded their TTL.

    This is the ARQ-compatible wrapper around the
    ``orders.functions.inventory_functions.expire_reservations`` business
    logic.  It opens a DB session, executes the sweep inside a transaction,
    commits, and logs the result.

    Called by ARQ on its cron schedule (every 5 minutes by default).

    Args:
        ctx: ARQ worker context dict.  Must contain ``session_factory`` —
             an ``async_sessionmaker`` instance created during worker startup.

    Returns:
        Number of reservations that were expired and released.
    """
    session_factory = ctx["session_factory"]

    async with session_factory() as session:
        async with session.begin():
            expired_count = await expire_reservations(session)

    if expired_count:
        logger.info(
            "Reservation expiry sweep completed",
            extra={"expired_count": expired_count},
        )
    else:
        logger.debug("Reservation expiry sweep: nothing to expire")

    return expired_count
