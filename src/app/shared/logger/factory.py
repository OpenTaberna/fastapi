"""
Factory functions for creating logger instances.

Provides convenient access to logger creation and management.
"""

import os
from pathlib import Path
from typing import Dict, Optional

from app.shared.config.enums import Environment

from .config import LoggerConfig
from .logger import AppLogger


# Global cache for logger instances
_loggers: Dict[str, AppLogger] = {}


def get_logger(
    name: str,
    config: Optional[LoggerConfig] = None,
    environment: Optional[Environment] = None,
    log_dir: Optional[Path] = None,
) -> AppLogger:
    """
    Get or create a logger instance.

    Args:
        name: Logger name (typically __name__)
        config: Optional custom configuration
        environment: Environment type (auto-detected if not provided)
        log_dir: Directory for log files

    Returns:
        Configured AppLogger instance

    Example:
        logger = get_logger(__name__)
        logger.info("Application started")
    """
    if name in _loggers:
        return _loggers[name]

    if config is None:
        # Auto-detect environment from environment variable
        env_str = os.getenv("ENVIRONMENT", "development").lower()
        try:
            env = Environment(env_str)
        except ValueError:
            env = Environment.DEVELOPMENT

        if environment:
            env = environment

        config = LoggerConfig.from_environment(name, env, log_dir)

    logger = AppLogger(config)
    _loggers[name] = logger
    return logger


def clear_loggers():
    """Clear all cached logger instances. Useful for testing."""
    global _loggers
    _loggers.clear()
