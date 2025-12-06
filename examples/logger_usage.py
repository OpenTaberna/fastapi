"""
Example usage of the refactored logger module.

This demonstrates how to use the logger in your application code.
"""

from app.shared.logger import get_logger, LogContext

# Create logger for this module
logger = get_logger(__name__)


def example_basic_usage():
    """Example of basic logging."""
    logger.info("Application started")
    logger.debug("Debug information", component="example")
    logger.warning("Warning message", threshold=80)


def example_with_context():
    """Example of logging with context."""
    with LogContext(request_id="req-12345", user_id="user-67890"):
        logger.info("Received user request")
        logger.info("Processing order", order_id="ord-999")


def example_exception_handling():
    """Example of exception logging."""
    try:
        risky_operation()
    except Exception:
        logger.exception("Failed to process", operation="risky")


def example_performance_tracking():
    """Example of performance measurement."""
    with logger.measure_time("database_query", table="users"):
        # Simulate database operation
        import time

        time.sleep(0.05)


def risky_operation():
    """Simulate a risky operation."""
    raise ValueError("Something went wrong!")


if __name__ == "__main__":
    print("Running logger examples...\n")

    example_basic_usage()
    print()

    example_with_context()
    print()

    example_exception_handling()
    print()

    example_performance_tracking()
    print()

    print("Examples completed!")
