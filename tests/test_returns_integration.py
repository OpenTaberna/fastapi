"""
Integration tests for the Returns (RMA) API — Phase 4.4.

Run against the live stack:

    docker compose -f docker-compose.dev.yml up -d

Endpoints covered:
    POST  /v1/orders/{id}/returns  — customer files a return
    PATCH /v1/admin/returns/{id}   — admin approves / rejects / completes

Orders must be SHIPPED before a return can be filed, and there is no endpoint
that walks an order all the way through payment, so the fixtures create the
order row and set its status directly via psql — the same approach the admin
and fulfillment integration tests already use.
"""

import os
import subprocess
import uuid

import pytest
import requests

_BASE = os.getenv("TEST_API_URL", "http://localhost:8000")
RETURNS_URL = f"{_BASE}/v1/orders"
ADMIN_RETURNS_URL = f"{_BASE}/v1/admin/returns"

ADMIN_HEADERS = {"X-Admin-Key": "dev"}


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


def _customer_headers(customer_id: str) -> dict:
    return {"X-Customer-ID": customer_id}


def _reason(text: str = "Item arrived damaged in transit") -> dict:
    return {"reason": text}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def customer():
    cid = str(uuid.uuid4())
    u = uuid.uuid4().hex[:8]
    _psql(
        f"INSERT INTO customers (id, keycloak_user_id, email, first_name, last_name) "
        f"VALUES ('{cid}', 'kc-ret-{u}', 'ret-{u}@returns-test.example', 'Ret', 'Test');"
    )
    yield cid
    _psql(f"DELETE FROM customers WHERE id = '{cid}';")


@pytest.fixture(scope="module")
def other_customer():
    cid = str(uuid.uuid4())
    u = uuid.uuid4().hex[:8]
    _psql(
        f"INSERT INTO customers (id, keycloak_user_id, email, first_name, last_name) "
        f"VALUES ('{cid}', 'kc-ret-o-{u}', 'ret-o-{u}@returns-test.example', 'Oth', 'Test');"
    )
    yield cid
    _psql(f"DELETE FROM customers WHERE id = '{cid}';")


def _make_order(customer_id: str, status: str) -> str:
    """Insert an order row directly in the given status and return its UUID."""
    order_id = str(uuid.uuid4())
    _psql(
        f"INSERT INTO orders (id, customer_id, status, total_amount, currency) "
        f"VALUES ('{order_id}', '{customer_id}', '{status}', 4999, 'EUR');"
    )
    return order_id


@pytest.fixture
def shipped_order(customer):
    order_id = _make_order(customer, "shipped")
    yield order_id
    _psql(f"DELETE FROM returns WHERE order_id = '{order_id}';")
    _psql(f"DELETE FROM orders WHERE id = '{order_id}';")


@pytest.fixture
def paid_order(customer):
    order_id = _make_order(customer, "paid")
    yield order_id
    _psql(f"DELETE FROM orders WHERE id = '{order_id}';")


@pytest.fixture
def filed_return(shipped_order, customer):
    """A return already in REQUESTED status, ready for admin transitions."""
    resp = requests.post(
        f"{RETURNS_URL}/{shipped_order}/returns",
        json=_reason(),
        headers=_customer_headers(customer),
    )
    assert resp.status_code == 201
    return resp.json()


# ---------------------------------------------------------------------------
# POST /v1/orders/{id}/returns
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestCreateReturn:
    def test_shipped_order_returns_201(self, shipped_order, customer):
        resp = requests.post(
            f"{RETURNS_URL}/{shipped_order}/returns",
            json=_reason(),
            headers=_customer_headers(customer),
        )
        assert resp.status_code == 201

    def test_response_body_is_a_requested_return(self, shipped_order, customer):
        resp = requests.post(
            f"{RETURNS_URL}/{shipped_order}/returns",
            json=_reason(),
            headers=_customer_headers(customer),
        )
        body = resp.json()
        assert body["status"] == "requested"
        assert body["order_id"] == shipped_order
        assert body["admin_note"] is None

    def test_created_return_is_durable_immediately(self, shipped_order, customer):
        # Guards issue #26: the handler must commit before responding, or a
        # follow-up request can fail to see the row it was just told exists.
        resp = requests.post(
            f"{RETURNS_URL}/{shipped_order}/returns",
            json=_reason(),
            headers=_customer_headers(customer),
        )
        return_id = resp.json()["id"]
        follow_up = requests.patch(
            f"{ADMIN_RETURNS_URL}/{return_id}",
            json={"status": "approved"},
            headers=ADMIN_HEADERS,
        )
        assert follow_up.status_code == 200

    def test_second_return_for_same_order_is_rejected(self, shipped_order, customer):
        first = requests.post(
            f"{RETURNS_URL}/{shipped_order}/returns",
            json=_reason(),
            headers=_customer_headers(customer),
        )
        assert first.status_code == 201
        second = requests.post(
            f"{RETURNS_URL}/{shipped_order}/returns",
            json=_reason("A completely different reason"),
            headers=_customer_headers(customer),
        )
        assert second.status_code == 400

    def test_unshipped_order_is_rejected(self, paid_order, customer):
        resp = requests.post(
            f"{RETURNS_URL}/{paid_order}/returns",
            json=_reason(),
            headers=_customer_headers(customer),
        )
        assert resp.status_code == 400

    def test_unknown_order_returns_404(self, customer):
        resp = requests.post(
            f"{RETURNS_URL}/{uuid.uuid4()}/returns",
            json=_reason(),
            headers=_customer_headers(customer),
        )
        assert resp.status_code == 404

    def test_other_customers_order_returns_403(self, shipped_order, other_customer):
        resp = requests.post(
            f"{RETURNS_URL}/{shipped_order}/returns",
            json=_reason(),
            headers=_customer_headers(other_customer),
        )
        assert resp.status_code == 403

    def test_short_reason_returns_422(self, shipped_order, customer):
        resp = requests.post(
            f"{RETURNS_URL}/{shipped_order}/returns",
            json=_reason("broken"),
            headers=_customer_headers(customer),
        )
        assert resp.status_code == 422

    def test_missing_reason_returns_422(self, shipped_order, customer):
        resp = requests.post(
            f"{RETURNS_URL}/{shipped_order}/returns",
            json={},
            headers=_customer_headers(customer),
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# PATCH /v1/admin/returns/{id}
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestAdminUpdateReturn:
    def test_approve_returns_200(self, filed_return):
        resp = requests.patch(
            f"{ADMIN_RETURNS_URL}/{filed_return['id']}",
            json={"status": "approved"},
            headers=ADMIN_HEADERS,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "approved"

    def test_admin_note_is_persisted(self, filed_return):
        resp = requests.patch(
            f"{ADMIN_RETURNS_URL}/{filed_return['id']}",
            json={"status": "approved", "admin_note": "Photo confirms damage"},
            headers=ADMIN_HEADERS,
        )
        assert resp.json()["admin_note"] == "Photo confirms damage"

    def test_approved_can_be_completed(self, filed_return):
        rid = filed_return["id"]
        requests.patch(
            f"{ADMIN_RETURNS_URL}/{rid}",
            json={"status": "approved"},
            headers=ADMIN_HEADERS,
        )
        resp = requests.patch(
            f"{ADMIN_RETURNS_URL}/{rid}",
            json={"status": "completed"},
            headers=ADMIN_HEADERS,
        )
        assert resp.status_code == 200

    def test_requested_cannot_jump_to_completed(self, filed_return):
        resp = requests.patch(
            f"{ADMIN_RETURNS_URL}/{filed_return['id']}",
            json={"status": "completed"},
            headers=ADMIN_HEADERS,
        )
        assert resp.status_code == 400

    def test_rejected_is_terminal(self, filed_return):
        rid = filed_return["id"]
        requests.patch(
            f"{ADMIN_RETURNS_URL}/{rid}",
            json={"status": "rejected"},
            headers=ADMIN_HEADERS,
        )
        resp = requests.patch(
            f"{ADMIN_RETURNS_URL}/{rid}",
            json={"status": "approved"},
            headers=ADMIN_HEADERS,
        )
        assert resp.status_code == 400

    def test_unknown_return_returns_404(self):
        resp = requests.patch(
            f"{ADMIN_RETURNS_URL}/{uuid.uuid4()}",
            json={"status": "approved"},
            headers=ADMIN_HEADERS,
        )
        assert resp.status_code == 404

    def test_without_admin_key_returns_403(self, filed_return):
        resp = requests.patch(
            f"{ADMIN_RETURNS_URL}/{filed_return['id']}",
            json={"status": "approved"},
        )
        assert resp.status_code == 403

    def test_invalid_status_returns_422(self, filed_return):
        resp = requests.patch(
            f"{ADMIN_RETURNS_URL}/{filed_return['id']}",
            json={"status": "banana"},
            headers=ADMIN_HEADERS,
        )
        assert resp.status_code == 422
