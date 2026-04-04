"""
ARQ Worker

Entry point for the ARQ background job worker process.

Run with:
    arq app.worker.WorkerSettings

Context (ctx dict):
    startup()  builds the context dict shared by all job functions:
        ctx["settings"]         — application Settings instance
        ctx["session_factory"]  — async_sessionmaker for DB access
        ctx["carrier_adapters"] — dict[str, CarrierAdapter]
        ctx["storage_adapter"]  — MinioStorageAdapter

Scheduled jobs:
    poll_outbox runs every settings.outbox_poll_interval seconds.  It reads
    PENDING rows from the outbox_events table and enqueues the corresponding
    ARQ jobs into Redis.  This is the bridge between the DB outbox guarantee
    and the ARQ execution layer.

Dead-letter hook:
    on_job_abort is called by ARQ when a job exhausts its retries.  It logs
    the failure at ERROR level and marks the outbox event row as DEAD so it
    is visible in the DB for manual investigation.

Retry / Backoff:
    ARQ retries up to WorkerSettings.max_tries times.  The default backoff
    is exponential (2^attempt seconds) and is handled entirely by ARQ.
"""

import json
from uuid import UUID

from arq import cron
from arq.connections import RedisSettings
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.db_models  # noqa: F401 — ensures all ORM models are registered
from app.services.fulfillment.adapters.dhl_adapter import build_dhl_adapter
from app.services.fulfillment.adapters.manual_adapter import ManualCarrierAdapter
from app.services.fulfillment.jobs.create_label_job import create_label
from app.services.fulfillment.outbox.services.outbox_db_service import (
    get_outbox_repository,
)
from app.shared.config import get_settings
from app.shared.logger import get_logger
from app.shared.storage.minio_adapter import build_minio_adapter

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Worker lifecycle hooks
# ---------------------------------------------------------------------------


async def startup(ctx: dict) -> None:
    """
    Initialise shared resources and populate the ARQ context dict.

    Called once when the worker process starts.  Resources created here are
    reused across all job executions in this worker — no per-job overhead.

    Args:
        ctx: ARQ worker context dict (mutable — populate it here).

    Returns:
        None
    """
    settings = get_settings()
    ctx["settings"] = settings

    engine = create_async_engine(
        settings.database_url,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_pre_ping=settings.database_pool_pre_ping,
    )
    ctx["session_factory"] = async_sessionmaker(engine, expire_on_commit=False)

    ctx["carrier_adapters"] = {
        "dhl": build_dhl_adapter(
            base_url=settings.dhl_api_base_url,
            client_id=settings.dhl_client_id,
            client_secret=settings.dhl_client_secret,
            billing_number=settings.dhl_billing_number,
        ),
        "manual": ManualCarrierAdapter(),
    }

    ctx["storage_adapter"] = build_minio_adapter(
        endpoint_url=settings.storage_endpoint_url,
        access_key=settings.storage_access_key,
        secret_key=settings.storage_secret_key,
        region=settings.storage_region,
    )

    # Ensure the label bucket exists before any job tries to upload
    await ctx["storage_adapter"].ensure_bucket(settings.storage_bucket_labels)

    logger.info("ARQ worker started")


async def shutdown(ctx: dict) -> None:
    """
    Clean up shared resources when the worker process shuts down.

    Args:
        ctx: ARQ worker context dict.

    Returns:
        None
    """
    logger.info("ARQ worker shutting down")


# ---------------------------------------------------------------------------
# Scheduled job: outbox poller
# ---------------------------------------------------------------------------


async def poll_outbox(ctx: dict) -> None:
    """
    Sweep the outbox_events table and enqueue any PENDING label jobs.

    This scheduled job bridges the DB outbox guarantee and the ARQ execution
    layer.  It runs every settings.outbox_poll_interval seconds.

    For each PENDING event:
        1. Increment the attempt counter.
        2. Enqueue an ARQ job via ctx["redis"].enqueue_job().
        3. Mark the outbox row as ENQUEUED with the returned ARQ job ID.

    Args:
        ctx: ARQ worker context dict with session_factory and redis keys.

    Returns:
        None
    """
    session_factory = ctx["session_factory"]

    async with session_factory() as session:
        outbox_repo = get_outbox_repository(session)
        pending = await outbox_repo.list_pending(limit=100)

    if not pending:
        return

    logger.info("Outbox poll found pending events", extra={"count": len(pending)})

    for event in pending:
        await _enqueue_single_outbox_event(ctx, event)


async def _enqueue_single_outbox_event(ctx: dict, event) -> None:
    """
    Enqueue one outbox event into ARQ and update its DB status.

    Args:
        ctx:   ARQ worker context dict.
        event: OutboxEventDB row to enqueue.

    Returns:
        None
    """
    session_factory = ctx["session_factory"]
    redis = ctx["redis"]

    try:
        payload = json.loads(event.payload)
        job = await redis.enqueue_job(
            event.event_type,
            outbox_event_id=str(event.id),
            **{k: v for k, v in payload.items() if k != "outbox_event_id"},
        )
        arq_job_id = job.job_id if job else str(event.id)

        async with session_factory() as session:
            async with session.begin():
                outbox_repo = get_outbox_repository(session)
                await outbox_repo.mark_enqueued(event.id, arq_job_id)
                await outbox_repo.increment_attempts(event.id)

        logger.info(
            "Outbox event enqueued",
            extra={
                "event_id": str(event.id),
                "arq_job_id": arq_job_id,
                "event_type": event.event_type,
            },
        )
    except Exception as exc:
        logger.error(
            "Failed to enqueue outbox event",
            extra={"event_id": str(event.id), "error": str(exc)},
            exc_info=True,
        )
        async with session_factory() as session:
            async with session.begin():
                outbox_repo = get_outbox_repository(session)
                await outbox_repo.increment_attempts(event.id)


# ---------------------------------------------------------------------------
# Dead-letter hook
# ---------------------------------------------------------------------------


async def on_job_abort(ctx: dict, job_id: str, function: str, args, kwargs) -> None:
    """
    Called by ARQ when a job exhausts all retries (dead-lettered).

    Logs the failure at ERROR level and marks the corresponding outbox
    event row as DEAD so it is visible for manual investigation.

    Args:
        ctx:      ARQ worker context dict.
        job_id:   ARQ job ID of the dead job.
        function: Name of the failed ARQ task function.
        args:     Positional arguments the job was called with.
        kwargs:   Keyword arguments the job was called with.

    Returns:
        None
    """
    outbox_event_id: str | None = kwargs.get("outbox_event_id")

    logger.error(
        "ARQ job dead-lettered",
        extra={
            "job_id": job_id,
            "function": function,
            "outbox_event_id": outbox_event_id,
        },
    )

    if outbox_event_id is None:
        return

    session_factory = ctx.get("session_factory")
    if session_factory is None:
        return

    try:
        async with session_factory() as session:
            async with session.begin():
                outbox_repo = get_outbox_repository(session)
                await outbox_repo.mark_dead(UUID(outbox_event_id))
        logger.info(
            "Outbox event marked DEAD",
            extra={"outbox_event_id": outbox_event_id},
        )
    except Exception as exc:
        logger.error(
            "Failed to mark outbox event as DEAD",
            extra={"outbox_event_id": outbox_event_id, "error": str(exc)},
            exc_info=True,
        )


# ---------------------------------------------------------------------------
# Worker settings
# ---------------------------------------------------------------------------


def _build_redis_settings() -> RedisSettings:
    """
    Build ARQ RedisSettings from the application Settings.

    Returns:
        Configured RedisSettings instance.
    """
    settings = get_settings()
    # arq expects host/port/password separately — parse from URL
    url = settings.redis_url  # e.g. "redis://localhost:6379/0"
    # Strip scheme and parse
    without_scheme = url.split("://", 1)[-1]
    host_port, *db_part = without_scheme.split("/")
    host, *port_part = host_port.split(":")
    port = int(port_part[0]) if port_part else 6379
    database = int(db_part[0]) if db_part else 0

    return RedisSettings(
        host=host,
        port=port,
        database=database,
        password=settings.redis_password,
    )


class WorkerSettings:
    """
    ARQ WorkerSettings class.

    ARQ reads this class to configure the worker process.  All settings are
    derived from the application Settings so a single .env file controls both
    the FastAPI app and the worker.

    Attributes:
        functions:      List of async callables ARQ can execute as jobs.
        cron_jobs:      Scheduled jobs that run on a fixed interval.
        on_startup:     Hook called once when the worker starts.
        on_shutdown:    Hook called once when the worker stops.
        on_job_abort:   Hook called when a job exhausts all retries.
        redis_settings: Connection details for the Redis broker.
        max_jobs:       Max concurrent jobs per worker process.
        job_timeout:    Max seconds a job may run before it is killed.
        max_tries:      Max delivery attempts per job.
        log_results:    Log job result values (disabled to avoid large payloads).
    """

    functions = [create_label]

    @staticmethod
    def _poll_interval() -> int:
        return get_settings().outbox_poll_interval

    cron_jobs = [
        cron(poll_outbox, minute={*range(0, 60)}, second=0),
    ]

    on_startup = startup
    on_shutdown = shutdown
    on_job_abort = on_job_abort

    redis_settings = _build_redis_settings()

    max_jobs = get_settings().arq_max_jobs
    job_timeout = get_settings().arq_job_timeout
    max_tries = get_settings().arq_max_tries
    log_results = False
