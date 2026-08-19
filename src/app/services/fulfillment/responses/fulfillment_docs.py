"""
OpenAPI response documentation for the fulfillment label endpoints.
"""

from app.shared.responses import ErrorResponse

TRIGGER_LABEL_RESPONSES: dict = {
    202: {"description": "Label job accepted and enqueued"},
    400: {
        "description": "Order has no shipment, or carrier does not support labels",
        "model": ErrorResponse,
    },
    404: {"description": "Order not found", "model": ErrorResponse},
    403: {"description": "Admin role required", "model": ErrorResponse},
}

DOWNLOAD_LABEL_RESPONSES: dict = {
    200: {"description": "Label file bytes (PDF or ZPL)"},
    404: {"description": "Order or label not found", "model": ErrorResponse},
    403: {"description": "Admin role required", "model": ErrorResponse},
    502: {"description": "Storage download failed", "model": ErrorResponse},
}
