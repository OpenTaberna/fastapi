"""
Payment Service — FastAPI Dependencies

Provides get_payment_adapter() for use with FastAPI Depends.
Swap the body of this function to change PSP without touching any router.
"""

from typing import Annotated

from fastapi import Depends

from app.shared.config import get_settings
from app.shared.config.loader import load_secret
from app.shared.config.settings import Settings

from .adapters import PaymentMethod, PaymentProviderAdapter, build_stripe_adapter


async def get_payment_adapter(
    settings: Annotated[Settings, Depends(get_settings)],
) -> PaymentProviderAdapter:
    """
    FastAPI dependency that builds and returns a PaymentProviderAdapter.

    Currently wires up StripeAdapter from application settings.
    To switch PSP, replace the body here — all routers stay untouched.

    Args:
        settings: Application settings (injected by FastAPI).

    Returns:
        Configured PaymentProviderAdapter instance.
    """
    # The development Stripe CLI sidecar can refresh this mounted secret when
    # it reconnects. Read it for each dependency instance instead of retaining
    # the value cached when Settings was first constructed.
    webhook_secret = (
        load_secret("stripe_webhook_secret") or settings.stripe_webhook_secret
    )

    return build_stripe_adapter(
        secret_key=settings.stripe_secret_key,
        webhook_secret=webhook_secret,
        payment_methods=[PaymentMethod(m) for m in settings.stripe_payment_methods],
        bank_transfer_country=settings.stripe_bank_transfer_country,
    )
