"""Admin-only REST facade used by a future webmail frontend."""

from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Response, status

from app.services.admin.dependencies import require_admin
from ..models.mail_models import (
    MailFolder,
    MailMessage,
    MailMessagePage,
    MailStatus,
    MoveMailRequest,
    SendMailRequest,
    SendMailResponse,
    UpdateFlagsRequest,
)
from ..services import MailService, get_mail_service

router = APIRouter(dependencies=[Depends(require_admin)])
Service = Annotated[MailService, Depends(get_mail_service)]


@router.get(
    "/status", response_model=MailStatus, summary="Get mailbox configuration status"
)
async def mailbox_status(service: Service) -> MailStatus:
    return service.status()


@router.get("/folders", response_model=list[MailFolder], summary="List mail folders")
async def list_folders(service: Service) -> list[MailFolder]:
    return await service.list_folders()


@router.get(
    "/folders/{folder:path}/messages",
    response_model=MailMessagePage,
    summary="List messages",
)
async def list_messages(
    folder: str,
    service: Service,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    query: str | None = Query(None, max_length=200),
) -> MailMessagePage:
    return await service.list_messages(folder, offset, limit, query)


@router.get(
    "/folders/{folder:path}/messages/{uid}",
    response_model=MailMessage,
    summary="Read a message",
)
async def get_message(folder: str, uid: int, service: Service) -> MailMessage:
    return await service.get_message(folder, uid)


@router.get(
    "/folders/{folder:path}/messages/{uid}/attachments/{part_id}",
    summary="Download an attachment",
)
async def get_attachment(
    folder: str, uid: int, part_id: str, service: Service
) -> Response:
    content, filename, content_type = await service.get_attachment(folder, uid, part_id)
    return Response(
        content=content,
        media_type=content_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"
        },
    )


@router.post(
    "/messages",
    response_model=SendMailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Send a message",
)
async def send_message(payload: SendMailRequest, service: Service) -> SendMailResponse:
    return await service.send(payload)


@router.post(
    "/folders/{folder:path}/messages/{uid}/move",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Move a message",
)
async def move_message(
    folder: str, uid: int, payload: MoveMailRequest, service: Service
) -> None:
    await service.move(folder, uid, payload)


@router.patch(
    "/folders/{folder:path}/messages/{uid}/flags",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Update message flags",
)
async def update_flags(
    folder: str, uid: int, payload: UpdateFlagsRequest, service: Service
) -> None:
    await service.update_flags(folder, uid, payload)


@router.delete(
    "/folders/{folder:path}/messages/{uid}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Permanently delete a message",
)
async def delete_message(folder: str, uid: int, service: Service) -> None:
    await service.delete(folder, uid)
