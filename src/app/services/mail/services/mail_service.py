from app.shared.config import get_settings
from app.shared.config.settings import Settings

from ..adapters import ImapSmtpMailAdapter
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


class MailService:
    """Application layer coordinating mailbox use cases."""

    def __init__(self, adapter: MailAdapter, settings: Settings):
        self.adapter = adapter
        self.settings = settings

    def status(self) -> MailStatus:
        return MailStatus(
            configured=bool(
                self.settings.mail_imap_host
                and self.settings.mail_smtp_host
                and self.settings.mail_username
            ),
            provider=self.settings.mail_provider,
        )

    async def list_folders(self) -> list[MailFolder]:
        return await self.adapter.list_folders()

    async def list_messages(
        self, folder: str, offset: int, limit: int, query: str | None
    ) -> MailMessagePage:
        return await self.adapter.list_messages(folder, offset, limit, query)

    async def get_message(self, folder: str, uid: int) -> MailMessage:
        return await self.adapter.get_message(folder, uid)

    async def get_attachment(
        self, folder: str, uid: int, part_id: str
    ) -> tuple[bytes, str, str]:
        return await self.adapter.get_attachment(folder, uid, part_id)

    async def send(self, payload: SendMailRequest) -> SendMailResponse:
        return SendMailResponse(message_id=await self.adapter.send(payload))

    async def move(self, folder: str, uid: int, payload: MoveMailRequest) -> None:
        await self.adapter.move(folder, uid, payload.destination)

    async def update_flags(
        self, folder: str, uid: int, payload: UpdateFlagsRequest
    ) -> None:
        await self.adapter.update_flags(
            folder,
            uid,
            [flag.value for flag in payload.add],
            [flag.value for flag in payload.remove],
        )

    async def delete(self, folder: str, uid: int) -> None:
        await self.adapter.delete(folder, uid)


def get_mail_service() -> MailService:
    settings = get_settings()
    return MailService(ImapSmtpMailAdapter(settings), settings)
