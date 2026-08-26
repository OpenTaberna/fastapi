"""Composition root for accounting dependencies."""

from typing import Annotated

from fastapi import Depends

from app.shared.config import get_settings

from .adapters import PaperlessAccountingAdapter
from .functions import AccountingOperations


def get_accounting_operations() -> AccountingOperations:
    settings = get_settings()
    return AccountingOperations(PaperlessAccountingAdapter(settings), settings)


AccountingOperationsDependency = Annotated[
    AccountingOperations, Depends(get_accounting_operations)
]

__all__ = ["AccountingOperationsDependency", "get_accounting_operations"]
