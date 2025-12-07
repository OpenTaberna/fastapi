"""
Configuration Factory

Provides singleton access to application settings.
"""

from functools import lru_cache

from app.shared.config.settings import Settings


@lru_cache
def get_settings() -> Settings:
    """
    Get application settings (cached singleton).

    Returns:
        Settings instance

    Example:
        >>> from app.shared.config import get_settings
        >>> settings = get_settings()
        >>> print(settings.database_url)
    """
    return Settings()


def clear_settings_cache() -> None:
    """
    Clear the settings cache.

    Useful for testing or reloading configuration.

    Example:
        >>> clear_settings_cache()
        >>> settings = get_settings()  # Loads fresh settings
    """
    get_settings.cache_clear()
