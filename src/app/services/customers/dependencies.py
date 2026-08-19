"""FastAPI dependencies for the customers service."""

from fastapi import Header

from .models import CustomerCreationHeaders


async def get_creation_headers(
    x_customer_email: str | None = Header(
        default=None,
        alias="X-Customer-Email",
        description="[Dev-only] Required only on first call (profile creation). Customer email address.",
    ),
    x_customer_first_name: str | None = Header(
        default=None,
        alias="X-Customer-First-Name",
        description="[Dev-only] Required only on first call (profile creation). Customer given name.",
    ),
    x_customer_last_name: str | None = Header(
        default=None,
        alias="X-Customer-Last-Name",
        description="[Dev-only] Required only on first call (profile creation). Customer family name.",
    ),
) -> CustomerCreationHeaders:
    """Collect the optional identity headers used for first-login creation."""
    return CustomerCreationHeaders(
        email=x_customer_email,
        first_name=x_customer_first_name,
        last_name=x_customer_last_name,
    )
