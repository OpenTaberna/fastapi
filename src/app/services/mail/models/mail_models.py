"""HTTP schemas shared by mail adapters and the future webmail UI."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator


class MailFlag(StrEnum):
    """Provider-neutral message flags exposed by the HTTP API."""

    SEEN = "seen"
    ANSWERED = "answered"
    FLAGGED = "flagged"
    DELETED = "deleted"
    DRAFT = "draft"


class MailFolder(BaseModel):
    """A mailbox folder returned by the configured provider."""

    name: str = Field(..., min_length=1, description="Provider folder name")
    delimiter: str = Field(default="/", description="Folder hierarchy delimiter")
    flags: list[str] = Field(
        default_factory=list, description="Provider capabilities and folder flags"
    )


class CreateFolderRequest(BaseModel):
    """Request to create a mailbox folder."""

    name: str = Field(..., min_length=1, max_length=255, description="New folder name")

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        """Trim folder names and reject protocol control characters."""
        value = value.strip()
        if not value:
            raise ValueError("folder name must not be blank")
        if any(character in value for character in ("\x00", "\r", "\n")):
            raise ValueError("folder name contains invalid control characters")
        return value


class RenameFolderRequest(BaseModel):
    """Request to rename an existing mailbox folder."""

    name: str = Field(..., min_length=1, max_length=255, description="New folder name")

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        """Apply the same provider-safe validation as folder creation."""
        return CreateFolderRequest(name=value).name


class MailAddress(BaseModel):
    """A validated email address with an optional display name."""

    name: str | None = Field(default=None, description="Display name")
    address: EmailStr = Field(..., description="RFC-compatible email address")


class MailAttachment(BaseModel):
    """Attachment metadata; content is downloaded from a separate endpoint."""

    part_id: str = Field(..., min_length=1, description="Provider MIME part identifier")
    filename: str = Field(..., min_length=1, description="Original filename")
    content_type: str = Field(..., min_length=1, description="MIME content type")
    size: int = Field(..., ge=0, description="Decoded attachment size in bytes")
    inline: bool = Field(default=False, description="Whether the part is inline")
    content_id: str | None = Field(default=None, description="MIME Content-ID")


class MailMessageSummary(BaseModel):
    """Message metadata used by mailbox list views."""

    uid: int = Field(..., ge=1, description="Folder-scoped IMAP UID")
    message_id: str | None = Field(default=None, description="RFC Message-ID")
    subject: str = Field(default="", description="Decoded subject")
    sender: MailAddress | None = Field(default=None, description="Sender")
    recipients: list[MailAddress] = Field(
        default_factory=list, description="To recipients"
    )
    sent_at: datetime | None = Field(default=None, description="Date header timestamp")
    flags: list[MailFlag] = Field(default_factory=list, description="Normalized flags")
    size: int = Field(default=0, ge=0, description="Message size in bytes")
    has_attachments: bool = Field(default=False, description="Attachment indicator")


class MailMessage(MailMessageSummary):
    """Complete message content returned by the detail endpoint."""

    cc: list[MailAddress] = Field(default_factory=list)
    reply_to: list[MailAddress] = Field(default_factory=list)
    text_body: str | None = None
    html_body: str | None = None
    attachments: list[MailAttachment] = Field(default_factory=list)


class MailMessagePage(BaseModel):
    """Offset-based message page suitable for IMAP UID result sets."""

    messages: list[MailMessageSummary] = Field(description="Messages in this page")
    total: int = Field(..., ge=0, description="Total matching messages")
    offset: int = Field(..., ge=0, description="Applied result offset")
    limit: int = Field(..., ge=1, le=200, description="Applied page limit")


class SendMailRequest(BaseModel):
    """Validated message composition request."""

    to: list[EmailStr] = Field(min_length=1)
    cc: list[EmailStr] = Field(default_factory=list)
    bcc: list[EmailStr] = Field(default_factory=list)
    subject: str = Field(default="", max_length=998)
    text_body: str | None = None
    html_body: str | None = None
    reply_to: EmailStr | None = None
    in_reply_to: str | None = None

    @model_validator(mode="after")
    def require_body(self):
        if not self.html_body and not self.text_body:
            raise ValueError("text_body or html_body is required")
        return self


class MoveMailRequest(BaseModel):
    """Request to move a message into another existing folder."""

    destination: str = Field(min_length=1, max_length=255)


class UpdateFlagsRequest(BaseModel):
    """Flags to add to or remove from a message."""

    add: list[MailFlag] = Field(default_factory=list)
    remove: list[MailFlag] = Field(default_factory=list)


class SendMailResponse(BaseModel):
    """Identity assigned to a successfully submitted outgoing message."""

    message_id: str = Field(..., min_length=1, description="Generated RFC Message-ID")


class MailStatus(BaseModel):
    """Non-sensitive mailbox adapter configuration status."""

    configured: bool = Field(description="Whether required mailbox settings exist")
    provider: str = Field(..., min_length=1, description="Configured adapter name")
