"""
Log handlers following Liskov Substitution Principle.

All handlers are interchangeable through the ILogHandler interface.
"""

import logging
import sys
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from pathlib import Path

from .interfaces import ILogFormatter, ILogHandler
from .enums import LogLevel


class _FormatterWrapper(logging.Formatter):
    """Wrapper to use custom ILogFormatter with logging.Handler."""

    def __init__(self, custom_formatter: ILogFormatter):
        super().__init__()
        self.custom_formatter = custom_formatter

    def format(self, record: logging.LogRecord) -> str:
        return self.custom_formatter.format(record)


class ConsoleHandler(ILogHandler):
    """Handler for console output."""

    def __init__(self, level: LogLevel = LogLevel.INFO):
        self.level = level

    def setup(self, logger: logging.Logger, formatter: ILogFormatter) -> None:
        """Setup console handler."""
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(getattr(logging, self.level.value))
        handler.setFormatter(_FormatterWrapper(formatter))
        logger.addHandler(handler)


class FileHandler(ILogHandler):
    """Handler for file output with rotation."""

    def __init__(
        self,
        filepath: Path,
        level: LogLevel = LogLevel.INFO,
        max_bytes: int = 10 * 1024 * 1024,  # 10MB
        backup_count: int = 5,
    ):
        self.filepath = filepath
        self.level = level
        self.max_bytes = max_bytes
        self.backup_count = backup_count

    def setup(self, logger: logging.Logger, formatter: ILogFormatter) -> None:
        """Setup rotating file handler."""
        self.filepath.parent.mkdir(parents=True, exist_ok=True)

        handler = RotatingFileHandler(
            filename=str(self.filepath),
            maxBytes=self.max_bytes,
            backupCount=self.backup_count,
            encoding="utf-8",
        )
        handler.setLevel(getattr(logging, self.level.value))
        handler.setFormatter(_FormatterWrapper(formatter))
        logger.addHandler(handler)


class DailyRotatingFileHandler(ILogHandler):
    """Handler for daily rotating file output."""

    def __init__(
        self, filepath: Path, level: LogLevel = LogLevel.INFO, backup_count: int = 30
    ):
        self.filepath = filepath
        self.level = level
        self.backup_count = backup_count

    def setup(self, logger: logging.Logger, formatter: ILogFormatter) -> None:
        """Setup daily rotating file handler."""
        self.filepath.parent.mkdir(parents=True, exist_ok=True)

        handler = TimedRotatingFileHandler(
            filename=str(self.filepath),
            when="midnight",
            interval=1,
            backupCount=self.backup_count,
            encoding="utf-8",
        )
        handler.setLevel(getattr(logging, self.level.value))
        handler.setFormatter(_FormatterWrapper(formatter))
        logger.addHandler(handler)
