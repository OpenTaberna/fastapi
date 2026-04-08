"""
Returns OpenAPI Response Documentation — Phase 4.4

Shared response dictionaries for the returns router.
"""

CREATE_RETURN_RESPONSES: dict = {
    201: {"description": "Return request created"},
    400: {
        "description": "Return already exists for this order, or order not in a returnable status"
    },
    404: {"description": "Order not found"},
    422: {"description": "Validation error"},
}

GET_RETURN_RESPONSES: dict = {
    200: {"description": "Return request details"},
    404: {"description": "Return not found"},
}

ADMIN_UPDATE_RETURN_RESPONSES: dict = {
    200: {"description": "Return updated"},
    400: {"description": "Invalid status transition"},
    404: {"description": "Return not found"},
    422: {"description": "Validation error"},
}
