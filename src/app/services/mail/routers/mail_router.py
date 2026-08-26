"""Admin-only REST facade used by a future webmail frontend."""

from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Response, status

from app.services.admin.dependencies import require_admin
from app.shared.responses import DataResponse

from ..dependencies import MailOperationsDependency
from ..models.mail_models import (
    CreateFolderRequest,
    MailFolder,
    MailMessage,
    MailMessagePage,
    MailStatus,
    MoveMailRequest,
    RenameFolderRequest,
    SendMailRequest,
    SendMailResponse,
    UpdateFlagsRequest,
)
from ..responses import (
    ATTACHMENT_RESPONSES,
    CREATE_FOLDER_RESPONSES,
    DELETE_FOLDER_RESPONSES,
    DELETE_MESSAGE_RESPONSES,
    FOLDER_RESPONSES,
    LIST_MESSAGES_RESPONSES,
    MESSAGE_RESPONSES,
    MOVE_MESSAGE_RESPONSES,
    RENAME_FOLDER_RESPONSES,
    SEND_MESSAGE_RESPONSES,
    STATUS_RESPONSES,
    UPDATE_FLAGS_RESPONSES,
)

router = APIRouter(dependencies=[Depends(require_admin)])


@router.get(
    "/status",
    response_model=DataResponse[MailStatus],
    summary="Get mailbox configuration status",
    responses=STATUS_RESPONSES,
)
async def mailbox_status(
    operations: MailOperationsDependency,
) -> DataResponse[MailStatus]:
    return DataResponse[MailStatus](
        data=operations.status(), message="Mailbox configuration status retrieved"
    )


@router.get(
    "/folders",
    response_model=DataResponse[list[MailFolder]],
    summary="List mail folders",
    responses=FOLDER_RESPONSES,
)
async def list_folders(
    operations: MailOperationsDependency,
) -> DataResponse[list[MailFolder]]:
    return DataResponse[list[MailFolder]](
        data=await operations.list_folders(), message="Mail folders retrieved"
    )


@router.post(
    "/folders",
    response_model=DataResponse[MailFolder],
    status_code=status.HTTP_201_CREATED,
    summary="Create a mail folder",
    responses=CREATE_FOLDER_RESPONSES,
)
async def create_folder(
    payload: CreateFolderRequest, operations: MailOperationsDependency
) -> DataResponse[MailFolder]:
    return DataResponse[MailFolder](
        data=await operations.create_folder(payload), message="Mail folder created"
    )


@router.get(
    "/folders/{folder:path}/messages",
    response_model=DataResponse[MailMessagePage],
    summary="List messages",
    responses=LIST_MESSAGES_RESPONSES,
)
async def list_messages(
    folder: str,
    operations: MailOperationsDependency,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    query: str | None = Query(None, max_length=200),
) -> DataResponse[MailMessagePage]:
    return DataResponse[MailMessagePage](
        data=await operations.list_messages(folder, offset, limit, query),
        message="Mail messages retrieved",
    )


@router.get(
    "/folders/{folder:path}/messages/{uid}",
    response_model=DataResponse[MailMessage],
    summary="Read a message",
    responses=MESSAGE_RESPONSES,
)
async def get_message(
    folder: str, uid: int, operations: MailOperationsDependency
) -> DataResponse[MailMessage]:
    return DataResponse[MailMessage](
        data=await operations.get_message(folder, uid), message="Mail message retrieved"
    )


@router.get(
    "/folders/{folder:path}/messages/{uid}/attachments/{part_id}",
    summary="Download an attachment",
    responses=ATTACHMENT_RESPONSES,
)
async def get_attachment(
    folder: str, uid: int, part_id: str, operations: MailOperationsDependency
) -> Response:
    content, filename, content_type = await operations.get_attachment(
        folder, uid, part_id
    )
    return Response(
        content=content,
        media_type=content_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"
        },
    )


@router.post(
    "/messages",
    response_model=DataResponse[SendMailResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Send a message",
    responses=SEND_MESSAGE_RESPONSES,
)
async def send_message(
    payload: SendMailRequest, operations: MailOperationsDependency
) -> DataResponse[SendMailResponse]:
    return DataResponse[SendMailResponse](
        data=await operations.send(payload), message="Mail message sent"
    )


@router.post(
    "/folders/{folder:path}/messages/{uid}/move",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Move a message",
    responses=MOVE_MESSAGE_RESPONSES,
)
async def move_message(
    folder: str,
    uid: int,
    payload: MoveMailRequest,
    operations: MailOperationsDependency,
) -> None:
    await operations.move(folder, uid, payload)


@router.patch(
    "/folders/{folder:path}/messages/{uid}/flags",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Update message flags",
    responses=UPDATE_FLAGS_RESPONSES,
)
async def update_flags(
    folder: str,
    uid: int,
    payload: UpdateFlagsRequest,
    operations: MailOperationsDependency,
) -> None:
    await operations.update_flags(folder, uid, payload)


@router.delete(
    "/folders/{folder:path}/messages/{uid}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Permanently delete a message",
    responses=DELETE_MESSAGE_RESPONSES,
)
async def delete_message(
    folder: str, uid: int, operations: MailOperationsDependency
) -> None:
    await operations.delete(folder, uid)


# The catch-all folder routes must remain after message routes so paths such as
# /folders/INBOX/messages/1 are matched by their more specific operation first.
@router.patch(
    "/folders/{folder:path}",
    response_model=DataResponse[MailFolder],
    summary="Rename a mail folder",
    responses=RENAME_FOLDER_RESPONSES,
)
async def rename_folder(
    folder: str,
    payload: RenameFolderRequest,
    operations: MailOperationsDependency,
) -> DataResponse[MailFolder]:
    return DataResponse[MailFolder](
        data=await operations.rename_folder(folder, payload),
        message="Mail folder renamed",
    )


@router.delete(
    "/folders/{folder:path}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a mail folder",
    responses=DELETE_FOLDER_RESPONSES,
)
async def delete_folder(folder: str, operations: MailOperationsDependency) -> None:
    await operations.delete_folder(folder)
