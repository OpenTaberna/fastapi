"""
Fulfillment Router — Phase 3

FastAPI router for carrier label endpoints:

    POST  /admin/orders/{id}/label  — trigger DHL label job (or re-trigger on failure)
    GET   /admin/orders/{id}/label  — download the label PDF/ZPL from storage

Route order: both routes are on the same path /admin/orders/{id}/label but
with different HTTP methods, so there is no ordering conflict.

Design:
    - POST enqueues the job via the outbox pattern — it does NOT call the
      carrier API directly.  The HTTP handler returns 202 Accepted immediately.
    - GET proxies the label bytes from MinIO back to the admin browser.
      The label_format is read from the ShipmentDB row so the correct
      Content-Type and file extension are set automatically.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.admin.dependencies import require_admin
from app.services.admin.functions.order_context import OrderContext, fetch_order_context
from app.services.shipments.models.shipments_models import Carrier
from app.shared.config import get_settings
from app.shared.config.settings import Settings
from app.shared.database.session import get_session_dependency
from app.shared.database.transaction import transaction
from app.shared.exceptions import BusinessRuleError, entity_not_found
from app.shared.logger import get_logger
from app.shared.storage import StorageAdapter

from ..outbox.services.outbox_enqueue import enqueue_label_job
from ..responses import DOWNLOAD_LABEL_RESPONSES, TRIGGER_LABEL_RESPONSES

logger = get_logger(__name__)

router = APIRouter()

# MIME types for label formats
_LABEL_MIME: dict[str, str] = {
    "pdf": "application/pdf",
    "zpl": "application/x-zpl",
}


def _get_storage_adapter(
    settings: Settings = Depends(get_settings),
) -> StorageAdapter:
    """
    Build and return a MinioStorageAdapter from application settings.

    Args:
        settings: Application Settings instance (injected by FastAPI).

    Returns:
        Configured MinioStorageAdapter ready for upload/download calls.
    """
    from app.shared.storage.minio_adapter import build_minio_adapter

    return build_minio_adapter(
        endpoint_url=settings.storage_endpoint_url,
        access_key=settings.storage_access_key,
        secret_key=settings.storage_secret_key,
        region=settings.storage_region,
    )


# ---------------------------------------------------------------------------
# POST /admin/orders/{id}/label — trigger label job
# ---------------------------------------------------------------------------


@router.post(
    "/{order_id}/label",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger DHL label job (admin)",
    description=(
        "Enqueue a label-creation job for the order's shipment. "
        "Returns **202 Accepted** immediately — the actual DHL API call "
        "runs asynchronously in the ARQ worker. "
        "Safe to call again if the previous attempt failed (idempotent enqueue)."
    ),
    dependencies=[Depends(require_admin)],
    responses=TRIGGER_LABEL_RESPONSES,
)
async def trigger_label_job(
    order_id: UUID,
    session: AsyncSession = Depends(get_session_dependency),
    settings: Settings = Depends(get_settings),
) -> dict:
    """
    Enqueue a carrier label job for a READY_TO_SHIP order via the outbox pattern.

    Steps:
    1. Load order context; raise 404 if missing.
    2. Guard: order must have a shipment record.
    3. Guard: shipment carrier must not be MANUAL (no automated label for manual).
    4. Write an outbox event in the same DB transaction (at-least-once guarantee).
    5. Return 202 — the worker will enqueue and run the ARQ job asynchronously.

    Args:
        order_id: UUID of the order to generate a label for.
        session:  Database session.
        settings: Application settings (for default label format).

    Returns:
        Dict with a status message and the outbox_event_id for tracking.

    Raises:
        NotFoundError (404):     If the order does not exist or is soft-deleted.
        BusinessRuleError (400): If the order has no shipment, or carrier is MANUAL.
    """
    ctx: OrderContext = await fetch_order_context(order_id, session)
    if not ctx.order or ctx.order.deleted_at is not None:
        raise entity_not_found("Order", order_id)

    _guard_shipment_exists(ctx, order_id)
    _guard_carrier_supports_labels(ctx, order_id)

    label_format = settings.dhl_default_label_format

    async with transaction(session):
        event = await enqueue_label_job(
            session=session,
            shipment_id=ctx.shipment.id,
            order_id=order_id,
            label_format=label_format,
        )

    logger.info(
        "Label job enqueued via outbox",
        extra={
            "order_id": str(order_id),
            "shipment_id": str(ctx.shipment.id),
            "outbox_event_id": str(event.id),
            "label_format": label_format,
        },
    )

    return {
        "status": "accepted",
        "outbox_event_id": str(event.id),
        "message": "Label job enqueued. The worker will generate the label asynchronously.",
    }


# ---------------------------------------------------------------------------
# GET /admin/orders/{id}/label — download label file
# ---------------------------------------------------------------------------


@router.get(
    "/{order_id}/label",
    summary="Download carrier label (admin)",
    description=(
        "Download the shipping label (PDF or ZPL) for an order directly from "
        "object storage. Returns the raw file bytes with the correct Content-Type. "
        "The label must have been created by the ARQ worker first."
    ),
    dependencies=[Depends(require_admin)],
    responses=DOWNLOAD_LABEL_RESPONSES,
)
async def download_label(
    order_id: UUID,
    session: AsyncSession = Depends(get_session_dependency),
    settings: Settings = Depends(get_settings),
    storage: StorageAdapter = Depends(_get_storage_adapter),
) -> Response:
    """
    Proxy the label file bytes from MinIO to the admin HTTP client.

    Steps:
    1. Load order context; raise 404 if missing.
    2. Guard: shipment must exist and label_url must be populated.
    3. Download the label bytes from MinIO via the storage adapter.
    4. Return a raw Response with the correct Content-Type and filename header.

    Args:
        order_id: UUID of the order whose label to download.
        session:  Database session.
        settings: Application settings (for storage bucket name).
        storage:  StorageAdapter instance (injected).

    Returns:
        Raw HTTP Response with label bytes, Content-Type, and Content-Disposition.

    Raises:
        NotFoundError (404):    If the order or label does not exist.
        StorageError (502):     If the MinIO download fails.
    """
    ctx: OrderContext = await fetch_order_context(order_id, session)
    if not ctx.order or ctx.order.deleted_at is not None:
        raise entity_not_found("Order", order_id)

    _guard_shipment_exists(ctx, order_id)
    _guard_label_ready(ctx, order_id)

    label_format: str = ctx.shipment.label_format or "pdf"
    key = f"labels/{ctx.shipment.id}.{label_format}"

    label_bytes = await storage.download(
        bucket=settings.storage_bucket_labels,
        key=key,
    )

    mime = _LABEL_MIME.get(label_format, "application/octet-stream")
    filename = f"label_{order_id}.{label_format}"

    logger.info(
        "Label downloaded by admin",
        extra={"order_id": str(order_id), "label_format": label_format},
    )

    return Response(
        content=label_bytes,
        media_type=mime,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Private guard helpers — each validates exactly one precondition
# ---------------------------------------------------------------------------


def _guard_shipment_exists(ctx: OrderContext, order_id: UUID) -> None:
    """
    Raise BusinessRuleError if the order has no shipment record.

    Args:
        ctx:      Loaded OrderContext for the order.
        order_id: UUID used in the error context.

    Raises:
        BusinessRuleError (400): If ctx.shipment is None.
    """
    if ctx.shipment is None:
        raise BusinessRuleError(
            message="Order has no shipment record. Create a shipment first via POST /admin/orders/{id}/shipments.",
            context={"order_id": str(order_id)},
        )


def _guard_carrier_supports_labels(ctx: OrderContext, order_id: UUID) -> None:
    """
    Raise BusinessRuleError if the shipment carrier does not support automated labels.

    Manual carrier shipments require the admin to enter a tracking number by
    hand — there is no API to call.

    Args:
        ctx:      Loaded OrderContext for the order.
        order_id: UUID used in the error context.

    Raises:
        BusinessRuleError (400): If the carrier is MANUAL.
    """
    if ctx.shipment.carrier == Carrier.MANUAL.value:
        raise BusinessRuleError(
            message="Manual carrier shipments do not support automated label generation.",
            context={"order_id": str(order_id), "carrier": ctx.shipment.carrier},
        )


def _guard_label_ready(ctx: OrderContext, order_id: UUID) -> None:
    """
    Raise entity_not_found if the label has not been generated yet.

    Args:
        ctx:      Loaded OrderContext for the order.
        order_id: UUID used in the error message.

    Raises:
        NotFoundError (404): If shipment.label_url is None.
    """
    if not ctx.shipment.label_url:
        raise entity_not_found("Label", order_id)
