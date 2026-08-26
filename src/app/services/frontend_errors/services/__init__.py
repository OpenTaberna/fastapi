"""Frontend error services."""

from .frontend_errors_db_service import (
    MAX_CLOCK_SKEW,
    FrontendErrorRepository,
    get_frontend_error_repository,
)

__all__ = [
    "MAX_CLOCK_SKEW",
    "FrontendErrorRepository",
    "get_frontend_error_repository",
]
