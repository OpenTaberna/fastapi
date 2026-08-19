"""
Correlation-ID Middleware

Propagates a per-request correlation ID through the full request lifecycle:
- Reads the ID from the incoming ``X-Correlation-ID`` header.
- Generates a new UUID v4 when the header is absent.
- Stores the ID in a ContextVar so structured log records can include it.
- Echoes the ID back in the ``X-Correlation-ID`` response header.

Usage:
    app.add_middleware(CorrelationIDMiddleware)

Log integration:
    Any code that calls ``get_correlation_id()`` during a request will receive
    the correlation ID for that request.  Wire it into a logging Filter to
    attach ``correlation_id`` to every log record automatically.
"""

import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# Module-level ContextVar — one per running coroutine (one per request)
_correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")

# Header name used for propagation (canonical form)
CORRELATION_ID_HEADER = "X-Correlation-ID"


def get_correlation_id() -> str:
    """
    Return the correlation ID for the currently executing request.

    Should only be called from within an active request context, i.e. inside
    a FastAPI route handler, middleware, or background task started during a
    request.  Returns an empty string when called outside a request context.

    Args:
        None

    Returns:
        Correlation ID string (UUID v4 format or caller-supplied value).
    """
    return _correlation_id_var.get()


class CorrelationIDMiddleware(BaseHTTPMiddleware):
    """
    ASGI middleware that attaches a correlation ID to every request.

    Order of operations per request:
        1. Read ``X-Correlation-ID`` from incoming headers.
        2. Generate a UUID v4 if the header is absent or blank.
        3. Store the ID in ``_correlation_id_var`` so it is accessible
           to all code that runs during this request coroutine.
        4. Continue processing the request.
        5. Append the ID to the outgoing response headers.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        """
        Inject a correlation ID into the request context and response headers.

        Args:
            request:   Incoming HTTP request.
            call_next: Next middleware / route handler in the ASGI chain.

        Returns:
            HTTP response with ``X-Correlation-ID`` header set.
        """
        correlation_id = _resolve_correlation_id(request)
        token = _correlation_id_var.set(correlation_id)

        try:
            response: Response = await call_next(request)
        finally:
            # Always reset — prevents leakage if the ContextVar is reused
            _correlation_id_var.reset(token)

        response.headers[CORRELATION_ID_HEADER] = correlation_id
        return response


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _resolve_correlation_id(request: Request) -> str:
    """
    Extract the correlation ID from the request or generate a fresh one.

    Returns the value of the ``X-Correlation-ID`` header if it is present and
    non-empty.  Generates a new UUID v4 string otherwise.

    Args:
        request: Incoming HTTP request.

    Returns:
        Non-empty correlation ID string.
    """
    incoming = request.headers.get(CORRELATION_ID_HEADER, "").strip()
    return incoming if incoming else str(uuid.uuid4())
