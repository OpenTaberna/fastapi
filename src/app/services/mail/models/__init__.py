"""Public API schemas for the mail service."""

from .mail_models import (
    CreateFolderRequest,
    MailAddress,
    MailAttachment,
    MailFlag,
    MailFolder,
    MailMessage,
    MailMessagePage,
    MailMessageSummary,
    MailStatus,
    MoveMailRequest,
    RenameFolderRequest,
    SendMailRequest,
    SendMailResponse,
    UpdateFlagsRequest,
)

__all__ = [
    "CreateFolderRequest",
    "MailAddress",
    "MailAttachment",
    "MailFlag",
    "MailFolder",
    "MailMessage",
    "MailMessagePage",
    "MailMessageSummary",
    "MailStatus",
    "MoveMailRequest",
    "RenameFolderRequest",
    "SendMailRequest",
    "SendMailResponse",
    "UpdateFlagsRequest",
]
