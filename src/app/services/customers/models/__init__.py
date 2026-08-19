"""
Customers Models Package

Exports ORM models and API data structures for the customers service.
"""

from .customers_db_models import AddressDB, CustomerDB
from .customers_models import (
    AddressBase,
    AddressCreate,
    AddressResponse,
    AddressUpdate,
    CustomerBase,
    CustomerCreate,
    CustomerCreationHeaders,
    CustomerResponse,
    CustomerUpdate,
)

__all__ = [
    # ORM models
    "CustomerDB",
    "AddressDB",
    # Pydantic schemas
    "CustomerBase",
    "CustomerCreate",
    "CustomerCreationHeaders",
    "CustomerUpdate",
    "CustomerResponse",
    "AddressBase",
    "AddressCreate",
    "AddressUpdate",
    "AddressResponse",
]
