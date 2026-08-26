"""
Log filters following Single Responsibility Principle.

Each filter has one specific responsibility.
"""

import logging
from typing import Any, Dict, Set

from .interfaces import ILogFilter
from .enums import LogLevel


class SensitiveDataFilter(ILogFilter):
    """Filter to remove sensitive information from logs."""

    # Common patterns for sensitive data
    SENSITIVE_KEYS: Set[str] = {
        "password",
        "passwd",
        "pwd",
        "secret",
        "token",
        "api_key",
        "apikey",
        "authorization",
        "auth",
        "credential",
        "private_key",
        "access_token",
        "refresh_token",
        "session_id",
        "cookie",
        "csrf_token",
        "ssn",
        "credit_card",
        "cvv",
        "pin",
    }

    MASK_VALUE = "***REDACTED***"

    def filter(self, record: logging.LogRecord) -> bool:
        """Always return True - we sanitize but don't block."""
        # Sanitize extra fields
        for key in list(record.__dict__.keys()):
            if self._is_sensitive_key(key):
                setattr(record, key, self.MASK_VALUE)
        return True

    def sanitize(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively remove sensitive data from dictionary."""
        if not isinstance(data, dict):
            return data

        sanitized = {}
        for key, value in data.items():
            if self._is_sensitive_key(key):
                sanitized[key] = self.MASK_VALUE
            elif isinstance(value, dict):
                sanitized[key] = self.sanitize(value)
            elif isinstance(value, (list, tuple)):
                sanitized[key] = [
                    self.sanitize(item) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                sanitized[key] = value

        return sanitized

    def _is_sensitive_key(self, key: str) -> bool:
        """Check if key name indicates sensitive data."""
        key_lower = key.lower()
        return any(sensitive in key_lower for sensitive in self.SENSITIVE_KEYS)


class CorrelationIdFilter(ILogFilter):
    """
    Attach the current request's correlation ID to every log record.

    CorrelationIDMiddleware stores the ID in a ContextVar per request. Without
    this filter that value is never read, so the ID reaches the response header
    but never the logs — which defeats the point of having one. Setting it as a
    record attribute means JSONFormatter picks it up as an extra field, so every
    line emitted while serving a request can be traced back to that request.

    Records emitted outside a request context (worker jobs, startup) get an
    empty string rather than a missing attribute, so formatters never KeyError.
    """

    ATTRIBUTE = "correlation_id"
    TRACE_ATTRIBUTE = "trace_id"

    def filter(self, record: logging.LogRecord) -> bool:
        """Never blocks — only enriches the record."""
        # Imported lazily so the logging package does not depend on Starlette
        # at import time; the logger is used by the worker too, which has no
        # HTTP stack.
        from app.shared.middleware.correlation_id import get_correlation_id

        if not hasattr(record, self.ATTRIBUTE):
            setattr(record, self.ATTRIBUTE, get_correlation_id())

        # The trace id is what joins a span found in Grafana to the log lines
        # for that same request. Without it the two systems describe the same
        # work and cannot be put side by side. Empty when tracing is off, so
        # the field is always present and a formatter never KeyErrors.
        if not hasattr(record, self.TRACE_ATTRIBUTE):
            from app.shared.observability import current_trace_id

            setattr(record, self.TRACE_ATTRIBUTE, current_trace_id() or "")
        return True

    def sanitize(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """No sanitization needed for correlation IDs."""
        return data


class LevelFilter(ILogFilter):
    """Filter logs by minimum level."""

    def __init__(self, min_level: LogLevel):
        self.min_level = getattr(logging, min_level.value)

    def filter(self, record: logging.LogRecord) -> bool:
        """Filter by log level."""
        return record.levelno >= self.min_level

    def sanitize(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """No sanitization needed for level filter."""
        return data
