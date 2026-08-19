"""
SlowAPI Limiter — Phase 4.5

Single application-wide SlowAPI limiter instance.  Import ``limiter`` wherever
rate-limiting decorators are needed and attach the SlowAPI middleware in
``main.py``.

Key identifiers are resolved by client IP (``get_remote_address`` default).
Adjust the ``key_func`` here if the application sits behind a load-balancer
that sets ``X-Forwarded-For`` — replace with a function that reads that header.

Both knobs come from Settings so the limiter can actually be configured:
``rate_limit_enabled`` turns limiting off entirely (useful in tests and local
development), and ``rate_limit_per_minute`` is the budget used by routes that
opt in.  Limiting is opt-in per route rather than global — see the note on
``default_limits`` below.

Usage in a route:
    from app.shared.rate_limit import limiter, default_rate_limit

    @limiter.limit(default_rate_limit())
    @router.post("/webhooks/stripe")
    async def stripe_webhook(request: Request, ...):
        ...
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.shared.config import get_settings


def default_rate_limit() -> str:
    """
    Build the SlowAPI limit string from settings.rate_limit_per_minute.

    Returns:
        A limit expression such as "60/minute".
    """
    return f"{get_settings().rate_limit_per_minute}/minute"


limiter = Limiter(
    key_func=get_remote_address,
    # enabled=False makes every decorated route a pass-through, so
    # RATE_LIMIT_ENABLED=false genuinely disables limiting rather than being
    # a setting nobody reads.
    enabled=get_settings().rate_limit_enabled,
    # Deliberately no default_limits. A global cap would apply to every route
    # including health probes and admin batch work, and at any value low
    # enough to be useful it throttles legitimate clients. Routes that need a
    # limit opt in with @limiter.limit(default_rate_limit()).
)
