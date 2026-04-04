"""
Application Settings

Environment-based configuration with support for:
- .env files
- Docker secrets
- Kubernetes secrets
- Environment variables
"""

from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.shared.config.enums import Environment
from app.shared.config.loader import load_secret


class Settings(BaseSettings):
    """
    Application settings.

    Loads configuration from (in order of priority):
    1. Docker/K8s secrets
    2. Environment variables
    3. .env file
    4. Default values

    Example:
        >>> settings = Settings()
        >>> print(settings.database_url)
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = Field(default="OpenTaberna API", description="Application name")
    app_version: str = Field(default="0.1.0", description="Application version")
    environment: Environment = Field(
        default=Environment.DEVELOPMENT, description="Application environment"
    )
    debug: bool = Field(default=False, description="Debug mode")
    secret_key: str = Field(
        default="CHANGE_ME_IN_PRODUCTION", description="Secret key for JWT/sessions"
    )

    # Server
    host: str = Field(default="0.0.0.0", description="Server host")
    port: int = Field(default=8000, description="Server port")
    workers: int = Field(default=1, description="Number of worker processes")
    reload: bool = Field(default=False, description="Auto-reload on code changes")

    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://opentaberna:opentaberna@localhost:5432/opentaberna",
        description="Database connection URL",
    )
    database_pool_size: int = Field(default=20, description="Database pool size")
    database_max_overflow: int = Field(
        default=40, description="Database pool max overflow"
    )
    database_pool_timeout: int = Field(
        default=30, description="Database pool timeout in seconds"
    )
    database_pool_recycle: int = Field(
        default=3600, description="Connection recycle time in seconds"
    )
    database_pool_pre_ping: bool = Field(
        default=True, description="Test connections before using them"
    )
    database_echo: bool = Field(
        default=False, description="Echo SQL queries (for debugging)"
    )
    database_echo_pool: bool = Field(
        default=False, description="Echo connection pool events"
    )
    database_statement_timeout: int = Field(
        default=60000, description="Statement timeout in milliseconds"
    )
    database_command_timeout: int = Field(
        default=60, description="Command timeout in seconds"
    )
    database_server_settings: dict[str, str] = Field(
        default_factory=lambda: {
            "application_name": "OpenTaberna API",
            "jit": "off",  # JIT can cause issues with some queries
        },
        description="PostgreSQL server settings",
    )

    # Redis
    redis_url: str = Field(
        default="redis://localhost:6379/0", description="Redis connection URL"
    )
    redis_password: str | None = Field(default=None, description="Redis password")

    # Keycloak
    keycloak_url: str = Field(
        default="http://localhost:8080", description="Keycloak server URL"
    )
    keycloak_realm: str = Field(
        default="opentaberna", description="Keycloak realm name"
    )
    keycloak_client_id: str = Field(
        default="opentaberna-api", description="Keycloak client ID"
    )
    keycloak_client_secret: str = Field(
        default="", description="Keycloak client secret"
    )

    # CORS
    cors_origins: list[str] = Field(default=["*"], description="Allowed CORS origins")
    cors_credentials: bool = Field(
        default=True, description="Allow credentials in CORS"
    )

    # Logging
    log_level: str = Field(default="INFO", description="Logging level")
    log_format: str = Field(
        default="console", description="Log format: console or json"
    )
    log_file: str | None = Field(default=None, description="Log file path")

    # Cache
    cache_enabled: bool = Field(default=True, description="Enable caching")
    cache_ttl: int = Field(default=300, description="Default cache TTL in seconds")

    # Rate Limiting
    rate_limit_enabled: bool = Field(default=True, description="Enable rate limiting")
    rate_limit_per_minute: int = Field(
        default=60, description="Rate limit requests per minute"
    )

    # Stripe
    stripe_secret_key: str = Field(
        default="CHANGE_ME_IN_PRODUCTION",
        description="Stripe secret key (sk_test_... or sk_live_...)",
    )
    stripe_webhook_secret: str = Field(
        default="CHANGE_ME_IN_PRODUCTION",
        description="Stripe webhook signing secret (whsec_...)",
    )
    stripe_publishable_key: str = Field(
        default="",
        description="Stripe publishable key (pk_test_... or pk_live_...)",
    )
    stripe_payment_methods: list[str] = Field(
        default=["card", "paypal", "bank_transfer"],
        description="Enabled payment methods: card | paypal | bank_transfer",
    )
    stripe_bank_transfer_country: str = Field(
        default="DE",
        description="ISO 3166-1 alpha-2 country for EU bank transfer virtual IBAN",
    )

    # SMTP / Transactional email
    smtp_host: str = Field(
        default="",
        description="SMTP server hostname (leave empty to disable email sending)",
    )
    smtp_port: int = Field(
        default=587, description="SMTP server port (587=STARTTLS, 465=SSL)"
    )
    smtp_user: str = Field(default="", description="SMTP authentication username")
    smtp_password: str = Field(default="", description="SMTP authentication password")
    email_from: str = Field(
        default="noreply@opentaberna.local",
        description="Envelope sender address for outgoing emails",
    )

    # Feature Flags
    feature_webhooks_enabled: bool = Field(default=False, description="Enable webhooks")

    # Order reservations
    reservation_ttl_minutes: int = Field(
        default=15,
        description="How long (in minutes) a stock reservation is held before it expires",
    )

    @field_validator("secret_key")
    @classmethod
    def validate_secret_key(cls, v: str, info: Any) -> str:
        """Ensure secret key is changed in production."""
        env = info.data.get("environment", Environment.DEVELOPMENT)
        if env == Environment.PRODUCTION and v == "CHANGE_ME_IN_PRODUCTION":
            raise ValueError("SECRET_KEY must be changed in production!")
        return v

    @field_validator("database_url", mode="before")
    @classmethod
    def load_database_url(cls, v: str | None) -> str:
        """Load database URL from secrets if available."""
        if v:
            return v
        return load_secret("database_url") or v or ""

    @field_validator("redis_password", mode="before")
    @classmethod
    def load_redis_password(cls, v: str | None) -> str | None:
        """Load Redis password from secrets if available."""
        if v:
            return v
        return load_secret("redis_password")

    @field_validator("keycloak_client_secret", mode="before")
    @classmethod
    def load_keycloak_secret(cls, v: str | None) -> str:
        """Load Keycloak client secret from secrets if available."""
        if v:
            return v
        return load_secret("keycloak_client_secret") or v or ""

    @field_validator("stripe_secret_key", mode="before")
    @classmethod
    def load_stripe_secret_key(cls, v: str | None) -> str:
        """Load Stripe secret key from secrets if available."""
        if v:
            return v
        return load_secret("stripe_secret_key") or v or "CHANGE_ME_IN_PRODUCTION"

    @field_validator("stripe_webhook_secret", mode="before")
    @classmethod
    def load_stripe_webhook_secret(cls, v: str | None) -> str:
        """Load Stripe webhook secret from secrets if available."""
        if v:
            return v
        return load_secret("stripe_webhook_secret") or v or "CHANGE_ME_IN_PRODUCTION"

    def model_post_init(self, __context: Any) -> None:
        """Post-initialization processing."""
        # Auto-enable debug in development
        if self.environment.is_development():
            self.debug = True
            self.reload = True

        # Ensure security in production
        if self.environment.is_production():
            self.debug = False
            self.reload = False
            self.database_echo = False

    @property
    def is_production(self) -> bool:
        """Check if running in production."""
        return self.environment.is_production()

    @property
    def is_testing(self) -> bool:
        """Check if running in testing mode."""
        return self.environment.is_testing()

    @property
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.environment.is_development()

    def get_database_url(self, hide_password: bool = False) -> str:
        """
        Get database URL, optionally hiding password.

        Args:
            hide_password: If True, replace password with ***

        Returns:
            Database URL string
        """
        if not hide_password:
            return self.database_url

        # Simple password hiding
        if "@" in self.database_url:
            protocol, rest = self.database_url.split("://", 1)
            if "@" in rest:
                creds, host = rest.split("@", 1)
                if ":" in creds:
                    user = creds.split(":")[0]
                    return f"{protocol}://{user}:***@{host}"
        return self.database_url
