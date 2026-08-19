"""
Admin Dependencies

FastAPI dependency functions for the admin service.

Keeping these in a dedicated module (matching the pattern of
services/payments/dependencies.py) makes them independently testable
and provides a clean extension point for the Keycloak role=admin
dependency that will replace the dev shim in production.
"""

from fastapi import Header

from app.shared.exceptions import access_denied
from app.shared.logger import get_logger

logger = get_logger(__name__)


async def require_admin(
    x_admin_key: str | None = Header(
        default=None,
        alias="X-Admin-Key",
        description="[Dev-only] Admin access token. Replaced by Keycloak role=admin check in production.",
    ),
) -> None:
    """
    Enforce admin access on every admin endpoint.

    Development shim: accepts any non-empty X-Admin-Key header value.
    Production TODO: validate a Keycloak JWT with role=admin claim and
    replace this function body entirely — no call sites change.

    Args:
        x_admin_key: Value of the X-Admin-Key request header.

    Raises:
        AuthorizationError (403): When the header is absent.
    """
    if x_admin_key is None:
        logger.warning("Admin access attempted without credentials")
        raise access_denied(
            resource="admin",
            action="access",
            message="Admin access required. Provide X-Admin-Key header (dev) or valid admin JWT (production).",
        )
