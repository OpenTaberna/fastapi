"""Composition root for mail use-case dependencies."""

from typing import Annotated

from fastapi import Depends

from app.shared.config import get_settings

from .adapters import ImapSmtpMailAdapter
from .functions import MailOperations


def get_mail_operations() -> MailOperations:
    """Build mail operations with the configured provider adapter."""
    settings = get_settings()
    return MailOperations(ImapSmtpMailAdapter(settings), settings)


MailOperationsDependency = Annotated[MailOperations, Depends(get_mail_operations)]

__all__ = ["MailOperationsDependency", "get_mail_operations"]
