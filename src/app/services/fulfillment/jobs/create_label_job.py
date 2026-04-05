"""
Create Label ARQ Job

Executes asynchronously in the ARQ worker process.

Lifecycle:
    1. Triggered by the outbox poller via arq.ArqRedis.enqueue_job("create_label", ...).
    2. Fetches the shipment and associated order/customer/address from the DB.
    3. Selects the correct CarrierAdapter from the ARQ context dict.
    4. Calls adapter.create_label() to obtain tracking number + label bytes.
    5. Uploads the label file to MinIO via the StorageAdapter.
    6. Updates ShipmentDB: tracking_number, label_url, label_format, status=LABEL_CREATED.
    7. Marks the outbox event as DONE.

Retry / Backoff:
    ARQ retries the job up to settings.arq_max_tries times.  Each retry is
    handled by ARQ's built-in backoff (2^attempt seconds, capped).  The job
    raises the exception on failure so ARQ increments the retry counter.

Dead-Letter:
    When ARQ gives up (max_tries exhausted), the on_job_abort hook in
    worker.py logs the failure at ERROR level and marks the outbox event DEAD.
    No silent data loss — every dead job is visible in the DB and the log.

Context keys (provided by worker.py startup):
    ctx["session_factory"]  — async_sessionmaker for DB access.
    ctx["carrier_adapters"] — dict[str, CarrierAdapter] keyed by carrier name.
    ctx["storage_adapter"]  — StorageAdapter instance for label upload.
    ctx["settings"]         — application Settings.

Order/customer/address data is loaded via fetch_order_context (the same
function used by admin endpoints) — no cross-service model imports needed.
"""

import json
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.admin.functions.order_context import OrderContext, fetch_order_context
from app.services.fulfillment.adapters.interface import CarrierAdapter, CarrierError
from app.services.fulfillment.outbox.services.outbox_db_service import (
    get_outbox_repository,
)
from app.services.shipments.models.shipments_models import ShipmentStatus
from app.services.shipments.services.shipments_db_service import get_shipment_repository
from app.shared.logger import get_logger
from app.shared.storage.interface import StorageAdapter

logger = get_logger(__name__)

# Storage object key pattern for label files
_LABEL_KEY_TEMPLATE = "labels/{shipment_id}.{ext}"

# MIME types per label format
_LABEL_MIME: dict[str, str] = {
    "pdf": "application/pdf",
    "zpl": "application/x-zpl",
}


async def create_label(
    ctx: dict,
    *,
    outbox_event_id: str,
    **_: object,
) -> None:
    """
    ARQ task: generate a carrier label and store it in MinIO.

    This function is the single ARQ task entry point.  It is registered in
    WorkerSettings.functions and called by ARQ when the job is dequeued.

    Args:
        ctx:             ARQ worker context dict (populated by startup hook).
        outbox_event_id: String UUID of the OutboxEventDB row that triggered
                         this job — used to load the payload and mark DONE/DEAD.
        **_: Additional legacy kwargs are accepted and ignored for
             compatibility with already-enqueued jobs.

    Returns:
        None

    Raises:
        CarrierError:  If the carrier API rejects the label request.
        StorageError:  If the MinIO upload fails.
        Exception:     Any other unexpected error — ARQ will retry.
    """
    event_uuid = UUID(outbox_event_id)
    session_factory = ctx["session_factory"]

    async with session_factory() as session:
        payload = await _load_outbox_payload(session, event_uuid)

    shipment_id = UUID(payload["shipment_id"])
    order_id = UUID(payload["order_id"])
    label_format: str = payload["label_format"]

    logger.info(
        "create_label job started",
        extra={
            "outbox_event_id": outbox_event_id,
            "shipment_id": str(shipment_id),
            "order_id": str(order_id),
            "label_format": label_format,
        },
    )

    async with session_factory() as session:
        order_ctx: OrderContext = await fetch_order_context(order_id, session)

    carrier_args = _extract_carrier_args(order_ctx, shipment_id)
    adapter: CarrierAdapter = _select_carrier_adapter(
        ctx, carrier_args["carrier"], shipment_id
    )
    storage: StorageAdapter = ctx["storage_adapter"]
    settings = ctx["settings"]
    bucket: str = settings.storage_bucket_labels

    label_result = await adapter.create_label(
        shipment_id=shipment_id,
        order_id=order_id,
        recipient_name=carrier_args["recipient_name"],
        street=carrier_args["street"],
        city=carrier_args["city"],
        postal_code=carrier_args["postal_code"],
        country_code=carrier_args["country_code"],
        weight_kg=carrier_args["weight_kg"],
        label_format=label_format,
    )

    label_url = await _upload_label(
        storage=storage,
        bucket=bucket,
        shipment_id=shipment_id,
        label_data=label_result.label_data,
        label_format=label_result.label_format,
    )

    async with session_factory() as session:
        async with session.begin():
            await _persist_label_result(
                session=session,
                shipment_id=shipment_id,
                tracking_number=label_result.tracking_number,
                label_url=label_url,
                label_format=label_result.label_format,
            )
            await _mark_outbox_done(session, event_uuid)

    logger.info(
        "create_label job completed",
        extra={
            "outbox_event_id": outbox_event_id,
            "shipment_id": str(shipment_id),
            "tracking_number": label_result.tracking_number,
        },
    )


# ---------------------------------------------------------------------------
# Private helpers — each does exactly one thing
# ---------------------------------------------------------------------------


async def _load_outbox_payload(session: AsyncSession, event_id: UUID) -> dict:
    """
    Load and deserialize the payload from an outbox event row.

    Args:
        session:  Active AsyncSession.
        event_id: UUID of the OutboxEventDB row.

    Returns:
        Deserialized payload dict with shipment_id, order_id, label_format.
    """
    outbox_repo = get_outbox_repository(session)
    event = await outbox_repo.get(event_id)
    return json.loads(event.payload)


def _extract_carrier_args(ctx: OrderContext, shipment_id: UUID) -> dict:
    """
    Extract the carrier adapter arguments from an already-loaded OrderContext.

    Uses the existing fetch_order_context result so no additional DB queries
    are needed and no cross-service model imports are required here.

    Args:
        ctx:         Fully loaded OrderContext for the order.
        shipment_id: UUID used in error context if required data is missing.

    Returns:
        Dict with carrier, recipient_name, street, city, postal_code (from
        AddressDB.zip_code), country_code (from AddressDB.country), and
        weight_kg ready to pass to CarrierAdapter.create_label.

    Raises:
        CarrierError: If the customer or shipping address is missing from the context.
    """
    if ctx.customer is None:
        raise CarrierError(
            message="Cannot create label: order has no associated customer.",
            context={"shipment_id": str(shipment_id)},
        )

    if ctx.shipping_address is None:
        raise CarrierError(
            message=(
                "Cannot create label: customer has no default shipping address. "
                "Set a default address via PATCH /customers/me/addresses/{id}."
            ),
            context={
                "shipment_id": str(shipment_id),
                "customer_id": str(ctx.customer.id),
            },
        )

    recipient_name = f"{ctx.customer.first_name} {ctx.customer.last_name}"

    return {
        "carrier": ctx.shipment.carrier,
        "recipient_name": recipient_name,
        "street": ctx.shipping_address.street,
        "city": ctx.shipping_address.city,
        "postal_code": ctx.shipping_address.zip_code,
        "country_code": ctx.shipping_address.country,
        "weight_kg": 1.0,  # Default weight — extend with per-order weight in Phase 4
    }


def _select_carrier_adapter(
    ctx: dict,
    carrier_name: str,
    shipment_id: UUID,
) -> CarrierAdapter:
    """
    Select the correct CarrierAdapter from the ARQ context by carrier name.

    Args:
        ctx:          ARQ worker context dict.
        carrier_name: Carrier string from ShipmentDB (e.g. "dhl", "manual").
        shipment_id:  UUID used in error context.

    Returns:
        The matching CarrierAdapter instance.

    Raises:
        CarrierError: If no adapter is registered for the given carrier name.
    """
    adapters: dict[str, CarrierAdapter] = ctx["carrier_adapters"]
    adapter = adapters.get(carrier_name)
    if adapter is None:
        raise CarrierError(
            message=f"No carrier adapter registered for carrier: {carrier_name!r}",
            context={"carrier": carrier_name, "shipment_id": str(shipment_id)},
        )
    return adapter


async def _upload_label(
    storage: StorageAdapter,
    bucket: str,
    shipment_id: UUID,
    label_data: bytes,
    label_format: str,
) -> str:
    """
    Upload label bytes to the object store and return the storage URL.

    Args:
        storage:      StorageAdapter instance.
        bucket:       Destination bucket name.
        shipment_id:  UUID used as the object key stem.
        label_data:   Raw label bytes.
        label_format: "pdf" or "zpl" — determines file extension and MIME type.

    Returns:
        Storage URL string for the uploaded object.
    """
    ext = label_format.lower()
    key = _LABEL_KEY_TEMPLATE.format(shipment_id=shipment_id, ext=ext)
    mime = _LABEL_MIME.get(ext, "application/octet-stream")
    return await storage.upload(
        bucket=bucket, key=key, data=label_data, content_type=mime
    )


async def _persist_label_result(
    session: AsyncSession,
    shipment_id: UUID,
    tracking_number: str,
    label_url: str,
    label_format: str,
) -> None:
    """
    Write the carrier label result back to the ShipmentDB row.

    Updates tracking_number, label_url, label_format, and advances
    the shipment status to LABEL_CREATED.

    Args:
        session:         Active AsyncSession (inside an open transaction).
        shipment_id:     UUID of the ShipmentDB row to update.
        tracking_number: Carrier-issued tracking number.
        label_url:       Storage URL of the uploaded label file.
        label_format:    "pdf" or "zpl".

    Returns:
        None
    """
    shipment_repo = get_shipment_repository(session)
    await shipment_repo.update(
        shipment_id,
        tracking_number=tracking_number,
        label_url=label_url,
        label_format=label_format,
        status=ShipmentStatus.LABEL_CREATED.value,
    )
    logger.info(
        "Shipment updated with label result",
        extra={
            "shipment_id": str(shipment_id),
            "tracking_number": tracking_number,
            "label_url": label_url,
        },
    )


async def _mark_outbox_done(session: AsyncSession, event_id: UUID) -> None:
    """
    Mark the outbox event row as DONE to prevent re-enqueuing.

    Called after the label upload and shipment DB update are both committed.

    Args:
        session:  Active AsyncSession (inside an open transaction).
        event_id: UUID of the OutboxEventDB row to mark as done.

    Returns:
        None
    """
    outbox_repo = get_outbox_repository(session)
    await outbox_repo.mark_done(event_id)
    logger.debug("Outbox event marked DONE", extra={"event_id": str(event_id)})
