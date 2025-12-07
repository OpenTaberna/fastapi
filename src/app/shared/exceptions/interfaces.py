"""
Interfaces (Abstract Base Classes) for the exception system.

Following Interface Segregation Principle - focused, minimal interfaces.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict
from .enums import ErrorCategory, ErrorCode


class IAppException(ABC):
    """
    Interface for application exceptions.

    Defines the contract that all custom exceptions must implement.
    """

    @abstractmethod
    def get_message(self) -> str:
        """Get the human-readable error message."""
        pass

    @abstractmethod
    def get_error_code(self) -> ErrorCode:
        """Get the specific error code."""
        pass

    @abstractmethod
    def get_category(self) -> ErrorCategory:
        """Get the error category."""
        pass

    @abstractmethod
    def get_context(self) -> Dict[str, Any]:
        """Get additional context data about the error."""
        pass

    @abstractmethod
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert exception to dictionary for logging and API responses.

        Returns:
            Dictionary with error details
        """
        pass

    @abstractmethod
    def should_log(self) -> bool:
        """
        Determine if this exception should be automatically logged.

        Returns:
            True if exception should be logged, False otherwise
        """
        pass


class IExceptionHandler(ABC):
    """Interface for exception handlers."""

    @abstractmethod
    def handle(self, exception: IAppException) -> Any:
        """
        Handle an application exception.

        Args:
            exception: The exception to handle

        Returns:
            Handler-specific result (e.g., HTTP response)
        """
        pass

    @abstractmethod
    def can_handle(self, exception: Exception) -> bool:
        """
        Check if this handler can handle the given exception.

        Args:
            exception: The exception to check

        Returns:
            True if handler can handle this exception
        """
        pass
