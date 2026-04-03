"""
Orders Service Package

Handles order lifecycle from DRAFT to SHIPPED.
"""

from .orders import orders_api_router, webhooks_api_router

__all__ = ["orders_api_router", "webhooks_api_router"]
