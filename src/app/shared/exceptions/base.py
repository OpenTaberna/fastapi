"""
Base exception class for all application exceptions.

Provides automatic logging and context management.
"""

from typing import Any, Dict, Optional
from .interfaces import IAppException
from .enums import ErrorCategory, ErrorCode


class AppException(Exception, IAppException):
    """
    Base class for all application exceptions.

    Implements automatic logging and provides a rich context for error handling.
    All custom exceptions should inherit from this class.

    Attributes:
        message: Human-readable error message
        error_code: Specific error code for identification
        category: Error category for classification
        context: Additional context data
        original_exception: Original exception if this wraps another exception
        should_auto_log: Whether to automatically log this exception
    """

    def __init__(
        self,
        message: str,
        error_code: ErrorCode,
        category: ErrorCategory,
        context: Optional[Dict[str, Any]] = None,
        original_exception: Optional[Exception] = None,
        should_auto_log: bool = True,
    ):
        """
        Initialize application exception.

        Args:
            message: Human-readable error message
            error_code: Specific error code
            category: Error category
            context: Additional context data (e.g., field names, entity IDs)
            original_exception: Original exception if wrapping another exception
            should_auto_log: Whether to automatically log this exception
        """
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.category = category
        self.context = context or {}
        self.original_exception = original_exception
        self.should_auto_log = should_auto_log

        # Automatic logging
        if self.should_auto_log:
            self._log_exception()

    def get_message(self) -> str:
        """Get the human-readable error message."""
        return self.message

    def get_error_code(self) -> ErrorCode:
        """Get the specific error code."""
        return self.error_code

    def get_category(self) -> ErrorCategory:
        """Get the error category."""
        return self.category

    def get_context(self) -> Dict[str, Any]:
        """Get additional context data about the error."""
        return self.context

    def should_log(self) -> bool:
        """Determine if this exception should be automatically logged."""
        return self.should_auto_log

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert exception to dictionary for logging and API responses.

        Returns:
            Dictionary with error details
        """
        result = {
            "error": {
                "message": self.message,
                "code": self.error_code.value,
                "category": self.category.value,
            }
        }

        # Add context if present
        if self.context:
            result["error"]["context"] = self.context

        # Add original exception info if present
        if self.original_exception:
            result["error"]["original_error"] = {
                "type": type(self.original_exception).__name__,
                "message": str(self.original_exception),
            }

        return result

    def _log_exception(self) -> None:
        """
        Log the exception automatically using the logger module.

        Uses appropriate log level based on error category:
        - Client errors (4xx): WARNING
        - Server errors (5xx): ERROR
        """
        try:
            from app.shared.logger import get_logger

            logger = get_logger(__name__)

            # Prepare log data
            log_data = {
                "error_code": self.error_code.value,
                "category": self.category.value,
                **self.context,
            }

            # Add original exception if present
            if self.original_exception:
                log_data["original_error"] = type(self.original_exception).__name__
                log_data["original_message"] = str(self.original_exception)

            # Log with appropriate level
            if self.category.is_client_error():
                logger.warning(
                    self.message,
                    **log_data,
                    exc_info=self.original_exception is not None,
                )
            else:
                logger.error(
                    self.message,
                    **log_data,
                    exc_info=True,  # Always include stack trace for server errors
                )

        except Exception as e:
            # Fallback: Don't let logging failure break the application
            # Just print to stderr
            import sys

            print(
                f"Failed to log exception: {e}. Original error: {self.message}",
                file=sys.stderr,
            )

    def __str__(self) -> str:
        """String representation of the exception."""
        context_str = f", context={self.context}" if self.context else ""
        return f"{self.category.value.upper()}: [{self.error_code.value}] {self.message}{context_str}"

    def __repr__(self) -> str:
        """Detailed representation of the exception."""
        return (
            f"{self.__class__.__name__}("
            f"message='{self.message}', "
            f"error_code={self.error_code.value}, "
            f"category={self.category.value}, "
            f"context={self.context})"
        )
