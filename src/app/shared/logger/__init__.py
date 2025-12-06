"""
Advanced Logger Module for OpenTaberna.

A production-ready logging system built following SOLID principles.

Quick Start:
    from app.shared.logger import get_logger, LogContext

    logger = get_logger(__name__)
    logger.info("Application started", version="1.0.0")

    with LogContext(request_id="abc-123"):
        logger.info("Processing request")

Architecture:
    - enums: Enumerations and constants
    - interfaces: Abstract base classes (SOLID interfaces)
    - formatters: Log formatting implementations
    - filters: Log filtering and sanitization
    - handlers: Output handlers (console, file, etc.)
    - config: Configuration management
    - context: Context management for request tracking
    - logger: Main AppLogger class
    - factory: Logger creation and caching
"""

# Main API
from .factory import get_logger, clear_loggers
from .logger import AppLogger
from .context import LogContext, setup_request_logging
from .config import LoggerConfig

# Enums
from .enums import LogLevel, Environment

# Interfaces (for custom implementations)
from .interfaces import ILogFormatter, ILogFilter, ILogHandler

# Implementations
from .formatters import JSONFormatter, ConsoleFormatter
from .filters import SensitiveDataFilter, LevelFilter
from .handlers import ConsoleHandler, FileHandler, DailyRotatingFileHandler


__all__ = [
    # Main API
    "get_logger",
    "clear_loggers",
    "AppLogger",
    "LogContext",
    "LoggerConfig",
    "setup_request_logging",
    # Enums
    "LogLevel",
    "Environment",
    # Interfaces (for custom implementations)
    "ILogFormatter",
    "ILogFilter",
    "ILogHandler",
    # Implementations
    "JSONFormatter",
    "ConsoleFormatter",
    "SensitiveDataFilter",
    "LevelFilter",
    "ConsoleHandler",
    "FileHandler",
    "DailyRotatingFileHandler",
]

__version__ = "1.0.0"
