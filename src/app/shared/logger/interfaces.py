"""
Interfaces (Abstract Base Classes) for the logging system.

Following Interface Segregation Principle - focused, minimal interfaces.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict
import logging


class ILogFormatter(ABC):
    """Interface for log formatters."""

    @abstractmethod
    def format(self, record: logging.LogRecord) -> str:
        """Format a log record into a string."""
        pass


class ILogFilter(ABC):
    """Interface for log filters."""

    @abstractmethod
    def filter(self, record: logging.LogRecord) -> bool:
        """Determine if a record should be logged."""
        pass

    @abstractmethod
    def sanitize(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Remove sensitive information from log data."""
        pass


class ILogHandler(ABC):
    """Interface for log handlers."""

    @abstractmethod
    def setup(self, logger: logging.Logger, formatter: ILogFormatter) -> None:
        """Configure and attach handler to logger."""
        pass
