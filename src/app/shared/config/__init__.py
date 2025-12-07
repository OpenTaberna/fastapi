"""
Configuration Module

Provides environment-based configuration management with support for:
- .env files
- Docker secrets (/run/secrets/*)
- Kubernetes secrets (mounted as files)
- Environment variables

Usage:
    from app.shared.config import get_settings

    settings = get_settings()
    print(settings.database_url)
"""

from app.shared.config.enums import Environment
from app.shared.config.factory import get_settings
from app.shared.config.settings import Settings

__all__ = [
    "Environment",
    "Settings",
    "get_settings",
]
