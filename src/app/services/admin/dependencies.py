"""
Admin Dependencies

Admin access is enforced by ``app.authorize.require_admin``, which requires a
Keycloak token carrying the admin realm role and issued to an admin frontend
client. This module re-exports it so admin, inventory, fulfillment and returns
keep importing from one place.

Kept as a module rather than collapsed into the imports of four routers so the
policy has a single obvious home, matching services/payments/dependencies.py.
"""

from app.authorize import require_admin

__all__ = ["require_admin"]
