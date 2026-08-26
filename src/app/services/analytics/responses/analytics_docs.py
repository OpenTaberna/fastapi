"""
OpenAPI Documentation for Analytics Endpoints

Error examples are built from real ErrorResponse instances so they cannot drift
from what the API actually returns — the same approach used in
services/admin/responses/admin_docs.py.
"""

from app.shared.responses import ErrorResponse

_FORBIDDEN = ErrorResponse(
    status_code=403,
    error_code="access_denied",
    error_category="authorization",
    message="Admin access required.",
    details={"resource": "analytics", "action": "read"},
).model_dump(mode="json", exclude_none=True)

_BAD_PERIOD = ErrorResponse(
    status_code=422,
    error_code="invalid_input",
    error_category="validation",
    message="The start of the period is after its end",
    details={"from": "2026-08-31", "to": "2026-08-01"},
).model_dump(mode="json", exclude_none=True)


_COMMON: dict[int | str, dict] = {
    403: {
        "description": "Caller is not an administrator, or the token came from a "
        "client that may not reach admin endpoints.",
        "content": {"application/json": {"example": _FORBIDDEN}},
    },
    422: {
        "description": "The requested period is invalid or too long.",
        "content": {"application/json": {"example": _BAD_PERIOD}},
    },
}

SUMMARY_RESPONSES = dict(_COMMON)
TIMESERIES_RESPONSES = dict(_COMMON)
PRODUCTS_RESPONSES = dict(_COMMON)
FUNNEL_RESPONSES = dict(_COMMON)

__all__ = [
    "FUNNEL_RESPONSES",
    "PRODUCTS_RESPONSES",
    "SUMMARY_RESPONSES",
    "TIMESERIES_RESPONSES",
]
