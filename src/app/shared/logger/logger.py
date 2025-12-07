"""
Main AppLogger class orchestrating all components.

This class follows SOLID principles by depending on interfaces,
not concrete implementations.
"""

import logging
import time
from contextlib import contextmanager

from app.shared.config.enums import Environment

from .config import LoggerConfig
from .enums import LogLevel
from .filters import SensitiveDataFilter
from .formatters import ConsoleFormatter, JSONFormatter
from .interfaces import ILogFilter


class AppLogger:
    """
    Main logger class following SOLID principles.

    This class orchestrates formatters, handlers, and filters without
    tight coupling to specific implementations.
    """

    def __init__(self, config: LoggerConfig):
        self.config = config
        self._logger = self._setup_logger()
        self._sensitive_filter = next(
            (f for f in config.filters if isinstance(f, SensitiveDataFilter)),
            SensitiveDataFilter(),
        )

    def _setup_logger(self) -> logging.Logger:
        """Initialize and configure the logger."""
        logger = logging.getLogger(self.config.name)
        logger.setLevel(getattr(logging, self.config.level.value))
        logger.propagate = False

        # Clear existing handlers
        logger.handlers.clear()

        # Determine formatter based on environment
        if self.config.environment == Environment.DEVELOPMENT:
            formatter = ConsoleFormatter(use_colors=True)
        else:
            formatter = JSONFormatter(include_extra=True)

        # Setup all handlers
        for handler in self.config.handlers:
            handler.setup(logger, formatter)

        # Add filters
        for log_filter in self.config.filters:
            if hasattr(log_filter, "filter"):
                logger.addFilter(_FilterWrapper(log_filter))

        return logger

    def debug(self, message: str, **kwargs):
        """Log debug message."""
        self._log(LogLevel.DEBUG, message, **kwargs)

    def info(self, message: str, **kwargs):
        """Log info message."""
        self._log(LogLevel.INFO, message, **kwargs)

    def warning(self, message: str, **kwargs):
        """Log warning message."""
        self._log(LogLevel.WARNING, message, **kwargs)

    def error(self, message: str, exc_info: bool = False, **kwargs):
        """Log error message."""
        self._log(LogLevel.ERROR, message, exc_info=exc_info, **kwargs)

    def critical(self, message: str, exc_info: bool = True, **kwargs):
        """Log critical message."""
        self._log(LogLevel.CRITICAL, message, exc_info=exc_info, **kwargs)

    def exception(self, message: str, **kwargs):
        """Log exception with traceback."""
        self._log(LogLevel.ERROR, message, exc_info=True, **kwargs)

    def _log(self, level: LogLevel, message: str, exc_info: bool = False, **kwargs):
        """Internal logging method."""
        # Reserved LogRecord attributes that cannot be overridden
        reserved_attrs = {
            "name",
            "msg",
            "args",
            "created",
            "filename",
            "funcName",
            "levelname",
            "levelno",
            "lineno",
            "module",
            "msecs",
            "message",
            "pathname",
            "process",
            "processName",
            "relativeCreated",
            "thread",
            "threadName",
            "exc_info",
            "exc_text",
            "stack_info",
            "taskName",
        }

        # Sanitize kwargs
        sanitized_kwargs = self._sensitive_filter.sanitize(kwargs)

        # Remove any reserved attributes from kwargs to avoid conflicts
        safe_kwargs = {
            k: v for k, v in sanitized_kwargs.items() if k not in reserved_attrs
        }

        # Get log method
        log_method = getattr(self._logger, level.value.lower())

        # Log with extra fields
        log_method(message, exc_info=exc_info, extra=safe_kwargs)

    @contextmanager
    def measure_time(self, operation: str, **context):
        """
        Context manager to measure execution time.

        Usage:
            with logger.measure_time("database_query", query_type="SELECT"):
                # ... operation
                pass
        """
        start_time = time.perf_counter()
        self.debug(f"Starting {operation}", **context)

        try:
            yield
        except Exception:
            duration = time.perf_counter() - start_time
            self.error(
                f"Failed {operation}",
                duration_ms=duration * 1000,
                exc_info=True,
                **context,
            )
            raise
        else:
            duration = time.perf_counter() - start_time
            self.info(f"Completed {operation}", duration_ms=duration * 1000, **context)


class _FilterWrapper(logging.Filter):
    """Wrapper to use custom ILogFilter with logging.Logger."""

    def __init__(self, custom_filter: ILogFilter):
        super().__init__()
        self.custom_filter = custom_filter

    def filter(self, record: logging.LogRecord) -> bool:
        return self.custom_filter.filter(record)
