"""
Chore Module

Infrastructure and operational tasks such as application lifecycle management,
database initialization, health checks, and scheduled maintenance tasks.
"""

from .lifespan import lifespan

__all__ = ["lifespan"]
