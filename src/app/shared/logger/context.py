"""
Context management for request-scoped logging data.

Uses contextvars for thread-safe and async-safe context storage.
"""

from contextvars import ContextVar
from typing import Any, Dict, Optional


# Context storage for request-scoped data
_log_context: ContextVar[Dict[str, Any]] = ContextVar("log_context", default={})


class LogContext:
    """
    Context manager for adding contextual information to logs.

    Usage:
        with LogContext(request_id="abc-123", user_id="456"):
            logger.info("Processing request")
            # Log will include request_id and user_id
    """

    def __init__(self, **context):
        self.context = context
        self.token: Optional[Any] = None

    def __enter__(self):
        """Add context to ContextVar."""
        current = _log_context.get()
        updated = {**current, **self.context}
        self.token = _log_context.set(updated)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Remove context from ContextVar."""
        if self.token:
            _log_context.reset(self.token)


def get_log_context() -> Dict[str, Any]:
    """Get current log context."""
    return _log_context.get()


def setup_request_logging(request_id: str, **context):
    """
    Setup logging context for a request.

    Convenience function for FastAPI middleware.

    Usage:
        @app.middleware("http")
        async def log_requests(request: Request, call_next):
            request_id = str(uuid.uuid4())
            with setup_request_logging(request_id, path=request.url.path):
                response = await call_next(request)
            return response
    """
    return LogContext(request_id=request_id, **context)
