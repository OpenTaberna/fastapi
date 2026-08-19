"""
Unit tests for Phase 4.1 / 4.5 — observability and rate limiting.

Covers:
    - CorrelationIDMiddleware: header propagation and ContextVar lifecycle
    - CorrelationIdFilter: attaches the ID to log records
    - JSONFormatter: promotes correlation_id to a top-level field
    - Rate limiter: reads rate_limit_enabled / rate_limit_per_minute
"""

import json
import logging
from unittest.mock import patch


from app.shared.logger.filters import CorrelationIdFilter
from app.shared.logger.formatters import JSONFormatter
from app.shared.middleware.correlation_id import (
    CORRELATION_ID_HEADER,
    _correlation_id_var,
    _resolve_correlation_id,
    get_correlation_id,
)


def _record(msg: str = "hello", **extra) -> logging.LogRecord:
    rec = logging.LogRecord("app.test", logging.INFO, "p", 1, msg, None, None)
    for k, v in extra.items():
        setattr(rec, k, v)
    return rec


def _limiter_module():
    """
    Return the limiter *module*.

    ``app.shared.rate_limit`` re-exports the Limiter instance as ``limiter``,
    which shadows the submodule of the same name, so a plain import binds the
    object instead of the module.
    """
    import importlib

    return importlib.import_module("app.shared.rate_limit.limiter")


class _FakeRequest:
    def __init__(self, headers: dict | None = None):
        self.headers = headers or {}


# ---------------------------------------------------------------------------
# Correlation ID resolution
# ---------------------------------------------------------------------------


class TestResolveCorrelationId:
    def test_uses_the_incoming_header(self):
        req = _FakeRequest({CORRELATION_ID_HEADER: "trace-abc"})
        assert _resolve_correlation_id(req) == "trace-abc"

    def test_generates_one_when_header_absent(self):
        assert _resolve_correlation_id(_FakeRequest()) != ""

    def test_generates_one_when_header_is_blank(self):
        req = _FakeRequest({CORRELATION_ID_HEADER: "   "})
        assert _resolve_correlation_id(req).strip() != ""

    def test_generated_ids_are_unique_per_request(self):
        a = _resolve_correlation_id(_FakeRequest())
        b = _resolve_correlation_id(_FakeRequest())
        assert a != b

    def test_incoming_value_is_trimmed(self):
        req = _FakeRequest({CORRELATION_ID_HEADER: "  trace-abc  "})
        assert _resolve_correlation_id(req) == "trace-abc"


class TestCorrelationContextVar:
    def test_empty_outside_a_request(self):
        assert get_correlation_id() == ""

    def test_reads_back_inside_a_request(self):
        token = _correlation_id_var.set("req-1")
        try:
            assert get_correlation_id() == "req-1"
        finally:
            _correlation_id_var.reset(token)

    def test_reset_restores_the_previous_value(self):
        token = _correlation_id_var.set("req-1")
        _correlation_id_var.reset(token)
        assert get_correlation_id() == ""


# ---------------------------------------------------------------------------
# Log integration — the part that was missing entirely
# ---------------------------------------------------------------------------


class TestCorrelationIdFilter:
    def test_attaches_the_id_to_the_record(self):
        token = _correlation_id_var.set("req-42")
        try:
            rec = _record()
            CorrelationIdFilter().filter(rec)
            assert rec.correlation_id == "req-42"
        finally:
            _correlation_id_var.reset(token)

    def test_never_blocks_the_record(self):
        assert CorrelationIdFilter().filter(_record()) is True

    def test_sets_empty_string_outside_a_request(self):
        rec = _record()
        CorrelationIdFilter().filter(rec)
        assert rec.correlation_id == ""

    def test_is_enabled_by_default_in_logger_config(self):
        # The filter existing is not enough — it has to be registered, or the
        # correlation ID silently never reaches a single log line.
        from app.shared.logger.config import LoggerConfig

        cfg = LoggerConfig(name="app.test")
        assert any(isinstance(f, CorrelationIdFilter) for f in cfg.filters)

    def test_does_not_overwrite_an_explicit_value(self):
        token = _correlation_id_var.set("from-context")
        try:
            rec = _record(correlation_id="explicit")
            CorrelationIdFilter().filter(rec)
            assert rec.correlation_id == "explicit"
        finally:
            _correlation_id_var.reset(token)


class TestJsonFormatterCorrelationId:
    def test_promotes_correlation_id_to_top_level(self):
        token = _correlation_id_var.set("req-7")
        try:
            rec = _record()
            CorrelationIdFilter().filter(rec)
            out = json.loads(JSONFormatter(include_extra=True).format(rec))
            assert out["correlation_id"] == "req-7"
        finally:
            _correlation_id_var.reset(token)

    def test_does_not_duplicate_it_inside_extra(self):
        token = _correlation_id_var.set("req-7")
        try:
            rec = _record(order_id="o-1")
            CorrelationIdFilter().filter(rec)
            out = json.loads(JSONFormatter(include_extra=True).format(rec))
            assert out["extra"] == {"order_id": "o-1"}
        finally:
            _correlation_id_var.reset(token)

    def test_key_absent_outside_a_request(self):
        rec = _record()
        CorrelationIdFilter().filter(rec)
        out = json.loads(JSONFormatter(include_extra=True).format(rec))
        assert "correlation_id" not in out

    def test_other_extra_fields_still_survive(self):
        rec = _record(order_id="o-1", payment_id="p-2")
        CorrelationIdFilter().filter(rec)
        out = json.loads(JSONFormatter(include_extra=True).format(rec))
        assert out["extra"]["order_id"] == "o-1"
        assert out["extra"]["payment_id"] == "p-2"


# ---------------------------------------------------------------------------
# Rate limiting — the settings were previously ignored
# ---------------------------------------------------------------------------


class TestRateLimitConfiguration:
    def test_default_limit_is_built_from_the_setting(self):
        mod = _limiter_module()

        with patch.object(mod, "get_settings") as gs:
            gs.return_value.rate_limit_per_minute = 5
            assert mod.default_rate_limit() == "5/minute"

    def test_changing_the_setting_changes_the_limit(self):
        mod = _limiter_module()

        with patch.object(mod, "get_settings") as gs:
            gs.return_value.rate_limit_per_minute = 120
            assert mod.default_rate_limit() == "120/minute"

    def test_limit_string_is_a_valid_slowapi_expression(self):
        from limits import parse

        mod = _limiter_module()

        with patch.object(mod, "get_settings") as gs:
            gs.return_value.rate_limit_per_minute = 60
            parse(mod.default_rate_limit())  # raises if malformed

    def test_no_global_default_limit_is_applied(self):
        # A global cap hits every route — health probes, admin batch work and
        # the test suite itself, which briefly exceeds any useful per-minute
        # budget from a single IP. Limiting is opt-in per route instead.
        from app.shared.rate_limit import limiter

        assert not limiter._default_limits

    def test_limiter_is_exported_from_the_package(self):
        from app.shared.rate_limit import default_rate_limit, limiter

        assert limiter is not None
        assert callable(default_rate_limit)
