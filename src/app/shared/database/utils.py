"""
Database Utilities

Common utilities and optional imports for database module.
Reduces code duplication across database components.
"""

import logging
from typing import TYPE_CHECKING

# Optional logger import with fallback
try:
    from app.shared.logger import get_logger as _get_logger

    def get_logger(name: str):
        """Get logger from shared module."""
        return _get_logger(name)

except ImportError:

    def get_logger(name: str):
        """Fallback to standard logging."""
        return logging.getLogger(name)


# Optional exception imports with fallbacks
if TYPE_CHECKING:
    from app.shared.exceptions import DatabaseError, NotFoundError, InternalError
else:
    try:
        from app.shared.exceptions import DatabaseError, NotFoundError, InternalError
    except ImportError:
        # Fallback exception classes if shared module not available

        class DatabaseError(Exception):  # type: ignore
            """Database operation error fallback."""

            def __init__(
                self,
                message: str,
                context: dict | None = None,
                original_exception: Exception | None = None,
            ):
                super().__init__(message)
                self.message = message
                self.context = context or {}
                self.original_exception = original_exception

        class NotFoundError(Exception):  # type: ignore
            """Entity not found error fallback."""

            def __init__(
                self,
                message: str,
                context: dict | None = None,
            ):
                super().__init__(message)
                self.message = message
                self.context = context or {}

        class InternalError(Exception):  # type: ignore
            """Internal system error fallback."""

            def __init__(
                self,
                message: str,
                context: dict | None = None,
            ):
                super().__init__(message)
                self.message = message
                self.context = context or {}


# Optional config import with fallback
try:
    from app.shared.config import get_settings
except ImportError:
    get_settings = None  # type: ignore


__all__ = [
    "get_logger",
    "DatabaseError",
    "NotFoundError",
    "InternalError",
    "get_settings",
]
