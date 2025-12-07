"""
Configuration Module Tests

Tests for environment-based configuration with secrets support.
"""

import pytest

from app.shared.config import Environment, Settings, get_settings
from app.shared.config.factory import clear_settings_cache
from app.shared.config.loader import load_secret, secrets_available


class TestEnvironmentEnum:
    """Test Environment enum."""

    def test_environment_values(self):
        """Test environment enum values."""
        assert Environment.DEVELOPMENT.value == "development"
        assert Environment.TESTING.value == "testing"
        assert Environment.STAGING.value == "staging"
        assert Environment.PRODUCTION.value == "production"

    def test_is_production(self):
        """Test is_production method."""
        assert Environment.PRODUCTION.is_production()
        assert not Environment.DEVELOPMENT.is_production()
        assert not Environment.TESTING.is_production()

    def test_is_testing(self):
        """Test is_testing method."""
        assert Environment.TESTING.is_testing()
        assert not Environment.PRODUCTION.is_testing()

    def test_is_development(self):
        """Test is_development method."""
        assert Environment.DEVELOPMENT.is_development()
        assert not Environment.PRODUCTION.is_development()


class TestSecretLoader:
    """Test secret loading from various sources."""

    def test_load_secret_from_env(self, monkeypatch):
        """Test loading secret from environment variable."""
        monkeypatch.setenv("TEST_SECRET", "secret-value")

        result = load_secret("test_secret")
        assert result == "secret-value"

    def test_load_secret_with_default(self):
        """Test loading secret with default value."""
        result = load_secret("nonexistent_secret", default="default-value")
        assert result == "default-value"

    def test_load_secret_not_found(self):
        """Test loading nonexistent secret returns None."""
        result = load_secret("definitely_does_not_exist")
        assert result is None

    def test_secrets_available(self):
        """Test checking if secrets directories exist."""
        # In test environment, secrets usually not available
        available = secrets_available()
        assert isinstance(available, bool)


class TestSettings:
    """Test Settings class."""

    def test_default_settings(self):
        """Test default settings values."""
        settings = Settings()

        assert settings.app_name == "OpenTaberna API"
        assert settings.app_version == "0.1.0"
        assert settings.environment in [
            Environment.DEVELOPMENT,
            Environment.TESTING,
        ]
        assert settings.host == "0.0.0.0"
        assert settings.port == 8000

    def test_custom_settings_from_env(self, monkeypatch):
        """Test loading custom settings from environment."""
        monkeypatch.setenv("APP_NAME", "Custom API")
        monkeypatch.setenv("PORT", "9000")
        monkeypatch.setenv("DEBUG", "true")

        settings = Settings()

        assert settings.app_name == "Custom API"
        assert settings.port == 9000
        assert settings.debug is True

    def test_environment_from_env(self, monkeypatch):
        """Test setting environment from env var."""
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("SECRET_KEY", "production-secret-key")

        settings = Settings()

        assert settings.environment == Environment.PRODUCTION
        assert settings.is_production

    def test_database_settings(self):
        """Test database configuration."""
        settings = Settings()

        assert "postgresql" in settings.database_url.lower()
        assert settings.database_pool_size == 20
        assert settings.database_max_overflow == 40
        assert settings.database_pool_timeout == 30

    def test_redis_settings(self):
        """Test Redis configuration."""
        settings = Settings()

        assert "redis" in settings.redis_url.lower()
        assert settings.redis_password is None  # No secret in tests

    def test_keycloak_settings(self):
        """Test Keycloak configuration."""
        settings = Settings()

        assert "localhost" in settings.keycloak_url
        assert settings.keycloak_realm == "opentaberna"
        assert settings.keycloak_client_id == "opentaberna-api"

    def test_cors_settings(self):
        """Test CORS configuration."""
        settings = Settings()

        assert isinstance(settings.cors_origins, list)
        assert settings.cors_credentials is True

    def test_logging_settings(self):
        """Test logging configuration."""
        settings = Settings()

        assert settings.log_level == "INFO"
        assert settings.log_format in ["console", "json"]

    def test_cache_settings(self):
        """Test cache configuration."""
        settings = Settings()

        assert isinstance(settings.cache_enabled, bool)
        assert settings.cache_ttl > 0

    def test_feature_flags(self):
        """Test feature flags."""
        settings = Settings()

        assert isinstance(settings.feature_webhooks_enabled, bool)


class TestSettingsValidation:
    """Test settings validation."""

    def test_secret_key_required_in_production(self, monkeypatch):
        """Test SECRET_KEY validation in production."""
        monkeypatch.setenv("ENVIRONMENT", "production")

        with pytest.raises(ValueError, match="SECRET_KEY must be changed"):
            Settings()

    def test_secret_key_ok_in_production(self, monkeypatch):
        """Test SECRET_KEY accepts custom value in production."""
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("SECRET_KEY", "custom-secure-key-123")

        settings = Settings()
        assert settings.secret_key == "custom-secure-key-123"

    def test_secret_key_default_ok_in_development(self):
        """Test default SECRET_KEY allowed in development."""
        settings = Settings()

        # Should not raise even with default secret key
        assert settings.secret_key is not None


class TestSettingsProperties:
    """Test Settings helper properties and methods."""

    def test_is_production_property(self, monkeypatch):
        """Test is_production property."""
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("SECRET_KEY", "prod-key")

        settings = Settings()
        assert settings.is_production is True

    def test_is_testing_property(self, monkeypatch):
        """Test is_testing property."""
        monkeypatch.setenv("ENVIRONMENT", "testing")

        settings = Settings()
        assert settings.is_testing is True

    def test_is_development_property(self, monkeypatch):
        """Test is_development property."""
        monkeypatch.setenv("ENVIRONMENT", "development")

        settings = Settings()
        assert settings.is_development is True

    def test_get_database_url_with_password(self):
        """Test getting database URL with password visible."""
        settings = Settings()

        url = settings.get_database_url(hide_password=False)
        assert "postgresql" in url.lower()

    def test_get_database_url_hidden_password(self):
        """Test getting database URL with hidden password."""
        settings = Settings()

        url = settings.get_database_url(hide_password=True)
        assert "***" in url or "@" not in url  # Password hidden or no password


class TestSettingsPostInit:
    """Test post-initialization settings modifications."""

    def test_debug_enabled_in_development(self, monkeypatch):
        """Test debug auto-enabled in development."""
        monkeypatch.setenv("ENVIRONMENT", "development")

        settings = Settings()

        assert settings.debug is True
        assert settings.reload is True

    def test_debug_disabled_in_production(self, monkeypatch):
        """Test debug disabled in production."""
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("SECRET_KEY", "prod-key")

        settings = Settings()

        assert settings.debug is False
        assert settings.reload is False
        assert settings.database_echo is False


class TestGetSettings:
    """Test get_settings factory function."""

    def test_get_settings_singleton(self):
        """Test get_settings returns cached singleton."""
        clear_settings_cache()

        settings1 = get_settings()
        settings2 = get_settings()

        assert settings1 is settings2  # Same instance

    def test_clear_settings_cache(self, monkeypatch):
        """Test clearing settings cache."""
        clear_settings_cache()

        # Get settings with custom env
        monkeypatch.setenv("APP_NAME", "First Name")
        settings1 = get_settings()
        assert settings1.app_name == "First Name"

        # Clear cache and change env
        clear_settings_cache()
        monkeypatch.setenv("APP_NAME", "Second Name")
        settings2 = get_settings()

        assert settings2.app_name == "Second Name"
        assert settings1 is not settings2  # Different instances

    def test_get_settings_with_env_file(self, tmp_path, monkeypatch):
        """Test loading settings from .env file."""
        # Create temporary .env file
        env_file = tmp_path / ".env"
        env_file.write_text("APP_NAME=Test App\nPORT=7000\nDEBUG=true\n")

        # Change to temp directory
        monkeypatch.chdir(tmp_path)
        clear_settings_cache()

        settings = get_settings()

        assert settings.app_name == "Test App"
        assert settings.port == 7000


class TestEnvironmentVariablePriority:
    """Test priority of different configuration sources."""

    def test_env_var_overrides_default(self, monkeypatch):
        """Test environment variable overrides default."""
        monkeypatch.setenv("PORT", "5000")
        clear_settings_cache()

        settings = get_settings()
        assert settings.port == 5000

    def test_case_insensitive_env_vars(self, monkeypatch):
        """Test case-insensitive environment variables."""
        monkeypatch.setenv("app_name", "Lower Case App")
        clear_settings_cache()

        settings = get_settings()
        assert settings.app_name == "Lower Case App"


class TestSettingsIntegration:
    """Integration tests for full settings usage."""

    def test_complete_configuration(self, monkeypatch):
        """Test loading complete configuration."""
        monkeypatch.setenv("ENVIRONMENT", "staging")
        monkeypatch.setenv("APP_NAME", "Staging API")
        monkeypatch.setenv("DATABASE_URL", "postgresql://staging-db/db")
        monkeypatch.setenv("REDIS_URL", "redis://staging-redis:6379/0")
        monkeypatch.setenv("LOG_LEVEL", "WARNING")
        clear_settings_cache()

        settings = get_settings()

        assert settings.environment == Environment.STAGING
        assert settings.app_name == "Staging API"
        assert "staging-db" in settings.database_url
        assert "staging-redis" in settings.redis_url
        assert settings.log_level == "WARNING"

    def test_production_configuration(self, monkeypatch):
        """Test production-specific configuration."""
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("SECRET_KEY", "super-secure-production-key")
        monkeypatch.setenv("DATABASE_POOL_SIZE", "50")
        monkeypatch.setenv("CORS_ORIGINS", '["https://example.com"]')
        clear_settings_cache()

        settings = get_settings()

        assert settings.is_production
        assert settings.debug is False
        assert settings.reload is False
        assert settings.database_pool_size == 50
