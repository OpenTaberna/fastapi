"""
Manual Carrier Adapter

No-op implementation of CarrierAdapter for the "manual" carrier workflow
where an admin provides the tracking number by hand.

This adapter exists so the label job can call `adapter.create_label()` via
the same interface regardless of carrier — it simply raises CarrierError to
signal that DHL automation is not applicable, keeping the interface consistent
across all code paths.
"""

from uuid import UUID

from app.shared.logger import get_logger

from .interface import CarrierAdapter, CarrierError, LabelResult

logger = get_logger(__name__)


class ManualCarrierAdapter(CarrierAdapter):
    """
    CarrierAdapter implementation for manual (non-automated) shipments.

    The manual workflow relies on the admin entering a tracking number
    directly through the admin UI.  Label generation is a no-op — calling
    create_label raises CarrierError so the job system knows no automated
    label creation is possible for this carrier.
    """

    async def create_label(
        self,
        shipment_id: UUID,
        order_id: UUID,
        recipient_name: str,
        street: str,
        city: str,
        postal_code: str,
        country_code: str,
        weight_kg: float,
        label_format: str,
    ) -> LabelResult:
        """
        No-op: manual carrier does not support automated label creation.

        This method always raises CarrierError to prevent the label job from
        treating a missing label as a retriable failure for manual shipments.

        Args:
            shipment_id:    Internal ShipmentDB UUID.
            order_id:       Internal OrderDB UUID.
            recipient_name: Recipient full name.
            street:         Street address with house number.
            city:           City name.
            postal_code:    Postal/ZIP code.
            country_code:   ISO 3166-1 alpha-2 country code.
            weight_kg:      Parcel weight in kilograms.
            label_format:   Requested format: "pdf" or "zpl".

        Returns:
            Never returns — always raises.

        Raises:
            CarrierError: Always, because manual carrier does not generate labels.
        """
        logger.warning(
            "create_label called on ManualCarrierAdapter — not supported",
            extra={"shipment_id": str(shipment_id), "order_id": str(order_id)},
        )
        raise CarrierError(
            message="Manual carrier does not support automated label creation.",
            context={
                "shipment_id": str(shipment_id),
                "order_id": str(order_id),
                "carrier": "manual",
            },
        )
