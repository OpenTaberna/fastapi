"""
DHL Parcel DE REST API Adapter

Concrete CarrierAdapter implementation for DHL Parcel Germany (REST API v2).

Authentication:
    DHL Parcel DE uses HTTP Basic Auth (client_id:client_secret) on every
    request — there is no separate token exchange step in v2.

Label formats:
    "pdf"  → PDF 105x208mm or A4 layout depending on DHL product.
    "zpl"  → ZPL II format for thermal label printers (Zebra, etc.).

Reference:
    https://developer.dhl.com/api-reference/parcel-de-shipping-v2

Configuration:
    Build via build_dhl_adapter() and inject via context passed to ARQ jobs.
    Credentials are read from Settings — never hard-coded.
"""

import base64
from uuid import UUID

import httpx

from app.shared.logger import get_logger

from .interface import CarrierAdapter, CarrierError, LabelResult

logger = get_logger(__name__)

# DHL product code for standard domestic parcel (V01PAK = Paket national)
_DHL_PRODUCT = "V01PAK"

# Map our label_format strings to DHL's docFormat query parameter values
_LABEL_FORMAT_MAP: dict[str, str] = {
    "pdf": "PDF",
    "zpl": "ZPL2",
}


class DhlAdapter(CarrierAdapter):
    """
    CarrierAdapter implementation for DHL Parcel DE REST API v2.

    Uses httpx for async HTTP calls.  All requests are authenticated with
    HTTP Basic Auth using the DHL client_id and client_secret.

    Attributes:
        _base_url:       DHL API base URL (sandbox or production).
        _billing_number: DHL EKP billing number used in label requests.
        _auth_header:    Pre-computed Base64 Basic Auth header value.
    """

    def __init__(
        self,
        base_url: str,
        client_id: str,
        client_secret: str,
        billing_number: str,
    ) -> None:
        """
        Initialise the adapter with DHL API credentials.

        Args:
            base_url:       DHL Parcel DE REST API base URL.
            client_id:      DHL API OAuth2 client ID (used as Basic Auth user).
            client_secret:  DHL API OAuth2 client secret (used as Basic Auth password).
            billing_number: DHL EKP billing number (Kundennummer) for label requests.
        """
        self._base_url = base_url.rstrip("/")
        self._billing_number = billing_number
        raw = f"{client_id}:{client_secret}".encode()
        self._auth_header = f"Basic {base64.b64encode(raw).decode()}"

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
        Request a DHL shipping label for the given recipient and parcel.

        Calls POST /orders on the DHL Parcel DE REST API v2 and returns the
        tracking number and label bytes extracted from the JSON response.

        Args:
            shipment_id:    Internal ShipmentDB UUID — stored in DHL customerReference.
            order_id:       Internal OrderDB UUID — stored in DHL customerReference2.
            recipient_name: Recipient full name.
            street:         Street address with house number (e.g. "Musterstraße 1").
            city:           City (e.g. "Berlin").
            postal_code:    German postal code (e.g. "10115").
            country_code:   ISO 3166-1 alpha-2 country code (e.g. "DE").
            weight_kg:      Parcel weight in kilograms.
            label_format:   "pdf" or "zpl".

        Returns:
            LabelResult with tracking_number, label_data bytes, and label_format.

        Raises:
            CarrierError: On HTTP errors, DHL API errors, or unexpected response format.
        """
        doc_format = _label_format_to_dhl(label_format)
        payload = _build_dhl_payload(
            billing_number=self._billing_number,
            shipment_id=shipment_id,
            order_id=order_id,
            recipient_name=recipient_name,
            street=street,
            city=city,
            postal_code=postal_code,
            country_code=country_code,
            weight_kg=weight_kg,
        )

        logger.info(
            "Requesting DHL label",
            extra={
                "shipment_id": str(shipment_id),
                "order_id": str(order_id),
                "label_format": label_format,
            },
        )

        response_json = await _post_dhl_order(
            base_url=self._base_url,
            auth_header=self._auth_header,
            payload=payload,
            doc_format=doc_format,
        )

        tracking_number, label_data = _extract_label_from_response(
            response_json=response_json,
            label_format=label_format,
            shipment_id=shipment_id,
        )

        logger.info(
            "DHL label created",
            extra={
                "shipment_id": str(shipment_id),
                "tracking_number": tracking_number,
            },
        )

        return LabelResult(
            tracking_number=tracking_number,
            label_data=label_data,
            label_format=label_format,
        )


# ---------------------------------------------------------------------------
# Private helpers — each does exactly one thing
# ---------------------------------------------------------------------------


def _label_format_to_dhl(label_format: str) -> str:
    """
    Map the internal label_format string to the DHL docFormat parameter.

    Args:
        label_format: "pdf" or "zpl".

    Returns:
        DHL docFormat value: "PDF" or "ZPL2".

    Raises:
        CarrierError: If the format is not supported.
    """
    doc_format = _LABEL_FORMAT_MAP.get(label_format.lower())
    if doc_format is None:
        raise CarrierError(
            message=f"Unsupported label format: {label_format!r}",
            context={
                "label_format": label_format,
                "supported": list(_LABEL_FORMAT_MAP),
            },
        )
    return doc_format


def _build_dhl_payload(
    billing_number: str,
    shipment_id: UUID,
    order_id: UUID,
    recipient_name: str,
    street: str,
    city: str,
    postal_code: str,
    country_code: str,
    weight_kg: float,
) -> dict:
    """
    Build the JSON payload for DHL POST /orders.

    Args:
        billing_number: DHL EKP billing number.
        shipment_id:    Internal ShipmentDB UUID.
        order_id:       Internal OrderDB UUID.
        recipient_name: Recipient full name.
        street:         Street address with house number.
        city:           City name.
        postal_code:    Postal/ZIP code.
        country_code:   ISO 3166-1 alpha-2 country code.
        weight_kg:      Parcel weight in kilograms.

    Returns:
        Dict ready to serialize as the DHL POST /orders request body.
    """
    return {
        "profile": "STANDARD_GRUPPENPROFIL",
        "shipments": [
            {
                "product": _DHL_PRODUCT,
                "billingNumber": billing_number,
                "customerReference": str(shipment_id),
                "customerReference2": str(order_id),
                "consignee": {
                    "name1": recipient_name,
                    "addressStreet": street,
                    "postalCode": postal_code,
                    "city": city,
                    "country": country_code.upper(),
                },
                "details": {
                    "weight": {"uom": "kg", "value": weight_kg},
                },
            }
        ],
    }


async def _post_dhl_order(
    base_url: str,
    auth_header: str,
    payload: dict,
    doc_format: str,
) -> dict:
    """
    POST the shipment order to the DHL API and return the parsed JSON response.

    Args:
        base_url:     DHL API base URL.
        auth_header:  Pre-computed "Basic <base64>" authorization header value.
        payload:      Request body dict to send as JSON.
        doc_format:   DHL docFormat query parameter value ("PDF" or "ZPL2").

    Returns:
        Parsed JSON response dict from DHL.

    Raises:
        CarrierError: On HTTP errors or non-200 DHL status codes.
    """
    url = f"{base_url}/orders"
    headers = {
        "Authorization": auth_header,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    params = {"docFormat": doc_format, "validate": "false"}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url, json=payload, headers=headers, params=params
            )
    except httpx.RequestError as exc:
        raise CarrierError(
            message="DHL API request failed (network error)",
            context={"url": url, "error": str(exc)},
            original_exception=exc,
        ) from exc

    if response.status_code not in (200, 201):
        raise CarrierError(
            message=f"DHL API returned HTTP {response.status_code}",
            context={
                "url": url,
                "status_code": response.status_code,
                "body": response.text[:500],
            },
        )

    try:
        return response.json()
    except Exception as exc:
        raise CarrierError(
            message="DHL API response is not valid JSON",
            context={"url": url, "body": response.text[:500]},
            original_exception=exc,
        ) from exc


def _extract_label_from_response(
    response_json: dict,
    label_format: str,
    shipment_id: UUID,
) -> tuple[str, bytes]:
    """
    Extract the tracking number and label bytes from the DHL response body.

    DHL returns labels as Base64-encoded strings inside the items array.

    Args:
        response_json: Parsed DHL POST /orders response dict.
        label_format:  "pdf" or "zpl" — determines which field to read.
        shipment_id:   Internal UUID used in error context.

    Returns:
        Tuple of (tracking_number, label_bytes).

    Raises:
        CarrierError: If the expected fields are missing from the response.
    """
    try:
        item = response_json["items"][0]
        tracking_number: str = item["shipmentTrackingNumber"]
        label_b64: str = item["label"]["b64"]
    except (KeyError, IndexError, TypeError) as exc:
        raise CarrierError(
            message="Unexpected DHL API response structure",
            context={
                "shipment_id": str(shipment_id),
                "response_keys": list(response_json),
            },
            original_exception=exc,
        ) from exc

    try:
        label_data = base64.b64decode(label_b64)
    except Exception as exc:
        raise CarrierError(
            message="Failed to decode DHL label Base64 data",
            context={"shipment_id": str(shipment_id)},
            original_exception=exc,
        ) from exc

    return tracking_number, label_data


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def build_dhl_adapter(
    base_url: str,
    client_id: str,
    client_secret: str,
    billing_number: str,
) -> DhlAdapter:
    """
    Construct a DhlAdapter from explicit credentials.

    Intended for use in the ARQ worker context factory:

        async def startup(ctx: dict) -> None:
            settings = get_settings()
            ctx["dhl_adapter"] = build_dhl_adapter(
                base_url=settings.dhl_api_base_url,
                client_id=settings.dhl_client_id,
                client_secret=settings.dhl_client_secret,
                billing_number=settings.dhl_billing_number,
            )

    Args:
        base_url:       DHL Parcel DE REST API base URL (sandbox or production).
        client_id:      DHL API client ID.
        client_secret:  DHL API client secret.
        billing_number: DHL EKP billing number.

    Returns:
        Configured DhlAdapter instance.
    """
    return DhlAdapter(
        base_url=base_url,
        client_id=client_id,
        client_secret=client_secret,
        billing_number=billing_number,
    )
