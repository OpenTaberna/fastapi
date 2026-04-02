"""
Customers Models Package

Exports ORM models and Pydantic schemas for the customers service.
"""

from .customers_db_models import AddressDB, CustomerDB
from .customers_models import (
    AddressBase,
    AddressCreate,
    AddressResponse,
    AddressUpdate,
    CustomerBase,
    CustomerCreate,
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
    "CustomerUpdate",
    "CustomerResponse",
    "AddressBase",
    "AddressCreate",
    "AddressUpdate",
    "AddressResponse",
]
