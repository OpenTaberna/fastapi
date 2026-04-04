"""
Integration tests for Phase 3 — Fulfillment label endpoints.

These tests run against the actual running API and database.
Make sure the Docker containers are running before executing:

    docker-compose -f docker-compose.dev.yml up -d

Endpoints covered:
    POST  /v1/admin/orders/{id}/label  — trigger_label_job
    GET   /v1/admin/orders/{id}/label  — download_label

Auth note:
    Admin endpoints accept the dev-only X-Admin-Key header with any non-empty
    value. Tests send "test-admin-key".

DB note:
    Fixtures insert rows directly via docker exec psql so we can control
    exactly which carrier and label_url state each scenario requires.
    FK CASCADE on orders.customer_id cleans up orders and shipments when the
    customer fixture is torn down.

MinIO note:
    The download happy-path test (GET returning 200) requires MinIO running
    AND a real label stored in the bucket.  That test is marked skip and
    intended for manual end-to-end verification after the worker has run.
"""

import subprocess
import uuid
import os

import pytest
import requests

_BASE = os.getenv("TEST_API_URL", "http://localhost:8000")
ADMIN_URL = f"{_BASE}/v1/admin/orders"

_ADMIN_HEADERS = {"X-Admin-Key": "test-admin-key"}


# ---------------------------------------------------------------------------
# DB helper — direct psql access (same pattern as other integration tests)
# ---------------------------------------------------------------------------


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
# Module-scoped fixtures — shared customer + orders for the full module
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def fulfillment_customer():
    """
    Insert a customer row used by all fulfillment integration tests.

    Deleted at teardown; FK cascade removes orders and shipments automatically.
    """
    customer_id = str(uuid.uuid4())
    unique = uuid.uuid4().hex[:8]
    _psql(
        f"INSERT INTO customers (id, keycloak_user_id, email, first_name, last_name) "
        f"VALUES ('{customer_id}', 'kc-fulfil-{unique}', "
        f"'{unique}@fulfil-test.example', 'Fulfil', 'Tester');"
    )
    yield customer_id
    # shipments.order_id FK is RESTRICT — delete shipments first, then customer
    _psql(
        f"DELETE FROM shipments WHERE order_id IN "
        f"(SELECT id FROM orders WHERE customer_id = '{customer_id}');"
    )
    _psql(f"DELETE FROM customers WHERE id = '{customer_id}';")


@pytest.fixture(scope="module")
def order_with_dhl_shipment(fulfillment_customer):
    """
    Insert an order and a DHL shipment for testing POST /label (202 path).

    The shipment has carrier='dhl' and no label_url — simulating a freshly
    created shipment waiting for the ARQ worker to generate a label.
    """
    order_id = str(uuid.uuid4())
    shipment_id = str(uuid.uuid4())

    _psql(
        f"INSERT INTO orders (id, customer_id, status, total_amount, currency) "
        f"VALUES ('{order_id}', '{fulfillment_customer}', 'ready_to_ship', 4999, 'EUR');"
    )
    _psql(
        f"INSERT INTO shipments (id, order_id, carrier, status) "
        f"VALUES ('{shipment_id}', '{order_id}', 'dhl', 'pending');"
    )
    yield {"order_id": order_id, "shipment_id": shipment_id}
    # Cascaded via orders → customer delete


@pytest.fixture(scope="module")
def order_with_manual_shipment(fulfillment_customer):
    """
    Insert an order and a manual shipment for testing the 400 carrier guard.
    """
    order_id = str(uuid.uuid4())
    shipment_id = str(uuid.uuid4())

    _psql(
        f"INSERT INTO orders (id, customer_id, status, total_amount, currency) "
        f"VALUES ('{order_id}', '{fulfillment_customer}', 'ready_to_ship', 1999, 'EUR');"
    )
    _psql(
        f"INSERT INTO shipments (id, order_id, carrier, status) "
        f"VALUES ('{shipment_id}', '{order_id}', 'manual', 'pending');"
    )
    yield {"order_id": order_id, "shipment_id": shipment_id}


@pytest.fixture(scope="module")
def order_without_shipment(fulfillment_customer):
    """
    Insert an order with no shipment for testing the 400 shipment guard.
    """
    order_id = str(uuid.uuid4())

    _psql(
        f"INSERT INTO orders (id, customer_id, status, total_amount, currency) "
        f"VALUES ('{order_id}', '{fulfillment_customer}', 'paid', 2999, 'EUR');"
    )
    yield order_id


@pytest.fixture(scope="module")
def order_with_labelled_shipment(fulfillment_customer):
    """
    Insert an order and a DHL shipment that already has a label_url set.

    Used by GET /label tests to verify the 404-when-no-label path (the worker
    has not actually uploaded a file, but the DB row claims it has).
    Note: the real download (200) test is skipped — it needs MinIO running.
    """
    order_id = str(uuid.uuid4())
    shipment_id = str(uuid.uuid4())

    _psql(
        f"INSERT INTO orders (id, customer_id, status, total_amount, currency) "
        f"VALUES ('{order_id}', '{fulfillment_customer}', 'ready_to_ship', 3999, 'EUR');"
    )
    _psql(
        f"INSERT INTO shipments (id, order_id, carrier, status, "
        f"label_url, label_format, tracking_number) "
        f"VALUES ('{shipment_id}', '{order_id}', 'dhl', 'label_created', "
        f"'http://localhost:9000/shipping-labels/labels/{shipment_id}.pdf', "
        f"'pdf', 'DE000000001');"
    )
    yield {"order_id": order_id, "shipment_id": shipment_id}


# ---------------------------------------------------------------------------
# POST /admin/orders/{id}/label — trigger_label_job
# ---------------------------------------------------------------------------


class TestTriggerLabelJob:
    """POST /v1/admin/orders/{id}/label"""

    def test_returns_202_for_dhl_shipment(self, order_with_dhl_shipment):
        """Happy path: enqueues outbox event and returns 202 Accepted."""
        order_id = order_with_dhl_shipment["order_id"]
        response = requests.post(
            f"{ADMIN_URL}/{order_id}/label",
            headers=_ADMIN_HEADERS,
        )
        assert response.status_code == 202

    def test_response_body_contains_status_accepted(self, order_with_dhl_shipment):
        """Response body must include status='accepted'."""
        order_id = order_with_dhl_shipment["order_id"]
        response = requests.post(
            f"{ADMIN_URL}/{order_id}/label",
            headers=_ADMIN_HEADERS,
        )
        data = response.json()
        assert data["status"] == "accepted"

    def test_response_body_contains_outbox_event_id(self, order_with_dhl_shipment):
        """Response must include outbox_event_id for job tracking."""
        order_id = order_with_dhl_shipment["order_id"]
        response = requests.post(
            f"{ADMIN_URL}/{order_id}/label",
            headers=_ADMIN_HEADERS,
        )
        data = response.json()
        assert "outbox_event_id" in data
        # Must be a valid UUID string
        uuid.UUID(data["outbox_event_id"])

    def test_returns_404_for_nonexistent_order(self):
        """Order that does not exist must return 404."""
        response = requests.post(
            f"{ADMIN_URL}/{uuid.uuid4()}/label",
            headers=_ADMIN_HEADERS,
        )
        assert response.status_code == 404

    def test_returns_400_when_order_has_no_shipment(self, order_without_shipment):
        """Order without a shipment record must return 400."""
        response = requests.post(
            f"{ADMIN_URL}/{order_without_shipment}/label",
            headers=_ADMIN_HEADERS,
        )
        assert response.status_code == 400

    def test_error_message_mentions_shipment_when_no_shipment(
        self, order_without_shipment
    ):
        """400 error body must hint that a shipment is required."""
        response = requests.post(
            f"{ADMIN_URL}/{order_without_shipment}/label",
            headers=_ADMIN_HEADERS,
        )
        assert "shipment" in response.json()["message"].lower()

    def test_returns_400_for_manual_carrier(self, order_with_manual_shipment):
        """Manual-carrier shipment must return 400 — no automated label possible."""
        order_id = order_with_manual_shipment["order_id"]
        response = requests.post(
            f"{ADMIN_URL}/{order_id}/label",
            headers=_ADMIN_HEADERS,
        )
        assert response.status_code == 400

    def test_error_message_mentions_manual_when_manual_carrier(
        self, order_with_manual_shipment
    ):
        """400 error body must explain manual carrier does not support labels."""
        order_id = order_with_manual_shipment["order_id"]
        response = requests.post(
            f"{ADMIN_URL}/{order_id}/label",
            headers=_ADMIN_HEADERS,
        )
        assert "manual" in response.json()["message"].lower()

    def test_returns_403_without_admin_header(self, order_with_dhl_shipment):
        """Missing X-Admin-Key must return 403 Forbidden."""
        order_id = order_with_dhl_shipment["order_id"]
        response = requests.post(f"{ADMIN_URL}/{order_id}/label")
        assert response.status_code == 403

    def test_idempotent_second_call_also_returns_202(self, order_with_dhl_shipment):
        """
        Calling POST /label a second time on the same order (re-trigger on failure)
        must also return 202 — writing a second outbox event is valid.
        """
        order_id = order_with_dhl_shipment["order_id"]
        # Second call on same order
        response = requests.post(
            f"{ADMIN_URL}/{order_id}/label",
            headers=_ADMIN_HEADERS,
        )
        assert response.status_code == 202


# ---------------------------------------------------------------------------
# GET /admin/orders/{id}/label — download_label
# ---------------------------------------------------------------------------


class TestDownloadLabel:
    """GET /v1/admin/orders/{id}/label"""

    def test_returns_404_for_nonexistent_order(self):
        """Order that does not exist must return 404."""
        response = requests.get(
            f"{ADMIN_URL}/{uuid.uuid4()}/label",
            headers=_ADMIN_HEADERS,
        )
        assert response.status_code == 404

    def test_returns_404_when_label_not_yet_generated(self, order_with_dhl_shipment):
        """Shipment with no label_url (worker not run yet) must return 404."""
        order_id = order_with_dhl_shipment["order_id"]
        response = requests.get(
            f"{ADMIN_URL}/{order_id}/label",
            headers=_ADMIN_HEADERS,
        )
        assert response.status_code == 404

    def test_returns_403_without_admin_header(self, order_with_dhl_shipment):
        """Missing X-Admin-Key must return 403 Forbidden."""
        order_id = order_with_dhl_shipment["order_id"]
        response = requests.get(f"{ADMIN_URL}/{order_id}/label")
        assert response.status_code == 403

    def test_returns_400_when_order_has_no_shipment(self, order_without_shipment):
        """Order without a shipment record must return 400."""
        response = requests.get(
            f"{ADMIN_URL}/{order_without_shipment}/label",
            headers=_ADMIN_HEADERS,
        )
        assert response.status_code == 400

    @pytest.mark.skip(
        reason=(
            "Requires MinIO running and a real label file in the bucket. "
            "Run manually after the ARQ worker has processed a label job: "
            "docker-compose -f docker-compose.dev.yml up -d "
            "then trigger POST /admin/orders/{id}/label and wait for the worker."
        )
    )
    def test_returns_200_with_pdf_bytes_when_label_exists(
        self, order_with_labelled_shipment
    ):
        """
        Happy path: when label_url is set and MinIO has the file,
        GET /label returns 200 with application/pdf content.
        """
        order_id = order_with_labelled_shipment["order_id"]
        response = requests.get(
            f"{ADMIN_URL}/{order_id}/label",
            headers=_ADMIN_HEADERS,
        )
        assert response.status_code == 200
        assert "application/pdf" in response.headers["content-type"]
        assert len(response.content) > 0

    @pytest.mark.skip(
        reason="Requires MinIO running and a real ZPL label stored in the bucket."
    )
    def test_content_disposition_header_contains_filename(
        self, order_with_labelled_shipment
    ):
        """Response must include Content-Disposition with a sensible filename."""
        order_id = order_with_labelled_shipment["order_id"]
        response = requests.get(
            f"{ADMIN_URL}/{order_id}/label",
            headers=_ADMIN_HEADERS,
        )
        disposition = response.headers.get("content-disposition", "")
        assert "attachment" in disposition
        assert "label_" in disposition
