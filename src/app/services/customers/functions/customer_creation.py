"""Business logic for creating customer profiles."""

from app.shared.exceptions import missing_field

from ..models import CustomerCreate, CustomerCreationHeaders


def build_customer_create(
    keycloak_user_id: str,
    headers: CustomerCreationHeaders,
) -> CustomerCreate:
    """Build validated customer data from the first-login identity headers."""
    if not headers.email:
        raise missing_field("X-Customer-Email")
    if not headers.first_name:
        raise missing_field("X-Customer-First-Name")
    if not headers.last_name:
        raise missing_field("X-Customer-Last-Name")

    return CustomerCreate(
        keycloak_user_id=keycloak_user_id,
        email=headers.email,
        first_name=headers.first_name,
        last_name=headers.last_name,
    )
