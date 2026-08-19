"""
Rate Limiting

Shared SlowAPI limiter instance and dependency for FastAPI routes.
"""

from .limiter import default_rate_limit, limiter

__all__ = ["limiter", "default_rate_limit"]
