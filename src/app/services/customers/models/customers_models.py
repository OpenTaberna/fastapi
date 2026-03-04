"""
Customers Pydantic Schemas

API-level input/output validation for the customers service.
Completely independent of SQLAlchemy — only used in routers and functions.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ============================================================================
# Customer Schemas
# ============================================================================


class CustomerBase(BaseModel):
    """Shared customer fields used in create and response schemas."""

    keycloak_user_id: str = Field(
        ...,
        description="Keycloak subject claim (sub) from JWT",
    )
    email: EmailStr = Field(..., description="Customer email address")
    first_name: str = Field(..., min_length=1, max_length=100, description="Given name")
    last_name: str = Field(..., min_length=1, max_length=100, description="Family name")


class CustomerCreate(CustomerBase):
    """Schema for creating a new customer record. Used internally on first login."""

    pass


class CustomerUpdate(BaseModel):
    """Schema for partial customer updates. All fields optional."""

    email: EmailStr | None = None
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)


class CustomerResponse(CustomerBase):
    """Customer response schema returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Internal customer UUID")
    created_at: datetime = Field(..., description="Record creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")


# ============================================================================
# Address Schemas
# ============================================================================


class AddressBase(BaseModel):
    """Shared address fields."""

    street: str = Field(
        ..., min_length=1, max_length=255, description="Street and house number"
    )
    city: str = Field(..., min_length=1, max_length=100, description="City name")
    zip_code: str = Field(
        ..., min_length=1, max_length=20, description="Postal / ZIP code"
    )
    country: str = Field(
        ...,
        min_length=2,
        max_length=2,
        description="ISO 3166-1 alpha-2 country code (e.g. 'DE')",
    )
    is_default: bool = Field(
        default=False, description="Whether this is the default shipping address"
    )


class AddressCreate(AddressBase):
    """Schema for creating a new address. customer_id is injected from the auth token."""

    pass


class AddressUpdate(BaseModel):
    """Schema for partial address updates. All fields optional."""

    street: str | None = Field(default=None, min_length=1, max_length=255)
    city: str | None = Field(default=None, min_length=1, max_length=100)
    zip_code: str | None = Field(default=None, min_length=1, max_length=20)
    country: str | None = Field(default=None, min_length=2, max_length=2)
    is_default: bool | None = None


class AddressResponse(AddressBase):
    """Address response schema returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Internal address UUID")
    customer_id: UUID = Field(..., description="UUID of the owning customer")
    created_at: datetime = Field(..., description="Record creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
