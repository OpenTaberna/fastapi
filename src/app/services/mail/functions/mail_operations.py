"""Provider-neutral mailbox use cases with structured audit logging."""

from app.shared.config.settings import Settings
from app.shared.logger import get_logger
from app.shared.exceptions import operation_not_allowed

from ..adapters.interface import MailAdapter
from ..models import (
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

logger = get_logger(__name__)


class MailOperations:
    """Coordinate mail use cases without depending on FastAPI or HTTP models."""

    def __init__(self, adapter: MailAdapter, settings: Settings):
        self.adapter = adapter
        self.settings = settings

    def status(self) -> MailStatus:
        """Return configuration presence without exposing credentials."""
        return MailStatus(
            configured=bool(
                self.settings.mail_imap_host
                and self.settings.mail_smtp_host
                and self.settings.mail_username
            ),
            provider=self.settings.mail_provider,
        )

    async def list_folders(self) -> list[MailFolder]:
        """List folders from the configured mailbox provider."""
        return await self.adapter.list_folders()

    async def create_folder(self, payload: CreateFolderRequest) -> MailFolder:
        """Create a provider folder after applying protected-name rules."""
        self._assert_name_available(payload.name)
        folder = await self.adapter.create_folder(payload.name)
        logger.info("Admin mail folder created", extra={"folder": folder.name})
        return folder

    async def rename_folder(
        self, folder: str, payload: RenameFolderRequest
    ) -> MailFolder:
        """Rename a mutable folder without allowing protected targets."""
        self._assert_mutable(folder, "rename")
        self._assert_name_available(payload.name)
        renamed = await self.adapter.rename_folder(folder, payload.name)
        logger.info(
            "Admin mail folder renamed",
            extra={"source_folder": folder, "destination_folder": renamed.name},
        )
        return renamed

    async def delete_folder(self, folder: str) -> None:
        """Delete a mutable folder and record the administrative action."""
        self._assert_mutable(folder, "delete")
        await self.adapter.delete_folder(folder)
        logger.info("Admin mail folder deleted", extra={"folder": folder})

    async def list_messages(
        self, folder: str, offset: int, limit: int, query: str | None
    ) -> MailMessagePage:
        """Return one offset-based page from a mailbox folder."""
        return await self.adapter.list_messages(folder, offset, limit, query)

    async def get_message(self, folder: str, uid: int) -> MailMessage:
        """Retrieve a complete provider-normalized message."""
        return await self.adapter.get_message(folder, uid)

    async def get_attachment(
        self, folder: str, uid: int, part_id: str
    ) -> tuple[bytes, str, str]:
        """Retrieve decoded attachment bytes and response metadata."""
        return await self.adapter.get_attachment(folder, uid, part_id)

    async def send(self, payload: SendMailRequest) -> SendMailResponse:
        """Submit a message and audit only non-sensitive delivery metadata."""
        message_id = await self.adapter.send(payload)
        logger.info(
            "Admin mail sent",
            extra={
                "message_id": message_id,
                "to_count": len(payload.to),
                "cc_count": len(payload.cc),
                "bcc_count": len(payload.bcc),
            },
        )
        return SendMailResponse(message_id=message_id)

    async def move(self, folder: str, uid: int, payload: MoveMailRequest) -> None:
        """Move a message and record the mailbox mutation."""
        await self.adapter.move(folder, uid, payload.destination)
        logger.info(
            "Admin mail moved",
            extra={
                "source_folder": folder,
                "destination_folder": payload.destination,
                "uid": uid,
            },
        )

    async def update_flags(
        self, folder: str, uid: int, payload: UpdateFlagsRequest
    ) -> None:
        """Apply provider-neutral flags and record the mailbox mutation."""
        await self.adapter.update_flags(folder, uid, payload.add, payload.remove)
        logger.info(
            "Admin mail flags updated",
            extra={
                "folder": folder,
                "uid": uid,
                "added_flags": [flag.value for flag in payload.add],
                "removed_flags": [flag.value for flag in payload.remove],
            },
        )

    async def delete(self, folder: str, uid: int) -> None:
        """Permanently delete a message and record the mailbox mutation."""
        await self.adapter.delete(folder, uid)
        logger.info("Admin mail deleted", extra={"folder": folder, "uid": uid})

    def _assert_mutable(self, folder: str, operation: str) -> None:
        protected = {name.casefold() for name in self.settings.mail_protected_folders}
        if folder.casefold() in protected:
            raise operation_not_allowed(
                operation=f"{operation}_mail_folder",
                reason=f"Mail folder '{folder}' is protected",
            )

    def _assert_name_available(self, folder: str) -> None:
        protected = {name.casefold() for name in self.settings.mail_protected_folders}
        if folder.casefold() in protected:
            raise operation_not_allowed(
                operation="create_or_rename_mail_folder",
                reason=f"Mail folder name '{folder}' is reserved",
            )
