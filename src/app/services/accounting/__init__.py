"""Provider-neutral admin accounting document API."""

from fastapi import APIRouter

from .routers.accounting_router import router

accounting_api_router = APIRouter(prefix="/admin/accounting", tags=["Admin Accounting"])
accounting_api_router.include_router(router)

__all__ = ["accounting_api_router"]
