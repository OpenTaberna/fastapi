"""
Logger configuration following Dependency Inversion Principle.

Configuration depends on abstractions (interfaces), not concrete implementations.
"""

from pathlib import Path
from typing import List, Optional

from app.shared.config.enums import Environment

from .enums import LogLevel
from .filters import SensitiveDataFilter
from .handlers import ConsoleHandler, DailyRotatingFileHandler, FileHandler
from .interfaces import ILogFilter, ILogHandler


class LoggerConfig:
    """Configuration for logger setup."""

    def __init__(
        self,
        name: str,
        level: LogLevel = LogLevel.INFO,
        handlers: Optional[List[ILogHandler]] = None,
        filters: Optional[List[ILogFilter]] = None,
        environment: Environment = Environment.DEVELOPMENT,
    ):
        self.name = name
        self.level = level
        self.handlers = handlers or []
        self.filters = filters or [SensitiveDataFilter()]
        self.environment = environment

    @classmethod
    def from_environment(
        cls, name: str, env: Environment, log_dir: Optional[Path] = None
    ) -> "LoggerConfig":
        """Create configuration based on environment."""
        if env == Environment.DEVELOPMENT:
            return cls._development_config(name)
        elif env == Environment.TESTING:
            return cls._testing_config(name)
        elif env == Environment.STAGING:
            return cls._staging_config(name, log_dir)
        else:  # PRODUCTION
            return cls._production_config(name, log_dir)

    @classmethod
    def _development_config(cls, name: str) -> "LoggerConfig":
        """Development environment configuration."""
        return cls(
            name=name,
            level=LogLevel.DEBUG,
            handlers=[ConsoleHandler(LogLevel.DEBUG)],
            filters=[SensitiveDataFilter()],
            environment=Environment.DEVELOPMENT,
        )

    @classmethod
    def _testing_config(cls, name: str) -> "LoggerConfig":
        """Testing environment configuration."""
        return cls(
            name=name,
            level=LogLevel.WARNING,
            handlers=[ConsoleHandler(LogLevel.WARNING)],
            filters=[SensitiveDataFilter()],
            environment=Environment.TESTING,
        )

    @classmethod
    def _staging_config(cls, name: str, log_dir: Optional[Path]) -> "LoggerConfig":
        """Staging environment configuration."""
        log_dir = log_dir or Path("/var/log/opentaberna")

        return cls(
            name=name,
            level=LogLevel.INFO,
            handlers=[
                ConsoleHandler(LogLevel.INFO),
                FileHandler(
                    filepath=log_dir / "app.log",
                    level=LogLevel.INFO,
                    max_bytes=50 * 1024 * 1024,  # 50MB
                    backup_count=5,
                ),
                FileHandler(
                    filepath=log_dir / "error.log",
                    level=LogLevel.ERROR,
                    max_bytes=50 * 1024 * 1024,
                    backup_count=5,
                ),
            ],
            filters=[SensitiveDataFilter()],
            environment=Environment.STAGING,
        )

    @classmethod
    def _production_config(cls, name: str, log_dir: Optional[Path]) -> "LoggerConfig":
        """Production environment configuration."""
        log_dir = log_dir or Path("/var/log/opentaberna")

        return cls(
            name=name,
            level=LogLevel.INFO,
            handlers=[
                ConsoleHandler(LogLevel.WARNING),
                DailyRotatingFileHandler(
                    filepath=log_dir / "app.log", level=LogLevel.INFO, backup_count=30
                ),
                DailyRotatingFileHandler(
                    filepath=log_dir / "error.log",
                    level=LogLevel.ERROR,
                    backup_count=90,
                ),
            ],
            filters=[SensitiveDataFilter()],
            environment=Environment.PRODUCTION,
        )
