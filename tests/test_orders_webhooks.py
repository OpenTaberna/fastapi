"""
Integration tests for the Stripe webhook endpoint.

These tests run against the actual running API and database.
Make sure the Docker containers are running before executing these tests:

    docker-compose -f docker-compose.dev.yml up -d

Endpoint covered:
    POST /v1/webhooks/stripe

What can be tested automatically (no Stripe credentials needed):
    - Missing Stripe-Signature header → 400
    - Invalid / garbage HMAC signature → 400

What requires a real Stripe signing secret (manual / CI with stripe-cli):
    - payment_intent.succeeded → order transitions to PAID
    - payment_intent.payment_failed → order transitions to CANCELLED
    - Duplicate event is handled idempotently (200, no double-processing)

    To run manually:
        stripe listen --forward-to http://localhost:8001/v1/webhooks/stripe
        stripe trigger payment_intent.succeeded
"""

import json
import subprocess
import uuid
import os

import pytest
import requests

_BASE = os.getenv("TEST_API_URL", "http://localhost:8001")
WEBHOOK_URL = f"{_BASE}/v1/webhooks/stripe"
ORDERS_URL = f"{_BASE}/v1/orders"
ITEMS_URL = f"{_BASE}/v1/items"

# A well-formed but completely fake Stripe-Signature value.
# The timestamp and v1 digest will never match any real secret.
FAKE_STRIPE_SIG = (
    "t=1700000000,v1=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _post_webhook(
    body: bytes, stripe_signature: str | None = None
) -> requests.Response:
    """POST raw bytes to the webhook endpoint with optional Stripe-Signature."""
    headers = {"Content-Type": "application/json"}
    if stripe_signature is not None:
        headers["Stripe-Signature"] = stripe_signature
    return requests.post(WEBHOOK_URL, data=body, headers=headers)


def _minimal_stripe_body(
    event_type: str = "payment_intent.succeeded",
    order_id: str | None = None,
) -> bytes:
    """Return a minimal JSON body shaped like a Stripe event."""
    payload = {
        "id": f"evt_{uuid.uuid4().hex}",
        "type": event_type,
        "data": {
            "object": {
                "id": f"pi_{uuid.uuid4().hex}",
                "object": "payment_intent",
                "amount": 1999,
                "currency": "eur",
                "metadata": {"order_id": order_id or str(uuid.uuid4())},
                "status": "succeeded",
            }
        },
    }
    return json.dumps(payload).encode()


def _psql(sql: str) -> None:
    """Execute a SQL statement inside the running Postgres container."""
    subprocess.run(
        [
            "docker",
            "exec",
            "opentaberna-db",
            "psql",
            "-U",
            "opentaberna",
            "-d",
            "opentaberna",
            "-c",
            sql,
        ],
        check=True,
        capture_output=True,
    )


# ---------------------------------------------------------------------------
# Module-scoped fixtures (reused by the skipped happy-path tests)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def customer():
    """Insert a real customer row; cascade-delete cleans up orders on teardown."""
    customer_id = str(uuid.uuid4())
    unique = uuid.uuid4().hex[:8]
    _psql(
        f"INSERT INTO customers (id, keycloak_user_id, email, first_name, last_name) "
        f"VALUES ('{customer_id}', 'kc-wh-{unique}', 'wh-{unique}@test.example', "
        f"'Webhook', 'Test');"
    )
    yield customer_id
    _psql(f"DELETE FROM customers WHERE id = '{customer_id}';")


@pytest.fixture(scope="module")
def catalogue_item():
    """Create a real catalogue item for order fixtures."""
    unique = uuid.uuid4().hex[:8].upper()
    payload = {
        "sku": f"WH-TEST-{unique}",
        "status": "active",
        "name": "Webhook Integration Test Product",
        "slug": f"wh-test-{unique.lower()}",
        "short_description": "Used by webhook integration tests",
        "description": "Temporary product for test_orders_webhooks.py",
        "brand": "TestBrand",
        "categories": [str(uuid.uuid4())],
        "price": {
            "amount": 1999,
            "currency": "EUR",
            "includes_tax": True,
            "original_amount": None,
            "tax_class": "standard",
        },
        "media": {"main_image": None, "gallery": []},
        "inventory": {
            "stock_quantity": 50,
            "stock_status": "in_stock",
            "allow_backorder": False,
        },
        "shipping": {
            "is_physical": True,
            "shipping_class": "standard",
            "weight": None,
            "dimensions": None,
        },
        "attributes": {},
        "identifiers": {
            "barcode": None,
            "manufacturer_part_number": None,
            "country_of_origin": None,
        },
        "custom": {},
        "system": {"version": 1, "source": "api", "locale": "en_US"},
    }
    response = requests.post(ITEMS_URL + "/", json=payload)
    assert response.status_code == 201, (
        f"catalogue_item fixture failed: {response.status_code} {response.json()}"
    )
    item = response.json()
    yield item
    requests.delete(f"{ITEMS_URL}/{item['uuid']}")


# ---------------------------------------------------------------------------
# TestWebhookGuards — no Stripe credentials needed
# ---------------------------------------------------------------------------


class TestWebhookGuards:
    """
    Guard checks that can be exercised without a valid Stripe signing secret.
    These should always pass in automated runs.
    """

    def test_missing_stripe_signature_returns_400(self):
        """Router rejects requests with no Stripe-Signature header."""
        body = _minimal_stripe_body()
        response = _post_webhook(body, stripe_signature=None)

        assert response.status_code == 400

    def test_invalid_stripe_signature_returns_422(self):
        """Adapter rejects a plausible-looking but wrong HMAC digest with 422."""
        body = _minimal_stripe_body()
        response = _post_webhook(body, stripe_signature=FAKE_STRIPE_SIG)

        assert response.status_code == 422

    def test_garbage_signature_returns_422(self):
        """Completely garbled Stripe-Signature header is rejected with 422."""
        body = _minimal_stripe_body()
        response = _post_webhook(body, stripe_signature="not-a-valid-sig-at-all")

        assert response.status_code == 422

    def test_empty_body_invalid_signature_returns_422(self):
        """Empty body with a fake signature is rejected with 422 by the adapter."""
        response = _post_webhook(b"", stripe_signature=FAKE_STRIPE_SIG)

        assert response.status_code == 422

    def test_malformed_json_invalid_signature_returns_422(self):
        """Non-JSON body with a fake signature is rejected with 422 by the adapter."""
        response = _post_webhook(b"this is not json", stripe_signature=FAKE_STRIPE_SIG)

        assert response.status_code == 422


# ---------------------------------------------------------------------------
# TestWebhookHappyPath — requires Stripe CLI / real webhook secret
# ---------------------------------------------------------------------------


class TestWebhookHappyPath:
    """
    Full end-to-end webhook tests that require a valid Stripe-signed event body.

    Run with:
        stripe listen --forward-to http://localhost:8001/v1/webhooks/stripe
        stripe payment_intents confirm pi_3TIADL9hz8OzCGYW1XXXXXXX --payment-method pm_card_visa

    All tests here are skipped in automated runs.
    """

    @pytest.mark.skip(
        reason="Requires valid Stripe HMAC — run manually with `stripe listen`"
    )
    def test_payment_succeeded_transitions_order_to_paid(
        self, customer, catalogue_item
    ):
        """
        payment_intent.succeeded → order.status == 'paid'.

        Steps (manual):
        1. Create a draft order via POST /v1/orders/.
        2. Checkout via POST /v1/orders/{id}/checkout — gets a PaymentIntent client_secret.
        3. Use Stripe CLI or Dashboard to trigger payment_intent.succeeded for that PI.
        4. Verify GET /v1/orders/{id} returns status == 'paid'.
        """
        pass

    @pytest.mark.skip(
        reason="Requires valid Stripe HMAC — run manually with `stripe listen`"
    )
    def test_payment_failed_transitions_order_to_cancelled(
        self, customer, catalogue_item
    ):
        """
        payment_intent.payment_failed → order.status == 'cancelled'.

        Same setup as above but trigger payment_intent.payment_failed.
        """
        pass

    @pytest.mark.skip(
        reason="Requires valid Stripe HMAC — run manually with `stripe listen`"
    )
    def test_duplicate_event_is_idempotent(self, customer, catalogue_item):
        """
        Sending the exact same Stripe event twice must return 200 both times
        and only process it once (idempotency via webhook_events inbox table).
        """
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
