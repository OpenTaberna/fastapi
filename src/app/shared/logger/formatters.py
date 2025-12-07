"""
Log formatters following Open/Closed Principle.

New formatters can be added by implementing ILogFormatter without modifying existing code.
"""

import json
import sys
import traceback
from datetime import datetime
import logging

from .interfaces import ILogFormatter
from .context import get_log_context


class JSONFormatter(ILogFormatter):
    """Structured JSON formatter for production environments."""

    def __init__(self, include_extra: bool = True):
        self.include_extra = include_extra

    def format(self, record: logging.LogRecord) -> str:
        """Format record as JSON string."""
        log_data = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add context data
        context = get_log_context()
        if context:
            log_data["context"] = context

        # Add extra fields
        if self.include_extra:
            # List of reserved LogRecord attributes
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

            extra_fields = {
                key: value
                for key, value in record.__dict__.items()
                if key not in reserved_attrs
            }
            if extra_fields:
                log_data["extra"] = extra_fields

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "traceback": traceback.format_exception(*record.exc_info),
            }

        return json.dumps(log_data, default=str)


class ConsoleFormatter(ILogFormatter):
    """Human-readable formatter for development environments."""

    COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[35m",  # Magenta
        "RESET": "\033[0m",
    }

    def __init__(self, use_colors: bool = True):
        self.use_colors = use_colors and sys.stderr.isatty()

    def format(self, record: logging.LogRecord) -> str:
        """Format record for console output."""
        timestamp = datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S")
        level = record.levelname

        if self.use_colors:
            color = self.COLORS.get(level, "")
            reset = self.COLORS["RESET"]
            level = f"{color}{level}{reset}"

        base_msg = f"[{timestamp}] {level:<8} {record.name}: {record.getMessage()}"

        # Add context if present
        context = get_log_context()
        if context:
            context_str = " ".join(f"{k}={v}" for k, v in context.items())
            base_msg += f" | {context_str}"

        # Add exception if present
        if record.exc_info:
            base_msg += f"\n{''.join(traceback.format_exception(*record.exc_info))}"

        return base_msg
