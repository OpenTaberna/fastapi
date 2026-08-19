"""
Authorization Package

Keycloak-backed authentication and the dependencies routes use to enforce it.
"""

from .dependencies import (
    get_keycloak_id,
    get_optional_principal,
    oauth2_scheme,
    require_admin,
    require_principal,
)
from .token import (
    Principal,
    TokenError,
    authenticate,
    decode_token,
    issuer_url,
    jwks_url,
    principal_from_claims,
    reset_key_cache,
)

__all__ = [
    "Principal",
    "TokenError",
    "authenticate",
    "oauth2_scheme",
    "decode_token",
    "get_keycloak_id",
    "get_optional_principal",
    "issuer_url",
    "jwks_url",
    "principal_from_claims",
    "require_admin",
    "require_principal",
    "reset_key_cache",
]
