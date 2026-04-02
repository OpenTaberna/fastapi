"""
Tests for the PSP adapter layer (Phase 1.4).

Covers:
    - PaymentMethod enum
    - PaymentSessionResult / WebhookEventResult dataclasses
    - PaymentProviderError / WebhookSignatureError exceptions
    - _build_bank_transfer_options() helper
    - _extract_payment_intent_id() helper
    - StripeAdapter construction and all three public methods
    - build_stripe_adapter() factory

Stripe SDK calls are never made against the network. asyncio.to_thread is
patched to call its wrapped function synchronously, and stripe SDK objects
are replaced with MagicMocks so tests run without credentials.
"""

import pytest
import stripe
from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.services.payments.adapters import (
    PaymentMethod,
    PaymentProviderAdapter,
    PaymentProviderError,
    PaymentSessionResult,
    StripeAdapter,
    WebhookEventResult,
    WebhookSignatureError,
    build_stripe_adapter,
)
from app.services.payments.adapters.stripe_adapter import (
    _STRIPE_METHOD_MAP,
    _build_bank_transfer_options,
    _extract_payment_intent_id,
)
from app.shared.exceptions.enums import ErrorCategory, ErrorCode


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def all_methods() -> list[PaymentMethod]:
    """All three payment methods."""
    return [PaymentMethod.CARD, PaymentMethod.PAYPAL, PaymentMethod.BANK_TRANSFER]


@pytest.fixture
def card_only() -> list[PaymentMethod]:
    """Card-only payment methods."""
    return [PaymentMethod.CARD]


@pytest.fixture
def adapter_all(all_methods) -> StripeAdapter:
    """StripeAdapter configured with all payment methods."""
    return StripeAdapter(
        secret_key="sk_test_dummy",
        webhook_secret="whsec_dummy",
        payment_methods=all_methods,
        bank_transfer_country="DE",
    )


@pytest.fixture
def adapter_card(card_only) -> StripeAdapter:
    """StripeAdapter configured with card only."""
    return StripeAdapter(
        secret_key="sk_test_dummy",
        webhook_secret="whsec_dummy",
        payment_methods=card_only,
    )


@pytest.fixture
def fake_to_thread():
    """
    Replacement for asyncio.to_thread that runs the wrapped function
    synchronously. Allows tests to inspect Stripe SDK call arguments without
    spawning a thread pool or touching the network.
    """

    async def _call_sync(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    return _call_sync


@pytest.fixture
def mock_payment_intent() -> MagicMock:
    """Minimal fake stripe.PaymentIntent returned by payment_intents.create."""
    intent = MagicMock()
    intent.id = "pi_test_abc123"
    intent.client_secret = "pi_test_abc123_secret_xyz"
    intent.amount = 4999
    intent.currency = "eur"
    return intent


def _make_stripe_event(event_type: str, obj: MagicMock) -> MagicMock:
    """Build a minimal fake stripe.Event for the given type and data object."""
    event = MagicMock()
    event.id = "evt_test_001"
    event.type = event_type
    event.data = MagicMock()
    event.data.object = obj
    event.to_dict.return_value = {"id": event.id, "type": event_type}
    return event


# ---------------------------------------------------------------------------
# PaymentMethod enum
# ---------------------------------------------------------------------------


class TestPaymentMethod:
    def test_values_match_expected_strings(self):
        """
        Each PaymentMethod must map to the exact string Stripe expects (or our
        internal canonical name).
        """
        assert PaymentMethod.CARD == "card"
        assert PaymentMethod.PAYPAL == "paypal"
        assert PaymentMethod.BANK_TRANSFER == "bank_transfer"

    def test_stripe_method_map_covers_all_members(self):
        """_STRIPE_METHOD_MAP must have an entry for every PaymentMethod."""
        for method in PaymentMethod:
            assert method in _STRIPE_METHOD_MAP, (
                f"{method} is missing from _STRIPE_METHOD_MAP"
            )

    def test_bank_transfer_maps_to_customer_balance(self):
        """Stripe represents bank transfer as 'customer_balance'."""
        assert _STRIPE_METHOD_MAP[PaymentMethod.BANK_TRANSFER] == "customer_balance"

    def test_paypal_maps_to_paypal(self):
        assert _STRIPE_METHOD_MAP[PaymentMethod.PAYPAL] == "paypal"

    def test_card_maps_to_card(self):
        assert _STRIPE_METHOD_MAP[PaymentMethod.CARD] == "card"


# ---------------------------------------------------------------------------
# Return-type dataclasses
# ---------------------------------------------------------------------------


class TestPaymentSessionResult:
    def test_stores_all_fields(self):
        result = PaymentSessionResult(
            provider_reference="pi_xxx",
            client_secret="pi_xxx_secret",
            amount=1000,
            currency="eur",
        )
        assert result.provider_reference == "pi_xxx"
        assert result.client_secret == "pi_xxx_secret"
        assert result.amount == 1000
        assert result.currency == "eur"

    def test_is_immutable(self):
        """frozen=True must prevent mutation."""
        result = PaymentSessionResult(
            provider_reference="pi_xxx",
            client_secret="secret",
            amount=100,
            currency="eur",
        )
        with pytest.raises(Exception):
            result.amount = 999  # type: ignore[misc]


class TestWebhookEventResult:
    def test_stores_all_fields(self):
        payload = {"id": "evt_1", "type": "payment_intent.succeeded"}
        result = WebhookEventResult(
            event_id="evt_1",
            event_type="payment_intent.succeeded",
            provider_reference="pi_xxx",
            raw_payload=payload,
        )
        assert result.event_id == "evt_1"
        assert result.event_type == "payment_intent.succeeded"
        assert result.provider_reference == "pi_xxx"
        assert result.raw_payload is payload

    def test_is_immutable(self):
        result = WebhookEventResult(
            event_id="evt_1",
            event_type="payment_intent.succeeded",
            provider_reference="pi_xxx",
            raw_payload={},
        )
        with pytest.raises(Exception):
            result.event_id = "evt_2"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class TestPaymentProviderError:
    def test_error_code_is_external_service_error(self):
        exc = PaymentProviderError(message="PSP down")
        assert exc.error_code == ErrorCode.EXTERNAL_SERVICE_ERROR

    def test_category_is_external_service(self):
        exc = PaymentProviderError(message="PSP down")
        assert exc.category == ErrorCategory.EXTERNAL_SERVICE

    def test_message_is_preserved(self):
        exc = PaymentProviderError(message="timeout after 30s")
        assert exc.message == "timeout after 30s"

    def test_context_stored(self):
        exc = PaymentProviderError(message="err", context={"order_id": "123"})
        assert exc.context["order_id"] == "123"

    def test_wraps_original_exception(self):
        cause = ValueError("stripe blew up")
        exc = PaymentProviderError(message="err", original_exception=cause)
        assert exc.original_exception is cause


class TestWebhookSignatureError:
    def test_error_code_is_invalid_format(self):
        exc = WebhookSignatureError(message="bad sig")
        assert exc.error_code == ErrorCode.INVALID_FORMAT

    def test_category_is_validation(self):
        exc = WebhookSignatureError(message="bad sig")
        assert exc.category == ErrorCategory.VALIDATION

    def test_is_client_error(self):
        exc = WebhookSignatureError(message="bad sig")
        assert exc.category.is_client_error()


# ---------------------------------------------------------------------------
# _build_bank_transfer_options()
# ---------------------------------------------------------------------------


class TestBuildBankTransferOptions:
    def test_returns_customer_balance_key(self):
        opts = _build_bank_transfer_options("DE")
        assert "customer_balance" in opts

    def test_funding_type_is_bank_transfer(self):
        opts = _build_bank_transfer_options("DE")
        assert opts["customer_balance"]["funding_type"] == "bank_transfer"

    def test_eu_bank_transfer_type(self):
        opts = _build_bank_transfer_options("DE")
        assert opts["customer_balance"]["bank_transfer"]["type"] == "eu_bank_transfer"

    def test_country_is_passed_through(self):
        opts = _build_bank_transfer_options("NL")
        country = opts["customer_balance"]["bank_transfer"]["eu_bank_transfer"][
            "country"
        ]
        assert country == "NL"

    def test_different_country(self):
        opts = _build_bank_transfer_options("FR")
        country = opts["customer_balance"]["bank_transfer"]["eu_bank_transfer"][
            "country"
        ]
        assert country == "FR"


# ---------------------------------------------------------------------------
# _extract_payment_intent_id()
# ---------------------------------------------------------------------------


class TestExtractPaymentIntentId:
    def test_payment_intent_event_returns_object_id(self):
        """payment_intent.* events carry the PI as the event object itself."""
        obj = MagicMock()
        obj.id = "pi_test_001"
        event = _make_stripe_event("payment_intent.succeeded", obj)

        result = _extract_payment_intent_id(event)

        assert result == "pi_test_001"

    def test_payment_intent_requires_action_event(self):
        obj = MagicMock()
        obj.id = "pi_test_002"
        event = _make_stripe_event("payment_intent.requires_action", obj)

        assert _extract_payment_intent_id(event) == "pi_test_002"

    def test_charge_event_uses_payment_intent_field(self):
        """charge.* events carry the PI ID in charge.payment_intent."""
        obj = MagicMock()
        obj.payment_intent = "pi_test_003"
        event = _make_stripe_event("charge.succeeded", obj)

        assert _extract_payment_intent_id(event) == "pi_test_003"

    def test_charge_event_without_payment_intent_raises(self):
        obj = MagicMock(spec=[])  # no attributes
        event = _make_stripe_event("charge.updated", obj)

        with pytest.raises(PaymentProviderError):
            _extract_payment_intent_id(event)

    def test_unsupported_event_type_raises(self):
        event = _make_stripe_event("customer.created", MagicMock())

        with pytest.raises(PaymentProviderError) as exc_info:
            _extract_payment_intent_id(event)

        assert "customer.created" in exc_info.value.message


# ---------------------------------------------------------------------------
# StripeAdapter.__init__
# ---------------------------------------------------------------------------


class TestStripeAdapterInit:
    def test_is_payment_provider_adapter(self, adapter_all):
        assert isinstance(adapter_all, PaymentProviderAdapter)

    def test_all_methods_mapped_to_stripe_strings(self, adapter_all):
        assert adapter_all._stripe_method_types == [
            "card",
            "paypal",
            "customer_balance",
        ]

    def test_card_only_excludes_paypal_and_bank_transfer(self, adapter_card):
        assert adapter_card._stripe_method_types == ["card"]

    def test_has_bank_transfer_true_when_included(self, adapter_all):
        assert adapter_all._has_bank_transfer is True

    def test_has_bank_transfer_false_when_excluded(self, adapter_card):
        assert adapter_card._has_bank_transfer is False

    def test_country_is_uppercased(self):
        adapter = StripeAdapter(
            secret_key="sk_test_x",
            webhook_secret="whsec_x",
            payment_methods=[PaymentMethod.BANK_TRANSFER],
            bank_transfer_country="de",
        )
        assert adapter._bank_transfer_country == "DE"

    def test_paypal_without_bank_transfer(self):
        adapter = StripeAdapter(
            secret_key="sk_test_x",
            webhook_secret="whsec_x",
            payment_methods=[PaymentMethod.CARD, PaymentMethod.PAYPAL],
        )
        assert adapter._stripe_method_types == ["card", "paypal"]
        assert adapter._has_bank_transfer is False


# ---------------------------------------------------------------------------
# StripeAdapter.create_payment_session
# ---------------------------------------------------------------------------


class TestStripeAdapterCreatePaymentSession:
    async def test_returns_payment_session_result(
        self, adapter_card, fake_to_thread, mock_payment_intent
    ):
        """Happy path: correct PaymentSessionResult is returned."""
        adapter_card._client.v1.payment_intents.create = MagicMock(
            return_value=mock_payment_intent
        )

        with patch(
            "app.services.payments.adapters.stripe_adapter.asyncio.to_thread",
            side_effect=fake_to_thread,
        ):
            result = await adapter_card.create_payment_session(
                order_id=uuid4(),
                amount=4999,
                currency="EUR",
                metadata={},
            )

        assert isinstance(result, PaymentSessionResult)
        assert result.provider_reference == mock_payment_intent.id
        assert result.client_secret == mock_payment_intent.client_secret
        assert result.amount == mock_payment_intent.amount
        assert result.currency == mock_payment_intent.currency

    async def test_currency_is_lowercased(
        self, adapter_card, fake_to_thread, mock_payment_intent
    ):
        """Currency must be normalised to lowercase before sending to Stripe."""
        adapter_card._client.v1.payment_intents.create = MagicMock(
            return_value=mock_payment_intent
        )

        with patch(
            "app.services.payments.adapters.stripe_adapter.asyncio.to_thread",
            side_effect=fake_to_thread,
        ):
            await adapter_card.create_payment_session(
                order_id=uuid4(), amount=100, currency="EUR", metadata={}
            )

        call_params = adapter_card._client.v1.payment_intents.create.call_args.kwargs[
            "params"
        ]
        assert call_params["currency"] == "eur"

    async def test_order_id_in_metadata(
        self, adapter_card, fake_to_thread, mock_payment_intent
    ):
        """order_id must be stored in the Stripe metadata for correlation."""
        order_id = uuid4()
        adapter_card._client.v1.payment_intents.create = MagicMock(
            return_value=mock_payment_intent
        )

        with patch(
            "app.services.payments.adapters.stripe_adapter.asyncio.to_thread",
            side_effect=fake_to_thread,
        ):
            await adapter_card.create_payment_session(
                order_id=order_id, amount=100, currency="eur", metadata={}
            )

        call_params = adapter_card._client.v1.payment_intents.create.call_args.kwargs[
            "params"
        ]
        assert call_params["metadata"]["order_id"] == str(order_id)

    async def test_caller_metadata_merged(
        self, adapter_card, fake_to_thread, mock_payment_intent
    ):
        """Extra metadata from the caller must be included alongside order_id."""
        adapter_card._client.v1.payment_intents.create = MagicMock(
            return_value=mock_payment_intent
        )

        with patch(
            "app.services.payments.adapters.stripe_adapter.asyncio.to_thread",
            side_effect=fake_to_thread,
        ):
            await adapter_card.create_payment_session(
                order_id=uuid4(),
                amount=100,
                currency="eur",
                metadata={"customer_id": "cus_xyz"},
            )

        call_params = adapter_card._client.v1.payment_intents.create.call_args.kwargs[
            "params"
        ]
        assert call_params["metadata"]["customer_id"] == "cus_xyz"

    async def test_bank_transfer_options_included_when_method_active(
        self, adapter_all, fake_to_thread, mock_payment_intent
    ):
        """payment_method_options must be present when BANK_TRANSFER is enabled."""
        adapter_all._client.v1.payment_intents.create = MagicMock(
            return_value=mock_payment_intent
        )

        with patch(
            "app.services.payments.adapters.stripe_adapter.asyncio.to_thread",
            side_effect=fake_to_thread,
        ):
            await adapter_all.create_payment_session(
                order_id=uuid4(), amount=100, currency="eur", metadata={}
            )

        call_params = adapter_all._client.v1.payment_intents.create.call_args.kwargs[
            "params"
        ]
        assert "payment_method_options" in call_params
        assert "customer_balance" in call_params["payment_method_options"]

    async def test_bank_transfer_options_absent_when_method_inactive(
        self, adapter_card, fake_to_thread, mock_payment_intent
    ):
        """payment_method_options must NOT be present when bank transfer is off."""
        adapter_card._client.v1.payment_intents.create = MagicMock(
            return_value=mock_payment_intent
        )

        with patch(
            "app.services.payments.adapters.stripe_adapter.asyncio.to_thread",
            side_effect=fake_to_thread,
        ):
            await adapter_card.create_payment_session(
                order_id=uuid4(), amount=100, currency="eur", metadata={}
            )

        call_params = adapter_card._client.v1.payment_intents.create.call_args.kwargs[
            "params"
        ]
        assert "payment_method_options" not in call_params

    async def test_stripe_error_raises_payment_provider_error(
        self, adapter_card, fake_to_thread
    ):
        """Any stripe.StripeError must be wrapped as PaymentProviderError."""
        adapter_card._client.v1.payment_intents.create = MagicMock(
            side_effect=stripe.StripeError("network error")
        )

        with patch(
            "app.services.payments.adapters.stripe_adapter.asyncio.to_thread",
            side_effect=fake_to_thread,
        ):
            with pytest.raises(PaymentProviderError) as exc_info:
                await adapter_card.create_payment_session(
                    order_id=uuid4(), amount=100, currency="eur", metadata={}
                )

        assert "PaymentIntent creation failed" in exc_info.value.message

    async def test_payment_method_types_sent_to_stripe(
        self, adapter_all, fake_to_thread, mock_payment_intent
    ):
        """Stripe must receive the correctly mapped payment_method_types list."""
        adapter_all._client.v1.payment_intents.create = MagicMock(
            return_value=mock_payment_intent
        )

        with patch(
            "app.services.payments.adapters.stripe_adapter.asyncio.to_thread",
            side_effect=fake_to_thread,
        ):
            await adapter_all.create_payment_session(
                order_id=uuid4(), amount=100, currency="eur", metadata={}
            )

        call_params = adapter_all._client.v1.payment_intents.create.call_args.kwargs[
            "params"
        ]
        assert call_params["payment_method_types"] == [
            "card",
            "paypal",
            "customer_balance",
        ]


# ---------------------------------------------------------------------------
# StripeAdapter.parse_webhook_event
# ---------------------------------------------------------------------------


class TestStripeAdapterParseWebhookEvent:
    async def test_returns_webhook_event_result_for_payment_intent_event(
        self, adapter_card, fake_to_thread
    ):
        """Happy path: payment_intent.succeeded returns a correct WebhookEventResult."""
        obj = MagicMock()
        obj.id = "pi_test_007"
        fake_event = _make_stripe_event("payment_intent.succeeded", obj)

        with (
            patch(
                "app.services.payments.adapters.stripe_adapter.asyncio.to_thread",
                side_effect=fake_to_thread,
            ),
            patch(
                "app.services.payments.adapters.stripe_adapter.stripe.Webhook.construct_event",
                return_value=fake_event,
            ),
        ):
            result = await adapter_card.parse_webhook_event(
                raw_payload=b'{"id":"evt_1"}',
                signature_header="t=123,v1=abc",
            )

        assert isinstance(result, WebhookEventResult)
        assert result.event_id == "evt_test_001"
        assert result.event_type == "payment_intent.succeeded"
        assert result.provider_reference == "pi_test_007"

    async def test_returns_webhook_event_result_for_charge_event(
        self, adapter_card, fake_to_thread
    ):
        """charge.succeeded must extract provider_reference from charge.payment_intent."""
        obj = MagicMock()
        obj.payment_intent = "pi_test_charge"
        fake_event = _make_stripe_event("charge.succeeded", obj)

        with (
            patch(
                "app.services.payments.adapters.stripe_adapter.asyncio.to_thread",
                side_effect=fake_to_thread,
            ),
            patch(
                "app.services.payments.adapters.stripe_adapter.stripe.Webhook.construct_event",
                return_value=fake_event,
            ),
        ):
            result = await adapter_card.parse_webhook_event(
                raw_payload=b"{}",
                signature_header="t=1,v1=x",
            )

        assert result.provider_reference == "pi_test_charge"

    async def test_raw_payload_included_in_result(self, adapter_card, fake_to_thread):
        obj = MagicMock()
        obj.id = "pi_abc"
        fake_event = _make_stripe_event("payment_intent.succeeded", obj)
        fake_event.to_dict.return_value = {"id": "evt_test_001", "amount": 500}

        with (
            patch(
                "app.services.payments.adapters.stripe_adapter.asyncio.to_thread",
                side_effect=fake_to_thread,
            ),
            patch(
                "app.services.payments.adapters.stripe_adapter.stripe.Webhook.construct_event",
                return_value=fake_event,
            ),
        ):
            result = await adapter_card.parse_webhook_event(
                raw_payload=b"{}", signature_header="t=1,v1=x"
            )

        assert result.raw_payload["amount"] == 500

    async def test_invalid_signature_raises_webhook_signature_error(
        self, adapter_card, fake_to_thread
    ):
        """stripe.SignatureVerificationError must become WebhookSignatureError."""
        with (
            patch(
                "app.services.payments.adapters.stripe_adapter.asyncio.to_thread",
                side_effect=fake_to_thread,
            ),
            patch(
                "app.services.payments.adapters.stripe_adapter.stripe.Webhook.construct_event",
                side_effect=stripe.SignatureVerificationError("bad sig", b""),
            ),
        ):
            with pytest.raises(WebhookSignatureError) as exc_info:
                await adapter_card.parse_webhook_event(
                    raw_payload=b"tampered", signature_header="t=1,v1=wrong"
                )

        assert "signature verification failed" in exc_info.value.message

    async def test_malformed_payload_raises_payment_provider_error(
        self, adapter_card, fake_to_thread
    ):
        """Any non-signature exception during parsing becomes PaymentProviderError."""
        with (
            patch(
                "app.services.payments.adapters.stripe_adapter.asyncio.to_thread",
                side_effect=fake_to_thread,
            ),
            patch(
                "app.services.payments.adapters.stripe_adapter.stripe.Webhook.construct_event",
                side_effect=ValueError("unexpected payload"),
            ),
        ):
            with pytest.raises(PaymentProviderError) as exc_info:
                await adapter_card.parse_webhook_event(
                    raw_payload=b"garbage", signature_header="t=1,v1=x"
                )

        assert "Failed to parse" in exc_info.value.message


# ---------------------------------------------------------------------------
# StripeAdapter.cancel_payment_intent
# ---------------------------------------------------------------------------


class TestStripeAdapterCancelPaymentIntent:
    async def test_happy_path_returns_none(self, adapter_card, fake_to_thread):
        """Successful cancellation returns None."""
        adapter_card._client.v1.payment_intents.cancel = MagicMock(return_value=None)

        with patch(
            "app.services.payments.adapters.stripe_adapter.asyncio.to_thread",
            side_effect=fake_to_thread,
        ):
            result = await adapter_card.cancel_payment_intent("pi_test_123")

        assert result is None

    async def test_correct_provider_reference_sent(self, adapter_card, fake_to_thread):
        """The provider_reference must be forwarded to the Stripe SDK unchanged."""
        adapter_card._client.v1.payment_intents.cancel = MagicMock(return_value=None)

        with patch(
            "app.services.payments.adapters.stripe_adapter.asyncio.to_thread",
            side_effect=fake_to_thread,
        ):
            await adapter_card.cancel_payment_intent("pi_exact_ref")

        adapter_card._client.v1.payment_intents.cancel.assert_called_once_with(
            "pi_exact_ref"
        )

    async def test_stripe_error_raises_payment_provider_error(
        self, adapter_card, fake_to_thread
    ):
        """stripe.StripeError from cancel must become PaymentProviderError."""
        adapter_card._client.v1.payment_intents.cancel = MagicMock(
            side_effect=stripe.StripeError("already cancelled")
        )

        with patch(
            "app.services.payments.adapters.stripe_adapter.asyncio.to_thread",
            side_effect=fake_to_thread,
        ):
            with pytest.raises(PaymentProviderError) as exc_info:
                await adapter_card.cancel_payment_intent("pi_already_done")

        assert "cancellation failed" in exc_info.value.message
        assert exc_info.value.context["provider_reference"] == "pi_already_done"


# ---------------------------------------------------------------------------
# build_stripe_adapter()
# ---------------------------------------------------------------------------


class TestBuildStripeAdapter:
    def test_default_includes_all_three_methods(self):
        """Without explicit payment_methods, all three are enabled."""
        adapter = build_stripe_adapter("sk_test_x", "whsec_x")
        assert adapter._stripe_method_types == ["card", "paypal", "customer_balance"]

    def test_default_has_bank_transfer(self):
        adapter = build_stripe_adapter("sk_test_x", "whsec_x")
        assert adapter._has_bank_transfer is True

    def test_custom_methods_override_default(self):
        adapter = build_stripe_adapter(
            "sk_test_x",
            "whsec_x",
            payment_methods=[PaymentMethod.CARD],
        )
        assert adapter._stripe_method_types == ["card"]

    def test_custom_country_is_applied(self):
        adapter = build_stripe_adapter(
            "sk_test_x",
            "whsec_x",
            bank_transfer_country="nl",
        )
        assert adapter._bank_transfer_country == "NL"

    def test_returns_stripe_adapter_instance(self):
        adapter = build_stripe_adapter("sk_test_x", "whsec_x")
        assert isinstance(adapter, StripeAdapter)
        assert isinstance(adapter, PaymentProviderAdapter)
