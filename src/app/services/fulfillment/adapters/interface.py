"""
Carrier Adapter Interface

Defines the abstract contract every shipping carrier integration must implement.
New carriers (UPS, FedEx, DPD) are added by subclassing CarrierAdapter —
no existing code needs to change (Open/Closed Principle).

Design:
    - CarrierAdapter is the only type callers depend on (DIP).
    - Each method has a single, well-defined responsibility (SRP).
    - LabelResult is a plain dataclass — no SDK objects leak through the boundary.
    - All methods are async and safe to call from the asyncio event loop.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from uuid import UUID

from app.shared.exceptions.base import AppException
from app.shared.exceptions.enums import ErrorCategory, ErrorCode


# ---------------------------------------------------------------------------
# Return types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LabelResult:
    """
    Returned by CarrierAdapter.create_label.

    Attributes:
        tracking_number: Carrier-issued tracking number for the shipment.
        label_data:      Raw label bytes (PDF or ZPL depending on format).
        label_format:    Format string: "pdf" or "zpl".
    """

    tracking_number: str
    label_data: bytes
    label_format: str


# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------


class CarrierError(AppException):
    """
    Raised when a carrier API call fails.

    Examples: network timeout, invalid credentials, invalid parcel dimensions.
    Maps to HTTP 502 Bad Gateway at the router layer.
    """

    def __init__(
        self,
        message: str,
        context: dict | None = None,
        original_exception: Exception | None = None,
    ) -> None:
        """
        Args:
            message:            Human-readable description of the failure.
            context:            Extra data (e.g. carrier name, order_id).
            original_exception: Underlying HTTP/SDK exception, if any.
        """
        super().__init__(
            message=message,
            error_code=ErrorCode.EXTERNAL_SERVICE_ERROR,
            category=ErrorCategory.EXTERNAL_SERVICE,
            context=context or {},
            original_exception=original_exception,
        )


# ---------------------------------------------------------------------------
# Abstract adapter
# ---------------------------------------------------------------------------


class CarrierAdapter(ABC):
    """
    Abstract interface for shipping carrier integrations.

    Implement this class to add support for a new carrier.
    All implementations must be stateless and safe to reuse across async tasks.

    Implementations:
        ManualCarrierAdapter — no-op; holds the interface consistent for
                               manual tracking-number workflows.
        DhlAdapter           — wraps the DHL Parcel DE REST API v2.
    """

    @abstractmethod
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
        Request a shipping label from the carrier API.

        Args:
            shipment_id:    Internal ShipmentDB UUID — used as reference in
                            carrier metadata for later correlation.
            order_id:       Internal OrderDB UUID — stored in carrier metadata.
            recipient_name: Full name of the recipient (first + last).
            street:         Street address line including house number.
            city:           City name.
            postal_code:    Postal/ZIP code.
            country_code:   ISO 3166-1 alpha-2 country code (e.g. "DE").
            weight_kg:      Parcel weight in kilograms.
            label_format:   Requested label format: "pdf" or "zpl".

        Returns:
            LabelResult with tracking_number, label_data bytes, and label_format.

        Raises:
            CarrierError: If the carrier API call fails for any reason.
        """
        ...
