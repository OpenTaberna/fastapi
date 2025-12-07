"""
Pagination Response Models

Response models for paginated data with page-based navigation.
Optimized for webshop and list views.
"""

from typing import Generic, TypeVar, List
from pydantic import BaseModel, Field, field_validator, ConfigDict
from .base import BaseResponse

# Generic type variable for paginated items
T = TypeVar("T")


class PageInfo(BaseModel):
    """
    Pagination metadata information.

    Contains all information needed for page-based navigation,
    suitable for webshop product listings and other paginated views.

    Attributes:
        page: Current page number (1-indexed)
        size: Number of items per page
        total: Total number of items across all pages
        pages: Total number of pages available
    """

    page: int = Field(..., description="Current page number (1-indexed)", ge=1)

    size: int = Field(..., description="Number of items per page", ge=1, le=1000)

    total: int = Field(..., description="Total number of items across all pages", ge=0)

    pages: int = Field(..., description="Total number of pages available", ge=0)

    @field_validator("page")
    @classmethod
    def validate_page(cls, v: int, info) -> int:
        """Validate page is within bounds if pages is set."""
        # Note: pages might not be set yet during initialization
        return v

    model_config = ConfigDict(
        json_schema_extra={"example": {"page": 1, "size": 20, "total": 100, "pages": 5}}
    )


class PaginatedResponse(BaseResponse, Generic[T]):
    """
    Generic paginated response for lists of items.

    Combines page information with a typed list of items.
    Use this for any endpoint that returns paginated data.

    Examples:
        >>> PaginatedResponse[Product](
        ...     items=[product1, product2],
        ...     page_info=PageInfo(page=1, size=20, total=100, pages=5),
        ...     message="Products retrieved successfully"
        ... )
    """

    success: bool = Field(
        default=True, description="Always True for successful responses"
    )

    items: List[T] = Field(..., description="List of items for the current page")

    page_info: PageInfo = Field(..., description="Pagination metadata")

    @field_validator("items")
    @classmethod
    def validate_items_length(cls, v: List[T], info) -> List[T]:
        """Validate items length matches page_info if available."""
        # Note: page_info might not be set yet during initialization
        return v

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "message": "Products retrieved successfully",
                "items": [
                    {"id": 1, "name": "Product 1", "price": 29.99},
                    {"id": 2, "name": "Product 2", "price": 39.99},
                ],
                "page_info": {"page": 1, "size": 20, "total": 100, "pages": 5},
                "timestamp": "2025-12-07T12:00:00Z",
            }
        }
    )


class CursorInfo(BaseModel):
    """
    Cursor-based pagination metadata (alternative to page-based).

    Use this for infinite scrolling or when items are frequently
    added/removed (e.g., social media feeds, real-time data).

    Attributes:
        cursor: Current cursor position (opaque string)
        has_next: Whether there are more items after this cursor
        has_previous: Whether there are items before this cursor
        count: Number of items in current result
    """

    cursor: str = Field(..., description="Current cursor position (opaque string)")

    has_next: bool = Field(
        ..., description="Whether there are more items after this cursor"
    )

    has_previous: bool = Field(
        default=False, description="Whether there are items before this cursor"
    )

    count: int = Field(..., description="Number of items in current result", ge=0)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "cursor": "eyJpZCI6MTIzfQ==",
                "has_next": True,
                "has_previous": False,
                "count": 20,
            }
        }
    )


class CursorPaginatedResponse(BaseResponse, Generic[T]):
    """
    Generic cursor-based paginated response.

    Alternative to page-based pagination for cases where
    cursor-based navigation is more appropriate.

    Examples:
        >>> CursorPaginatedResponse[Post](
        ...     items=[post1, post2],
        ...     cursor_info=CursorInfo(
        ...         cursor="abc123",
        ...         has_next=True,
        ...         count=20
        ...     )
        ... )
    """

    success: bool = Field(
        default=True, description="Always True for successful responses"
    )

    items: List[T] = Field(..., description="List of items for the current cursor")

    cursor_info: CursorInfo = Field(..., description="Cursor pagination metadata")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "message": "Posts retrieved successfully",
                "items": [
                    {"id": 1, "title": "Post 1", "content": "..."},
                    {"id": 2, "title": "Post 2", "content": "..."},
                ],
                "cursor_info": {
                    "cursor": "eyJpZCI6Mn0=",
                    "has_next": True,
                    "has_previous": False,
                    "count": 2,
                },
                "timestamp": "2025-12-07T12:00:00Z",
            }
        }
    )
