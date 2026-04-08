"""
Rate Limiting

Shared SlowAPI limiter instance and dependency for FastAPI routes.
"""

from .limiter import limiter

__all__ = ["limiter"]
