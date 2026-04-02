"""
Payment Provider Adapter Interface

Defines the abstract contract that every PSP integration must implement.
New providers (PayPal, Adyen, etc.) are added by subclassing
PaymentProviderAdapter — no existing code needs to change (Open/Closed).

Design:
    - PaymentProviderAdapter is the only thing callers depend on (DIP).
    - Each method has a single, well-defined responsibility (SRP).
    - Return types are plain dataclasses, not SDK objects, so the adapter
      boundary is clean and testable without a live PSP connection.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from uuid import UUID

from app.shared.exceptions.base import AppException
from app.shared.exceptions.enums import ErrorCategory, ErrorCode


# ---------------------------------------------------------------------------
# Payment method enum
# ---------------------------------------------------------------------------


class PaymentMethod(str, Enum):
    """
    Payment methods supported across all PSP adapters.

    Each adapter maps these values to its own provider-specific identifiers.
    """

    CARD = "card"
    PAYPAL = "paypal"
    BANK_TRANSFER = "bank_transfer"


# ---------------------------------------------------------------------------
# Return types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PaymentSessionResult:
    """
    Returned by PaymentProviderAdapter.create_payment_session.

    Attributes:
        provider_reference: PSP-side payment intent / session ID (e.g. pi_xxx).
        client_secret:      Opaque token forwarded to the frontend SDK to
                            complete the payment UI flow.
        amount:             Confirmed amount in smallest currency unit (cents).
        currency:           Lowercase ISO 4217 currency code (e.g. "eur").
    """

    provider_reference: str
    client_secret: str
    amount: int
    currency: str


@dataclass(frozen=True)
class WebhookEventResult:
    """
    Returned by PaymentProviderAdapter.parse_webhook_event.

    Attributes:
        event_id:           PSP-side event ID used for idempotency (e.g. evt_xxx).
        event_type:         Provider event type string (e.g. "payment_intent.succeeded").
        provider_reference: Payment intent / session ID the event relates to.
        raw_payload:        Full deserialized event payload stored for audit.
    """

    event_id: str
    event_type: str
    provider_reference: str
    raw_payload: dict


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class PaymentProviderError(AppException):
    """
    Raised when a PSP call fails for a non-signature reason.

    Examples: network timeout, invalid API key, Stripe API error.
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
            context:            Extra data (e.g. provider name, order_id).
            original_exception: Underlying PSP SDK exception, if any.
        """
        super().__init__(
            message=message,
            error_code=ErrorCode.EXTERNAL_SERVICE_ERROR,
            category=ErrorCategory.EXTERNAL_SERVICE,
            context=context or {},
            original_exception=original_exception,
        )


class WebhookSignatureError(AppException):
    """
    Raised when a webhook payload fails signature verification.

    Maps to HTTP 400 Bad Request at the router layer — the request is
    structurally valid but the HMAC signature does not match.
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
            context:            Extra data (e.g. provider name).
            original_exception: Underlying PSP SDK exception, if any.
        """
        super().__init__(
            message=message,
            error_code=ErrorCode.INVALID_FORMAT,
            category=ErrorCategory.VALIDATION,
            context=context or {},
            original_exception=original_exception,
        )


# ---------------------------------------------------------------------------
# Abstract adapter
# ---------------------------------------------------------------------------


class PaymentProviderAdapter(ABC):
    """
    Abstract interface for payment service provider (PSP) integrations.

    Implement this class to add support for a new PSP.  All implementations
    must be stateless and safe to use from multiple asyncio tasks.

    Implementations:
        StripeAdapter — wraps the official Stripe Python SDK.
    """

    @abstractmethod
    async def create_payment_session(
        self,
        order_id: UUID,
        amount: int,
        currency: str,
        metadata: dict[str, str],
    ) -> PaymentSessionResult:
        """
        Create a payment intent / session with the PSP.

        Args:
            order_id: Internal order UUID stored in PSP metadata for correlation.
            amount:   Amount in smallest currency unit (e.g. cents for EUR/USD).
            currency: ISO 4217 currency code (e.g. "EUR").  Case-insensitive —
                      implementations must normalise to lowercase before sending.
            metadata: Arbitrary string key-value pairs attached to the PSP object
                      for later correlation (e.g. {"customer_id": "..."}).

        Returns:
            PaymentSessionResult with provider_reference and client_secret.

        Raises:
            PaymentProviderError: If the PSP call fails for any reason.
        """
        ...

    @abstractmethod
    async def parse_webhook_event(
        self,
        raw_payload: bytes,
        signature_header: str,
    ) -> WebhookEventResult:
        """
        Verify the webhook signature and parse the event payload.

        The raw bytes must be passed unmodified — any decoding before
        this call will break HMAC verification.

        Args:
            raw_payload:      Raw request body bytes, exactly as received.
            signature_header: Value of the provider-specific signature header
                              (e.g. the Stripe-Signature header value).

        Returns:
            WebhookEventResult with event_id, event_type, and provider_reference.

        Raises:
            WebhookSignatureError: If the HMAC signature is invalid or expired.
            PaymentProviderError:  If the payload cannot be parsed after
                                   successful signature verification.
        """
        ...

    @abstractmethod
    async def cancel_payment_intent(
        self,
        provider_reference: str,
    ) -> None:
        """
        Cancel an open payment intent at the PSP.

        Called when an order transitions to CANCELLED while payment is
        still PENDING — releases any hold on the customer's payment method.

        Args:
            provider_reference: PSP-side payment intent ID (e.g. Stripe pi_xxx).

        Returns:
            None

        Raises:
            PaymentProviderError: If the PSP call fails.
        """
        ...
