"""
Integration tests for the health endpoints — Phase 4.1.

Run against the live stack:

    docker compose -f docker-compose.dev.yml up -d

Endpoints covered:
    GET /health        — liveness, never touches dependencies
    GET /health/ready  — readiness, checks database and Redis

These are the endpoints an orchestrator polls, so the contract that matters is
the status code and the shape, not the prose.
"""

import os

import pytest
import requests

_BASE = os.getenv("TEST_API_URL", "http://localhost:8000")
HEALTH_URL = f"{_BASE}/health"
READY_URL = f"{_BASE}/health/ready"


@pytest.mark.integration
class TestLiveness:
    def test_returns_200(self):
        assert requests.get(HEALTH_URL).status_code == 200

    def test_reports_ok(self):
        assert requests.get(HEALTH_URL).json()["status"] == "ok"

    def test_includes_a_timestamp(self):
        assert requests.get(HEALTH_URL).json()["timestamp"]

    def test_needs_no_authentication(self):
        # An orchestrator probe cannot present credentials.
        assert requests.get(HEALTH_URL, headers={}).status_code == 200

    def test_does_not_report_dependencies(self):
        # Liveness must stay cheap — checking the DB here would make a slow
        # database look like a dead process and get the container killed.
        body = requests.get(HEALTH_URL).json()
        assert "database" not in body
        assert "redis" not in body


@pytest.mark.integration
class TestReadiness:
    def test_returns_200_when_dependencies_are_up(self):
        assert requests.get(READY_URL).status_code == 200

    def test_reports_database_status(self):
        db = requests.get(READY_URL).json()["database"]
        assert db["healthy"] is True
        assert db["error"] is None

    def test_reports_redis_status(self):
        redis = requests.get(READY_URL).json()["redis"]
        assert redis["healthy"] is True
        assert redis["error"] is None

    def test_reports_latency_for_each_dependency(self):
        body = requests.get(READY_URL).json()
        assert isinstance(body["database"]["latency_ms"], (int, float))
        assert isinstance(body["redis"]["latency_ms"], (int, float))

    def test_overall_status_is_ok_when_all_healthy(self):
        assert requests.get(READY_URL).json()["status"] == "ok"


@pytest.mark.integration
class TestCorrelationIdHeader:
    """The middleware must echo a correlation ID on every response."""

    def test_response_carries_a_correlation_id(self):
        resp = requests.get(HEALTH_URL)
        assert resp.headers.get("X-Correlation-ID")

    def test_supplied_id_is_echoed_back(self):
        resp = requests.get(HEALTH_URL, headers={"X-Correlation-ID": "trace-xyz"})
        assert resp.headers["X-Correlation-ID"] == "trace-xyz"

    def test_generated_ids_differ_between_requests(self):
        a = requests.get(HEALTH_URL).headers["X-Correlation-ID"]
        b = requests.get(HEALTH_URL).headers["X-Correlation-ID"]
        assert a != b

    def test_present_on_error_responses_too(self):
        # Tracing a failure is exactly when the ID matters most.
        resp = requests.get(f"{_BASE}/v1/orders/does-not-exist")
        assert resp.headers.get("X-Correlation-ID")
