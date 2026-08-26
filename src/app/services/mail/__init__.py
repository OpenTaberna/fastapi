"""Provider-neutral admin mailbox API."""

from fastapi import APIRouter

from .routers.mail_router import router

mail_api_router = APIRouter(prefix="/admin/mail", tags=["Admin Mail"])
mail_api_router.include_router(router)

__all__ = ["mail_api_router"]
