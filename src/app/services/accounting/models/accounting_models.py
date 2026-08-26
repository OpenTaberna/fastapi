"""Stable admin-facing schemas for accounting documents and classifications."""

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PaperlessResource(BaseModel):
    """A Paperless classification object, retaining provider extension fields."""

    model_config = ConfigDict(extra="allow")

    id: int
    name: str


class PaperlessDocument(BaseModel):
    """Document fields used by the admin UI, with forward-compatible extras."""

    model_config = ConfigDict(extra="allow")

    id: int
    title: str
    content: str | None = None
    created: date | None = None
    added: datetime | None = None
    modified: datetime | None = None
    correspondent: int | None = None
    document_type: int | None = None
    storage_path: int | None = None
    tags: list[int] = Field(default_factory=list)
    archive_serial_number: int | None = None
    original_file_name: str | None = None
    archived_file_name: str | None = None


class PaperlessPage(BaseModel):
    """Paperless-compatible cursor/page response."""

    model_config = ConfigDict(extra="allow")

    count: int
    next: str | None = None
    previous: str | None = None
    results: list[dict[str, Any]]


class AccountingStatus(BaseModel):
    configured: bool
    provider: str = "paperless_ngx"
    reachable: bool | None = None
    version: str | None = None


class DocumentUpdate(BaseModel):
    """Editable root-document metadata."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=512)
    content: str | None = None
    created: date | None = None
    correspondent: int | None = Field(default=None, ge=1)
    document_type: int | None = Field(default=None, ge=1)
    storage_path: int | None = Field(default=None, ge=1)
    tags: list[int] | None = None
    archive_serial_number: int | None = Field(default=None, ge=1)
    custom_fields: list[dict[str, Any]] | None = None


class ResourceWrite(BaseModel):
    """Create/update payload common to Paperless classifiers."""

    model_config = ConfigDict(extra="allow")

    name: str = Field(min_length=1, max_length=256)


class BulkEditRequest(BaseModel):
    documents: list[int] = Field(min_length=1)
    method: str = Field(min_length=1, max_length=64)
    parameters: dict[str, Any] = Field(default_factory=dict)


class UploadResult(BaseModel):
    task_id: str
