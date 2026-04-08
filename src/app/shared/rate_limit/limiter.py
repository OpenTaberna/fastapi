"""
SlowAPI Limiter — Phase 4.5

Single application-wide SlowAPI limiter instance.  Import ``limiter`` wherever
rate-limiting decorators are needed and attach the SlowAPI middleware in
``main.py``.

Key identifiers are resolved by client IP (``get_remote_address`` default).
Adjust the ``key_func`` here if the application sits behind a load-balancer
that sets ``X-Forwarded-For`` — replace with a function that reads that header.

Usage in a route:
    from app.shared.rate_limit import limiter

    @limiter.limit("5/minute")
    @router.post("/webhooks/stripe")
    async def stripe_webhook(request: Request, ...):
        ...
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
