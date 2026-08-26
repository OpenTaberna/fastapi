"""
Analytics Dependencies

Analytics is admin-only. Re-exports the shared admin guard so the policy has one
home, matching services/admin/dependencies.py.
"""

from app.authorize import require_admin

__all__ = ["require_admin"]
