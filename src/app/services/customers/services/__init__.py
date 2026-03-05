"""
Customers Services Package
"""

from .customers_db_service import (
    AddressRepository,
    CustomerRepository,
    get_address_repository,
    get_customer_repository,
)

__all__ = [
    "CustomerRepository",
    "AddressRepository",
    "get_customer_repository",
    "get_address_repository",
]
