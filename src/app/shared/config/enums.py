"""
Configuration Enums

Defines enumerations for configuration values.
"""

from enum import Enum


class Environment(str, Enum):
    """Application environment."""

    DEVELOPMENT = "development"
    TESTING = "testing"
    STAGING = "staging"
    PRODUCTION = "production"

    def is_production(self) -> bool:
        """Check if environment is production."""
        return self == Environment.PRODUCTION

    def is_testing(self) -> bool:
        """Check if environment is testing."""
        return self == Environment.TESTING

    def is_development(self) -> bool:
        """Check if environment is development."""
        return self == Environment.DEVELOPMENT
