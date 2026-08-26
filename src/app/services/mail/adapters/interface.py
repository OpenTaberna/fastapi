"""Contract that allows IMAP/SMTP to be replaced by Graph or another provider."""

from abc import ABC, abstractmethod

from ..models.mail_models import (
    MailFolder,
    MailMessage,
    MailMessagePage,
    SendMailRequest,
)


class MailAdapter(ABC):
    @abstractmethod
    async def list_folders(self) -> list[MailFolder]: ...

    @abstractmethod
    async def list_messages(
        self, folder: str, offset: int, limit: int, query: str | None
    ) -> MailMessagePage: ...

    @abstractmethod
    async def get_message(self, folder: str, uid: int) -> MailMessage: ...

    @abstractmethod
    async def get_attachment(
        self, folder: str, uid: int, part_id: str
    ) -> tuple[bytes, str, str]: ...

    @abstractmethod
    async def send(self, payload: SendMailRequest) -> str: ...

    @abstractmethod
    async def move(self, folder: str, uid: int, destination: str) -> None: ...

    @abstractmethod
    async def update_flags(
        self, folder: str, uid: int, add: list[str], remove: list[str]
    ) -> None: ...

    @abstractmethod
    async def delete(self, folder: str, uid: int) -> None: ...
