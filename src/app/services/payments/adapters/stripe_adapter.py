"""
Stripe Payment Provider Adapter

Concrete implementation of PaymentProviderAdapter for Stripe.

Uses the official stripe-python SDK (>= 7.0) with stripe.StripeClient.
All SDK calls are blocking and are offloaded to a thread pool via
asyncio.to_thread so the FastAPI event loop is never blocked.

Configuration:
    Inject StripeAdapter via FastAPI Depends using build_stripe_adapter().
    The adapter reads stripe_secret_key and stripe_webhook_secret from
    the application Settings — never hard-code credentials.
"""

import asyncio
from uuid import UUID

import stripe

from app.shared.logger import get_logger

from .interface import (
    PaymentMethod,
    PaymentProviderAdapter,
    PaymentProviderError,
    PaymentSessionResult,
    WebhookEventResult,
    WebhookSignatureError,
)

# Maps our internal PaymentMethod enum to the Stripe payment_method_types string.
_STRIPE_METHOD_MAP: dict[PaymentMethod, str] = {
    PaymentMethod.CARD: "card",
    PaymentMethod.PAYPAL: "paypal",
    PaymentMethod.BANK_TRANSFER: "customer_balance",
}

logger = get_logger(__name__)


class StripeAdapter(PaymentProviderAdapter):
    """
    PSP adapter for Stripe.

    Wraps stripe.StripeClient for payment intent creation and cancellation,
    and stripe.Webhook for signature-verified event parsing.

    All public methods are async and safe to call from FastAPI route handlers.
    """

    def __init__(
        self,
        secret_key: str,
        webhook_secret: str,
        payment_methods: list[PaymentMethod],
        bank_transfer_country: str = "DE",
    ) -> None:
        """
        Initialise the adapter with Stripe credentials and payment method config.

        Args:
            secret_key:             Stripe secret key (sk_test_... or sk_live_...).
            webhook_secret:         Stripe webhook signing secret (whsec_...).
            payment_methods:        Payment methods to offer at checkout
                                    (e.g. [PaymentMethod.CARD, PaymentMethod.PAYPAL]).
            bank_transfer_country:  ISO 3166-1 alpha-2 country code used for EU bank
                                    transfer instructions. Only relevant when
                                    PaymentMethod.BANK_TRANSFER is in payment_methods.
                                    Defaults to "DE".

        Returns:
            None
        """
        self._client = stripe.StripeClient(api_key=secret_key)
        self._webhook_secret = webhook_secret
        self._stripe_method_types = [
            _STRIPE_METHOD_MAP[m] for m in payment_methods
        ]
        self._bank_transfer_country = bank_transfer_country.upper()
        self._has_bank_transfer = PaymentMethod.BANK_TRANSFER in payment_methods

    async def create_payment_session(
        self,
        order_id: UUID,
        amount: int,
        currency: str,
        metadata: dict[str, str],
    ) -> PaymentSessionResult:
        """
        Create a Stripe PaymentIntent for the given order.

        Merges order_id into the metadata dict so Stripe events can be
        correlated back to the internal order without a database lookup.
        Uses automatic_payment_methods so Stripe decides the best payment
        method for the customer's locale.

        Args:
            order_id: Internal order UUID — stored under metadata["order_id"].
            amount:   Amount in smallest currency unit (e.g. cents for EUR).
            currency: ISO 4217 code, case-insensitive (e.g. "EUR" or "eur").
            metadata: Caller-supplied key-value pairs merged into PSP metadata.

        Returns:
            PaymentSessionResult with provider_reference (pi_xxx) and
            client_secret for the frontend Stripe.js SDK.

        Raises:
            PaymentProviderError: On any Stripe API error.
        """
        params: stripe.PaymentIntentCreateParams = {
            "amount": amount,
            "currency": currency.lower(),
            "payment_method_types": self._stripe_method_types,
            "metadata": {"order_id": str(order_id), **metadata},
        }

        if self._has_bank_transfer:
            params["payment_method_options"] = _build_bank_transfer_options(
                self._bank_transfer_country
            )

        logger.info(
            "Creating Stripe PaymentIntent",
            order_id=str(order_id),
            amount=amount,
            currency=currency.lower(),
        )

        try:
            intent = await asyncio.to_thread(
                self._client.payment_intents.create,
                params=params,
            )
        except stripe.StripeError as exc:
            raise PaymentProviderError(
                message="Stripe PaymentIntent creation failed",
                context={"order_id": str(order_id), "stripe_error": str(exc)},
                original_exception=exc,
            ) from exc

        logger.info(
            "Stripe PaymentIntent created",
            order_id=str(order_id),
            provider_reference=intent.id,
        )

        return PaymentSessionResult(
            provider_reference=intent.id,
            client_secret=intent.client_secret,
            amount=intent.amount,
            currency=intent.currency,
        )

    async def parse_webhook_event(
        self,
        raw_payload: bytes,
        signature_header: str,
    ) -> WebhookEventResult:
        """
        Verify the Stripe-Signature header and parse the webhook payload.

        Stripe signs every webhook request with an HMAC-SHA256 signature
        over the raw body.  stripe.Webhook.construct_event re-computes the
        signature using the webhook_secret and rejects the request if it
        does not match or if the timestamp is older than 300 seconds.

        The raw_payload bytes must not be decoded or modified before this
        call — any transformation breaks the HMAC.

        Args:
            raw_payload:      Raw request body bytes as received from Stripe.
            signature_header: Value of the "Stripe-Signature" HTTP header.

        Returns:
            WebhookEventResult with event_id, event_type, provider_reference,
            and the full deserialized payload dict for audit storage.

        Raises:
            WebhookSignatureError: If the HMAC is invalid or the timestamp
                                   is outside Stripe's tolerance window.
            PaymentProviderError:  If the event type or payload structure is
                                   unexpected after successful verification.
        """
        logger.debug("Verifying Stripe webhook signature")

        try:
            event = await asyncio.to_thread(
                stripe.Webhook.construct_event,
                raw_payload,
                signature_header,
                self._webhook_secret,
            )
        except stripe.SignatureVerificationError as exc:
            raise WebhookSignatureError(
                message="Stripe webhook signature verification failed",
                context={"stripe_error": str(exc)},
                original_exception=exc,
            ) from exc
        except Exception as exc:
            raise PaymentProviderError(
                message="Failed to parse Stripe webhook payload",
                context={"stripe_error": str(exc)},
                original_exception=exc,
            ) from exc

        provider_reference = _extract_payment_intent_id(event)

        logger.info(
            "Stripe webhook event parsed",
            event_id=event.id,
            event_type=event.type,
            provider_reference=provider_reference,
        )

        return WebhookEventResult(
            event_id=event.id,
            event_type=event.type,
            provider_reference=provider_reference,
            raw_payload=event.to_dict(),
        )

    async def cancel_payment_intent(
        self,
        provider_reference: str,
    ) -> None:
        """
        Cancel a Stripe PaymentIntent, releasing any hold on the payment method.

        Should only be called on intents in status "requires_payment_method",
        "requires_capture", "requires_confirmation", or "requires_action".
        Stripe will return an error for intents already succeeded or cancelled —
        that error is wrapped and re-raised as PaymentProviderError.

        Args:
            provider_reference: Stripe PaymentIntent ID (pi_xxx).

        Returns:
            None

        Raises:
            PaymentProviderError: If Stripe rejects the cancellation.
        """
        logger.info(
            "Cancelling Stripe PaymentIntent",
            provider_reference=provider_reference,
        )

        try:
            await asyncio.to_thread(
                self._client.payment_intents.cancel,
                provider_reference,
            )
        except stripe.StripeError as exc:
            raise PaymentProviderError(
                message="Stripe PaymentIntent cancellation failed",
                context={
                    "provider_reference": provider_reference,
                    "stripe_error": str(exc),
                },
                original_exception=exc,
            ) from exc

        logger.info(
            "Stripe PaymentIntent cancelled",
            provider_reference=provider_reference,
        )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _build_bank_transfer_options(country: str) -> dict:
    """
    Build the Stripe payment_method_options dict for EU bank transfer.

    Stripe requires this block when customer_balance is in payment_method_types.
    It instructs Stripe to generate a virtual IBAN that the customer uses to
    send the wire transfer (Überweisung).

    Args:
        country: ISO 3166-1 alpha-2 country code for the virtual IBAN
                 (e.g. "DE" for a German IBAN).

    Returns:
        Dict ready to assign to PaymentIntentCreateParams["payment_method_options"].
    """
    return {
        "customer_balance": {
            "funding_type": "bank_transfer",
            "bank_transfer": {
                "type": "eu_bank_transfer",
                "eu_bank_transfer": {"country": country},
            },
        }
    }


def _extract_payment_intent_id(event: stripe.Event) -> str:
    """
    Extract the PaymentIntent ID from a Stripe event object.

    Stripe events carry their linked object inside event.data.object.
    For payment_intent.* events this is the PaymentIntent itself.
    For charge.* events the PaymentIntent ID lives in
    event.data.object.payment_intent.

    Args:
        event: Verified stripe.Event instance.

    Returns:
        PaymentIntent ID string (pi_xxx).

    Raises:
        PaymentProviderError: If the ID cannot be located in the payload.
    """
    obj = event.data.object

    if event.type.startswith("payment_intent."):
        return obj.id

    if event.type.startswith("charge."):
        payment_intent_id = getattr(obj, "payment_intent", None)
        if payment_intent_id:
            return payment_intent_id

    raise PaymentProviderError(
        message=f"Cannot extract PaymentIntent ID from event type '{event.type}'",
        context={"event_id": event.id, "event_type": event.type},
    )


# ---------------------------------------------------------------------------
# Dependency injection factory
# ---------------------------------------------------------------------------


def build_stripe_adapter(
    secret_key: str,
    webhook_secret: str,
    payment_methods: list[PaymentMethod] | None = None,
    bank_transfer_country: str = "DE",
) -> StripeAdapter:
    """
    Construct a StripeAdapter from explicit credentials.

    Intended for use with FastAPI Depends:

        async def get_payment_adapter(
            settings: Annotated[Settings, Depends(get_settings)],
        ) -> StripeAdapter:
            return build_stripe_adapter(
                secret_key=settings.stripe_secret_key,
                webhook_secret=settings.stripe_webhook_secret,
                payment_methods=[
                    PaymentMethod(m) for m in settings.stripe_payment_methods
                ],
                bank_transfer_country=settings.stripe_bank_transfer_country,
            )

    Args:
        secret_key:             Stripe secret key (sk_test_... or sk_live_...).
        webhook_secret:         Stripe webhook signing secret (whsec_...).
        payment_methods:        Payment methods to offer. Defaults to
                                [CARD, PAYPAL, BANK_TRANSFER] when None.
        bank_transfer_country:  ISO 3166-1 alpha-2 country for EU bank transfer
                                virtual IBAN. Defaults to "DE".

    Returns:
        Configured StripeAdapter instance.
    """
    if payment_methods is None:
        payment_methods = [
            PaymentMethod.CARD,
            PaymentMethod.PAYPAL,
            PaymentMethod.BANK_TRANSFER,
        ]

    return StripeAdapter(
        secret_key=secret_key,
        webhook_secret=webhook_secret,
        payment_methods=payment_methods,
        bank_transfer_country=bank_transfer_country,
    )
