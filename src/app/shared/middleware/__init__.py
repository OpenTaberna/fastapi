"""
Shared Middleware

Provides ASGI/Starlette middleware components for the FastAPI application.
"""

from .correlation_id import CorrelationIDMiddleware

__all__ = ["CorrelationIDMiddleware"]
