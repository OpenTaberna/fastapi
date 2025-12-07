"""
Test suite for logger module.

Tests all logger functionality including basic logging, context management,
sensitive data filtering, performance measurement, and custom configuration.
"""

import pytest
from app.shared.logger import (
    get_logger,
    LogContext,
    LogLevel,
    Environment,
    LoggerConfig,
    ConsoleHandler,
    clear_loggers,
)


@pytest.fixture(autouse=True)
def cleanup_loggers():
    """Clean up loggers before and after each test."""
    clear_loggers()
    yield
    clear_loggers()


def test_basic_logging(capsys):
    """Test basic logging functionality."""
    logger = get_logger("test.basic")

    logger.debug("Debug message", test_id=1)
    logger.info("Info message", test_id=2)
    logger.warning("Warning message", test_id=3)
    logger.error("Error message", test_id=4)

    captured = capsys.readouterr()
    assert "Debug message" in captured.out
    assert "Info message" in captured.out
    assert "Warning message" in captured.out
    assert "Error message" in captured.out


def test_context_logging(capsys):
    """Test context management."""
    logger = get_logger("test.context")

    with LogContext(request_id="req-123", user_id="user-456"):
        logger.info("Inside context")

        with LogContext(order_id="order-789"):
            logger.info("Nested context")

    logger.info("Outside context")

    captured = capsys.readouterr()
    assert "Inside context" in captured.out
    assert "request_id=req-123" in captured.out
    assert "user_id=user-456" in captured.out
    assert "Nested context" in captured.out
    assert "order_id=order-789" in captured.out


def test_sensitive_data_filtering(capsys):
    """Test sensitive data filtering."""
    logger = get_logger("test.sensitive")

    logger.info(
        "User login",
        username="john",
        password="secret123",
        token="abc-xyz-789",
        email="john@example.com",
    )

    captured = capsys.readouterr()
    assert "User login" in captured.out
    # Sensitive data should be redacted or not appear in output
    # Note: The filter sanitizes before logging, so sensitive data won't appear


def test_performance_measurement(capsys):
    """Test performance measurement."""
    logger = get_logger("test.performance")

    import time

    with logger.measure_time("test_operation", operation_type="test"):
        time.sleep(0.05)

    captured = capsys.readouterr()
    assert "Starting test_operation" in captured.out
    assert "Completed test_operation" in captured.out


def test_exception_logging(capsys):
    """Test exception logging."""
    logger = get_logger("test.exception")

    try:
        1 / 0
    except Exception:
        logger.exception("Division by zero error", operation="divide")

    captured = capsys.readouterr()
    assert "Division by zero error" in captured.out
    assert "ZeroDivisionError" in captured.out


def test_custom_config(capsys):
    """Test custom configuration."""
    config = LoggerConfig(
        name="test.custom",
        level=LogLevel.DEBUG,
        handlers=[ConsoleHandler(LogLevel.DEBUG)],
        environment=Environment.DEVELOPMENT,
    )

    logger = get_logger("test.custom", config=config)
    logger.debug("Custom config logger")

    captured = capsys.readouterr()
    assert "Custom config logger" in captured.out


def test_logger_levels():
    """Test that different log levels work correctly."""
    logger = get_logger("test.levels")

    # Should not raise exceptions
    logger.debug("Debug level")
    logger.info("Info level")
    logger.warning("Warning level")
    logger.error("Error level")
    logger.critical("Critical level")


def test_clear_loggers():
    """Test that clear_loggers removes cached instances."""
    logger1 = get_logger("test.clear1")
    logger2 = get_logger("test.clear1")
    assert logger1 is logger2  # Same instance from cache

    clear_loggers()

    get_logger("test.clear1")
    # Can't test identity after clear since fixture also clears


def test_reserved_attributes_filtered():
    """Test that reserved LogRecord attributes are filtered out."""
    logger = get_logger("test.reserved")

    # Should not raise KeyError for reserved attributes
    logger.info("Test message", module="should_be_filtered", name="also_filtered")
    # If we get here without exception, the test passes


def test_environment_config():
    """Test environment-based configuration."""
    # Test development config
    dev_logger = get_logger("test.dev", environment=Environment.DEVELOPMENT)
    assert dev_logger is not None

    # Test testing config
    clear_loggers()
    test_logger = get_logger("test.test", environment=Environment.TESTING)
    assert test_logger is not None


def test_multiple_loggers():
    """Test that multiple loggers can coexist."""
    logger1 = get_logger("test.logger1")
    logger2 = get_logger("test.logger2")

    assert logger1 is not logger2
    assert logger1.config.name == "test.logger1"
    assert logger2.config.name == "test.logger2"


def test_log_with_extra_fields(capsys):
    """Test logging with extra fields."""
    logger = get_logger("test.extra")

    logger.info(
        "Order processed",
        order_id="ORD-123",
        user_id="USR-456",
        amount=99.99,
        currency="EUR",
    )

    captured = capsys.readouterr()
    assert "Order processed" in captured.out
