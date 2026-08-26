"""HTTP schemas shared by mail adapters and the future webmail UI."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, EmailStr, Field, model_validator


class MailFlag(StrEnum):
    SEEN = "seen"
    ANSWERED = "answered"
    FLAGGED = "flagged"
    DELETED = "deleted"
    DRAFT = "draft"


class MailFolder(BaseModel):
    name: str
    delimiter: str = "/"
    flags: list[str] = Field(default_factory=list)


class MailAddress(BaseModel):
    name: str | None = None
    address: EmailStr


class MailAttachment(BaseModel):
    part_id: str
    filename: str
    content_type: str
    size: int
    inline: bool = False
    content_id: str | None = None


class MailMessageSummary(BaseModel):
    uid: int
    message_id: str | None = None
    subject: str = ""
    sender: MailAddress | None = None
    recipients: list[MailAddress] = Field(default_factory=list)
    sent_at: datetime | None = None
    flags: list[MailFlag] = Field(default_factory=list)
    size: int = 0
    has_attachments: bool = False


class MailMessage(MailMessageSummary):
    cc: list[MailAddress] = Field(default_factory=list)
    reply_to: list[MailAddress] = Field(default_factory=list)
    text_body: str | None = None
    html_body: str | None = None
    attachments: list[MailAttachment] = Field(default_factory=list)


class MailMessagePage(BaseModel):
    messages: list[MailMessageSummary]
    total: int
    offset: int
    limit: int


class SendMailRequest(BaseModel):
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
    destination: str = Field(min_length=1, max_length=255)


class UpdateFlagsRequest(BaseModel):
    add: list[MailFlag] = Field(default_factory=list)
    remove: list[MailFlag] = Field(default_factory=list)


class SendMailResponse(BaseModel):
    message_id: str


class MailStatus(BaseModel):
    configured: bool
    provider: str
