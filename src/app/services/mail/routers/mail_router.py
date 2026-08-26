"""Admin-only REST facade used by a future webmail frontend."""

from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Response, status

from app.services.admin.dependencies import require_admin
from app.shared.config import get_settings

from ..adapters.interface import MailAdapter
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
from ..services import get_mail_adapter

router = APIRouter(dependencies=[Depends(require_admin)])
Adapter = Annotated[MailAdapter, Depends(get_mail_adapter)]


@router.get(
    "/status", response_model=MailStatus, summary="Get mailbox configuration status"
)
async def mailbox_status() -> MailStatus:
    settings = get_settings()
    return MailStatus(
        configured=bool(
            settings.mail_imap_host
            and settings.mail_smtp_host
            and settings.mail_username
        ),
        provider=settings.mail_provider,
    )


@router.get("/folders", response_model=list[MailFolder], summary="List mail folders")
async def list_folders(adapter: Adapter) -> list[MailFolder]:
    return await adapter.list_folders()


@router.get(
    "/folders/{folder:path}/messages",
    response_model=MailMessagePage,
    summary="List messages",
)
async def list_messages(
    folder: str,
    adapter: Adapter,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    query: str | None = Query(None, max_length=200),
) -> MailMessagePage:
    return await adapter.list_messages(folder, offset, limit, query)


@router.get(
    "/folders/{folder:path}/messages/{uid}",
    response_model=MailMessage,
    summary="Read a message",
)
async def get_message(folder: str, uid: int, adapter: Adapter) -> MailMessage:
    return await adapter.get_message(folder, uid)


@router.get(
    "/folders/{folder:path}/messages/{uid}/attachments/{part_id}",
    summary="Download an attachment",
)
async def get_attachment(
    folder: str, uid: int, part_id: str, adapter: Adapter
) -> Response:
    content, filename, content_type = await adapter.get_attachment(folder, uid, part_id)
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
async def send_message(payload: SendMailRequest, adapter: Adapter) -> SendMailResponse:
    return SendMailResponse(message_id=await adapter.send(payload))


@router.post(
    "/folders/{folder:path}/messages/{uid}/move",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Move a message",
)
async def move_message(
    folder: str, uid: int, payload: MoveMailRequest, adapter: Adapter
) -> None:
    await adapter.move(folder, uid, payload.destination)


@router.patch(
    "/folders/{folder:path}/messages/{uid}/flags",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Update message flags",
)
async def update_flags(
    folder: str, uid: int, payload: UpdateFlagsRequest, adapter: Adapter
) -> None:
    await adapter.update_flags(
        folder, uid, [v.value for v in payload.add], [v.value for v in payload.remove]
    )


@router.delete(
    "/folders/{folder:path}/messages/{uid}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Permanently delete a message",
)
async def delete_message(folder: str, uid: int, adapter: Adapter) -> None:
    await adapter.delete(folder, uid)
