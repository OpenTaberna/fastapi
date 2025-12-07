"""
Success Response Models

Type-safe response models for successful API operations.
Uses TypeVar for generic type safety.
"""

from typing import Generic, Optional, TypeVar
from pydantic import Field, ConfigDict
from .base import BaseResponse

# Generic type variable for type-safe responses
T = TypeVar("T")


class SuccessResponse(BaseResponse, Generic[T]):
    """
    Generic success response with optional data.

    Use this when you want to return data with the response.
    The data field is type-safe using generics.

    Examples:
        >>> SuccessResponse[User](success=True, data=user)
        >>> SuccessResponse[List[Item]](success=True, data=items)
    """

    success: bool = Field(
        default=True, description="Always True for successful responses"
    )

    data: Optional[T] = Field(None, description="Response data of generic type T")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "message": "User retrieved successfully",
                "data": {"id": 1, "name": "John Doe", "email": "john@example.com"},
                "timestamp": "2025-12-07T12:00:00Z",
            }
        }
    )


class MessageResponse(BaseResponse):
    """
    Simple success response with only a message.

    Use this when you don't need to return data,
    just confirm that an operation succeeded.

    Examples:
        >>> MessageResponse(success=True, message="Item deleted")
        >>> MessageResponse(success=True, message="Email sent")
    """

    success: bool = Field(
        default=True, description="Always True for successful responses"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "message": "Operation completed successfully",
                "timestamp": "2025-12-07T12:00:00Z",
            }
        }
    )


class DataResponse(SuccessResponse[T], Generic[T]):
    """
    Success response that requires data.

    Similar to SuccessResponse but data is required, not optional.
    Use this when data should always be present.

    Examples:
        >>> DataResponse[User](data=user, message="User found")
    """

    data: T = Field(..., description="Required response data of generic type T")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "message": "Data retrieved successfully",
                "data": {"id": 1, "value": "example"},
                "timestamp": "2025-12-07T12:00:00Z",
            }
        }
    )
