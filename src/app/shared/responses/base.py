"""
Base Response Model

Provides common fields and structure for all API responses.
Following SOLID principles with shared behavior in base class.
"""

from datetime import datetime, UTC
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field, ConfigDict


class BaseResponse(BaseModel):
    """
    Base class for all API responses.

    Provides common fields that every response should have:
    - success: Indicates if the request was successful
    - message: Human-readable message
    - timestamp: When the response was generated
    - request_id: Optional request ID for tracing
    - metadata: Optional additional metadata
    """

    success: Optional[bool] = Field(
        None, description="Indicates whether the request was successful"
    )

    message: Optional[str] = Field(
        None, description="Human-readable message about the response"
    )

    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp when the response was generated (UTC)",
    )

    request_id: Optional[str] = Field(
        None, description="Unique request ID for tracing and debugging"
    )

    metadata: Optional[Dict[str, Any]] = Field(
        None, description="Optional additional metadata"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "message": "Operation completed successfully",
                "timestamp": "2025-12-07T12:00:00Z",
                "request_id": "req_abc123",
                "metadata": {"version": "1.0.0"},
            }
        }
    )
