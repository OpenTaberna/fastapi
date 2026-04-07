"""
Customers Service Package

Handles customer profiles and addresses.
"""

from fastapi import APIRouter

from .routers import customers_router

customers_api_router = APIRouter(
    prefix="/customers",
    tags=["Customers"],
)
customers_api_router.include_router(customers_router)

__all__ = ["customers_api_router"]
