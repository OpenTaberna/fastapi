"""Admin-only REST facade for Paperless-backed accounting documents."""

from typing import Any, Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile, status

from app.services.admin.dependencies import require_admin
from app.shared.responses import DataResponse

from ..dependencies import AccountingOperationsDependency
from ..models import (
    AccountingStatus,
    BulkEditRequest,
    DocumentUpdate,
    PaperlessDocument,
    PaperlessPage,
    PaperlessResource,
    ResourceWrite,
    UploadResult,
)

router = APIRouter(dependencies=[Depends(require_admin)])
ResourceName = Literal[
    "tags", "correspondents", "document-types", "storage-paths", "custom-fields"
]


@router.get("/status", response_model=DataResponse[AccountingStatus])
async def accounting_status(
    operations: AccountingOperationsDependency, probe: bool = False
) -> DataResponse[AccountingStatus]:
    return DataResponse(
        data=await operations.status(probe), message="Accounting status retrieved"
    )


@router.get("/documents", response_model=DataResponse[PaperlessPage])
async def list_documents(
    operations: AccountingOperationsDependency,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    query: str | None = Query(None, max_length=500),
    correspondent: int | None = Query(None, ge=1),
    document_type: int | None = Query(None, ge=1),
    storage_path: int | None = Query(None, ge=1),
    tags: list[int] | None = Query(None),
    ordering: str | None = Query(None, max_length=100),
) -> DataResponse[PaperlessPage]:
    params = {
        "page": page,
        "page_size": page_size,
        "text": query,
        "correspondent__id": correspondent,
        "document_type__id": document_type,
        "storage_path__id": storage_path,
        "tags__id__all": ",".join(map(str, tags)) if tags else None,
        "ordering": ordering,
    }
    data = await operations.list_documents(
        {k: v for k, v in params.items() if v is not None}
    )
    return DataResponse(
        data=PaperlessPage.model_validate(data), message="Documents retrieved"
    )


@router.post("/documents", response_model=DataResponse[UploadResult], status_code=202)
async def upload_document(
    operations: AccountingOperationsDependency,
    document: UploadFile = File(...),
    title: str | None = Form(None),
    created: str | None = Form(None),
    correspondent: int | None = Form(None),
    document_type: int | None = Form(None),
    storage_path: int | None = Form(None),
    tags: list[int] | None = Form(None),
    archive_serial_number: int | None = Form(None),
) -> DataResponse[UploadResult]:
    # Read one byte beyond the limit so oversized files are rejected without
    # loading an arbitrarily large request into application memory.
    content = await document.read(operations.max_upload_bytes + 1)
    task_id = await operations.upload(
        document.filename or "document",
        document.content_type or "application/octet-stream",
        content,
        {
            "title": title,
            "created": created,
            "correspondent": correspondent,
            "document_type": document_type,
            "storage_path": storage_path,
            "tags": tags,
            "archive_serial_number": archive_serial_number,
        },
    )
    return DataResponse(data=UploadResult(task_id=task_id), message="Document queued")


@router.post("/documents/bulk-edit", response_model=DataResponse[Any], status_code=202)
async def bulk_edit_documents(
    payload: BulkEditRequest, operations: AccountingOperationsDependency
) -> DataResponse[Any]:
    return DataResponse(
        data=await operations.bulk_edit(payload), message="Bulk edit queued"
    )


@router.get("/documents/{document_id}", response_model=DataResponse[PaperlessDocument])
async def get_document(
    document_id: int, operations: AccountingOperationsDependency
) -> DataResponse[PaperlessDocument]:
    data = await operations.get_document(document_id)
    return DataResponse(
        data=PaperlessDocument.model_validate(data), message="Document retrieved"
    )


@router.patch(
    "/documents/{document_id}", response_model=DataResponse[PaperlessDocument]
)
async def update_document(
    document_id: int,
    payload: DocumentUpdate,
    operations: AccountingOperationsDependency,
) -> DataResponse[PaperlessDocument]:
    data = await operations.update_document(document_id, payload)
    return DataResponse(
        data=PaperlessDocument.model_validate(data), message="Document updated"
    )


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: int, operations: AccountingOperationsDependency
) -> None:
    await operations.delete_document(document_id)


@router.get("/documents/{document_id}/file")
async def download_document(
    document_id: int,
    operations: AccountingOperationsDependency,
    variant: Literal["original", "preview", "thumbnail"] = "original",
) -> Response:
    downloaded = await operations.download(document_id, variant)
    headers = {}
    if downloaded.filename:
        headers["Content-Disposition"] = (
            f"attachment; filename*=UTF-8''{quote(downloaded.filename)}"
        )
    return Response(
        downloaded.content, media_type=downloaded.content_type, headers=headers
    )


@router.get("/tasks", response_model=DataResponse[PaperlessPage])
async def list_tasks(
    operations: AccountingOperationsDependency,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    task_id: str | None = Query(None, max_length=100),
) -> DataResponse[PaperlessPage]:
    params = {"page": page, "page_size": page_size, "task_id": task_id}
    data = await operations.list_tasks(
        {k: v for k, v in params.items() if v is not None}
    )
    return DataResponse(
        data=PaperlessPage.model_validate(data), message="Tasks retrieved"
    )


@router.get("/resources/{resource}", response_model=DataResponse[PaperlessPage])
async def list_resources(
    resource: ResourceName,
    operations: AccountingOperationsDependency,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=200),
    query: str | None = Query(None, max_length=256),
) -> DataResponse[PaperlessPage]:
    params = {"page": page, "page_size": page_size, "name__icontains": query}
    data = await operations.list_resources(
        resource, {k: v for k, v in params.items() if v is not None}
    )
    return DataResponse(
        data=PaperlessPage.model_validate(data), message="Resources retrieved"
    )


@router.post(
    "/resources/{resource}",
    response_model=DataResponse[PaperlessResource],
    status_code=201,
)
async def create_resource(
    resource: ResourceName,
    payload: ResourceWrite,
    operations: AccountingOperationsDependency,
) -> DataResponse[PaperlessResource]:
    data = await operations.create_resource(resource, payload)
    return DataResponse(
        data=PaperlessResource.model_validate(data), message="Resource created"
    )


@router.patch(
    "/resources/{resource}/{resource_id}",
    response_model=DataResponse[PaperlessResource],
)
async def update_resource(
    resource: ResourceName,
    resource_id: int,
    payload: ResourceWrite,
    operations: AccountingOperationsDependency,
) -> DataResponse[PaperlessResource]:
    data = await operations.update_resource(resource, resource_id, payload)
    return DataResponse(
        data=PaperlessResource.model_validate(data), message="Resource updated"
    )


@router.delete(
    "/resources/{resource}/{resource_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_resource(
    resource: ResourceName, resource_id: int, operations: AccountingOperationsDependency
) -> None:
    await operations.delete_resource(resource, resource_id)
