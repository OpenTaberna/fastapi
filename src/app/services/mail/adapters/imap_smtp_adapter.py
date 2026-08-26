"""Standard-library IMAP/SMTP implementation.

Blocking protocol clients are isolated in worker threads so FastAPI's event loop
is never held up by a remote mail server.
"""

import asyncio
import imaplib
import re
import smtplib
import ssl
from datetime import UTC, datetime
from email import policy
from email.header import decode_header, make_header
from email.message import EmailMessage, Message
from email.parser import BytesParser
from email.utils import format_datetime, getaddresses, make_msgid, parsedate_to_datetime

from app.shared.config.settings import Settings
from app.shared.exceptions import ExternalServiceError, NotFoundError, ValidationError

from .interface import MailAdapter
from ..models.mail_models import (
    MailAddress,
    MailAttachment,
    MailFlag,
    MailFolder,
    MailMessage,
    MailMessagePage,
    MailMessageSummary,
    SendMailRequest,
)

_IMAP_FLAGS = {
    "\\Seen": MailFlag.SEEN,
    "\\Answered": MailFlag.ANSWERED,
    "\\Flagged": MailFlag.FLAGGED,
    "\\Deleted": MailFlag.DELETED,
    "\\Draft": MailFlag.DRAFT,
}
_FLAG_TO_IMAP = {value.value: key for key, value in _IMAP_FLAGS.items()}


class ImapSmtpMailAdapter(MailAdapter):
    def __init__(self, settings: Settings):
        self.settings = settings

    async def list_folders(self) -> list[MailFolder]:
        return await asyncio.to_thread(self._list_folders)

    async def create_folder(self, name: str) -> MailFolder:
        return await asyncio.to_thread(self._create_folder, name)

    async def rename_folder(self, folder: str, name: str) -> MailFolder:
        return await asyncio.to_thread(self._rename_folder, folder, name)

    async def delete_folder(self, folder: str) -> None:
        await asyncio.to_thread(self._delete_folder, folder)

    async def list_messages(
        self, folder: str, offset: int, limit: int, query: str | None
    ) -> MailMessagePage:
        return await asyncio.to_thread(
            self._list_messages, folder, offset, limit, query
        )

    async def get_message(self, folder: str, uid: int) -> MailMessage:
        return await asyncio.to_thread(self._get_message, folder, uid)

    async def get_attachment(
        self, folder: str, uid: int, part_id: str
    ) -> tuple[bytes, str, str]:
        return await asyncio.to_thread(self._get_attachment, folder, uid, part_id)

    async def send(self, payload: SendMailRequest) -> str:
        return await asyncio.to_thread(self._send, payload)

    async def move(self, folder: str, uid: int, destination: str) -> None:
        await asyncio.to_thread(self._move, folder, uid, destination)

    async def update_flags(
        self, folder: str, uid: int, add: list[MailFlag], remove: list[MailFlag]
    ) -> None:
        await asyncio.to_thread(self._update_flags, folder, uid, add, remove)

    async def delete(self, folder: str, uid: int) -> None:
        await asyncio.to_thread(self._delete, folder, uid)

    def _imap(self):
        if not self.settings.mail_imap_host:
            raise ValidationError(message="Mailbox IMAP server is not configured")
        try:
            if self.settings.mail_imap_ssl:
                client = imaplib.IMAP4_SSL(
                    self.settings.mail_imap_host,
                    self.settings.mail_imap_port,
                    ssl_context=ssl.create_default_context(),
                    timeout=self.settings.mail_timeout_seconds,
                )
            else:
                client = imaplib.IMAP4(
                    self.settings.mail_imap_host,
                    self.settings.mail_imap_port,
                    timeout=self.settings.mail_timeout_seconds,
                )
            client.login(self.settings.mail_username, self.settings.mail_password)
            return client
        except (OSError, imaplib.IMAP4.error) as exc:
            raise ExternalServiceError(
                message="Could not connect to the IMAP server", original_exception=exc
            ) from exc

    def _selected(self, folder: str, readonly: bool = True):
        client = self._imap()
        status, _ = client.select(folder, readonly=readonly)
        if status != "OK":
            client.logout()
            raise NotFoundError(message=f"Mail folder '{folder}' was not found")
        return client

    def _list_folders(self) -> list[MailFolder]:
        client = self._imap()
        try:
            status, rows = client.list()
            if status != "OK":
                raise ExternalServiceError(message="IMAP folder listing failed")
            result = []
            pattern = re.compile(rb'^\((.*?)\)\s+"?([^" ]+)"?\s+(.*)$')
            for row in rows or []:
                match = pattern.match(row)
                if not match:
                    continue
                flags, delimiter, name = match.groups()
                result.append(
                    MailFolder(
                        name=name.strip(b'"').decode("utf-8", "replace"),
                        delimiter=delimiter.decode("ascii", "replace"),
                        flags=flags.decode("ascii", "replace").split(),
                    )
                )
            return result
        finally:
            client.logout()

    def _create_folder(self, name: str) -> MailFolder:
        client = self._imap()
        try:
            status, _ = client.create(name)
            if status != "OK":
                raise ExternalServiceError(
                    message=f"Could not create mail folder '{name}'"
                )
            return MailFolder(name=name)
        finally:
            client.logout()

    def _rename_folder(self, folder: str, name: str) -> MailFolder:
        client = self._imap()
        try:
            status, _ = client.rename(folder, name)
            if status != "OK":
                raise NotFoundError(
                    message=f"Mail folder '{folder}' could not be renamed"
                )
            return MailFolder(name=name)
        finally:
            client.logout()

    def _delete_folder(self, folder: str) -> None:
        client = self._imap()
        try:
            status, _ = client.delete(folder)
            if status != "OK":
                raise NotFoundError(
                    message=f"Mail folder '{folder}' could not be deleted"
                )
        finally:
            client.logout()

    def _list_messages(
        self, folder: str, offset: int, limit: int, query: str | None
    ) -> MailMessagePage:
        client = self._selected(folder)
        try:
            uids = self._search_uids(client, query)
            uids.reverse()
            page = uids[offset : offset + limit]
            messages = [self._fetch(client, uid, full=False) for uid in page]
            return MailMessagePage(
                messages=messages, total=len(uids), offset=offset, limit=limit
            )
        finally:
            client.logout()

    @staticmethod
    def _search_uids(client, query: str | None) -> list[int]:
        """Search compatibly without requiring provider support for IMAP OR."""
        if not query:
            status, data = client.uid("search", None, "ALL")
            if status != "OK":
                raise ExternalServiceError(message="IMAP message search failed")
            return [int(value) for value in (data[0] or b"").split()]

        matches: set[int] = set()
        escaped = f'"{_imap_escape(query)}"'
        for field in ("SUBJECT", "FROM"):
            status, data = client.uid("search", None, field, escaped)
            if status != "OK":
                raise ExternalServiceError(message="IMAP message search failed")
            matches.update(int(value) for value in (data[0] or b"").split())
        return sorted(matches)

    def _get_message(self, folder: str, uid: int) -> MailMessage:
        client = self._selected(folder)
        try:
            return self._fetch(client, uid, full=True)
        finally:
            client.logout()

    def _fetch(self, client, uid: int, full: bool) -> MailMessage | MailMessageSummary:
        query = (
            "(RFC822 FLAGS RFC822.SIZE)"
            if full
            else "(BODY.PEEK[HEADER] FLAGS RFC822.SIZE)"
        )
        status, data = client.uid("fetch", str(uid), query)
        raw = next((item[1] for item in data or [] if isinstance(item, tuple)), None)
        if status != "OK" or raw is None:
            raise NotFoundError(message=f"Mail message UID {uid} was not found")
        meta = next((item[0] for item in data if isinstance(item, tuple)), b"")
        message = BytesParser(policy=policy.default).parsebytes(raw)
        flag_names = (token.decode() for token in re.findall(rb"\\[A-Za-z]+", meta))
        flags = [_IMAP_FLAGS[name] for name in flag_names if name in _IMAP_FLAGS]
        common = dict(
            uid=uid,
            message_id=message.get("Message-ID"),
            subject=_decode(message.get("Subject", "")),
            sender=_addresses(message.get_all("From", []))[0]
            if _addresses(message.get_all("From", []))
            else None,
            recipients=_addresses(message.get_all("To", [])),
            sent_at=_date(message.get("Date")),
            flags=flags,
            size=len(raw),
            has_attachments=any(part.get_filename() for part in message.walk()),
        )
        if not full:
            return MailMessageSummary(**common)
        text, html, attachments = _content(message)
        return MailMessage(
            **common,
            cc=_addresses(message.get_all("Cc", [])),
            reply_to=_addresses(message.get_all("Reply-To", [])),
            text_body=text,
            html_body=html,
            attachments=attachments,
        )

    def _get_attachment(
        self, folder: str, uid: int, part_id: str
    ) -> tuple[bytes, str, str]:
        message = self._raw_message(folder, uid)
        for index, part in enumerate(message.walk(), start=1):
            if str(index) == part_id and part.get_filename():
                return (
                    part.get_payload(decode=True) or b"",
                    _decode(part.get_filename() or "attachment"),
                    part.get_content_type(),
                )
        raise NotFoundError(message=f"Attachment part '{part_id}' was not found")

    def _raw_message(self, folder: str, uid: int) -> Message:
        client = self._selected(folder)
        try:
            status, data = client.uid("fetch", str(uid), "(RFC822)")
            raw = next(
                (item[1] for item in data or [] if isinstance(item, tuple)), None
            )
            if status != "OK" or raw is None:
                raise NotFoundError(message=f"Mail message UID {uid} was not found")
            return BytesParser(policy=policy.default).parsebytes(raw)
        finally:
            client.logout()

    def _send(self, payload: SendMailRequest) -> str:
        if not self.settings.mail_smtp_host:
            raise ValidationError(message="Mailbox SMTP server is not configured")
        message = EmailMessage()
        message_id = make_msgid(
            domain=(self.settings.mail_from or self.settings.mail_username).partition(
                "@"
            )[2]
            or None
        )
        message["Message-ID"] = message_id
        message["Date"] = format_datetime(datetime.now(UTC))
        message["From"] = self.settings.mail_from or self.settings.mail_username
        message["To"] = ", ".join(str(v) for v in payload.to)
        if payload.cc:
            message["Cc"] = ", ".join(str(v) for v in payload.cc)
        if payload.reply_to:
            message["Reply-To"] = str(payload.reply_to)
        if payload.in_reply_to:
            message["In-Reply-To"] = payload.in_reply_to
        message["Subject"] = payload.subject
        message.set_content(payload.text_body or "")
        if payload.html_body:
            message.add_alternative(payload.html_body, subtype="html")
        recipients = [str(v) for v in payload.to + payload.cc + payload.bcc]
        try:
            with smtplib.SMTP(
                self.settings.mail_smtp_host,
                self.settings.mail_smtp_port,
                timeout=self.settings.mail_timeout_seconds,
            ) as smtp:
                if self.settings.mail_smtp_starttls:
                    smtp.starttls(context=ssl.create_default_context())
                if self.settings.mail_username:
                    smtp.login(self.settings.mail_username, self.settings.mail_password)
                smtp.send_message(message, to_addrs=recipients)
        except (OSError, smtplib.SMTPException) as exc:
            raise ExternalServiceError(
                message="Could not send mail through the SMTP server",
                original_exception=exc,
            ) from exc
        return message_id

    def _move(self, folder: str, uid: int, destination: str) -> None:
        client = self._selected(folder, readonly=False)
        try:
            status, _ = client.uid("MOVE", str(uid), destination)
            if status != "OK":
                # Compatible fallback for servers without RFC 6851 MOVE.
                status, _ = client.uid("COPY", str(uid), destination)
                if status == "OK":
                    client.uid("STORE", str(uid), "+FLAGS.SILENT", "(\\Deleted)")
                    client.expunge()
            if status != "OK":
                raise ExternalServiceError(message="IMAP move failed")
        finally:
            client.logout()

    def _update_flags(
        self, folder: str, uid: int, add: list[MailFlag], remove: list[MailFlag]
    ) -> None:
        client = self._selected(folder, readonly=False)
        try:
            for operation, values in (
                ("+FLAGS.SILENT", add),
                ("-FLAGS.SILENT", remove),
            ):
                flags = [_FLAG_TO_IMAP[value.value] for value in values]
                if flags:
                    status, _ = client.uid(
                        "STORE", str(uid), operation, f"({' '.join(flags)})"
                    )
                    if status != "OK":
                        raise ExternalServiceError(message="IMAP flag update failed")
        finally:
            client.logout()

    def _delete(self, folder: str, uid: int) -> None:
        client = self._selected(folder, readonly=False)
        try:
            status, _ = client.uid("STORE", str(uid), "+FLAGS.SILENT", "(\\Deleted)")
            if status != "OK":
                raise NotFoundError(message=f"Mail message UID {uid} was not found")
            client.expunge()
        finally:
            client.logout()


def _decode(value: str) -> str:
    try:
        return str(make_header(decode_header(value)))
    except LookupError, UnicodeError:
        return value


def _addresses(values: list[str]) -> list[MailAddress]:
    return [
        MailAddress(name=_decode(name) or None, address=address)
        for name, address in getaddresses(values)
        if address
    ]


def _date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed
    except TypeError, ValueError:
        return None


def _content(message: Message) -> tuple[str | None, str | None, list[MailAttachment]]:
    text = html = None
    attachments = []
    for index, part in enumerate(message.walk(), start=1):
        filename = part.get_filename()
        if filename:
            attachments.append(
                MailAttachment(
                    part_id=str(index),
                    filename=_decode(filename),
                    content_type=part.get_content_type(),
                    size=len(part.get_payload(decode=True) or b""),
                    inline=part.get_content_disposition() == "inline",
                    content_id=part.get("Content-ID"),
                )
            )
        elif part.get_content_maintype() != "multipart":
            try:
                value = part.get_content()
            except LookupError, UnicodeDecodeError:
                value = (part.get_payload(decode=True) or b"").decode(
                    "utf-8", "replace"
                )
            if part.get_content_type() == "text/plain" and text is None:
                text = value
            if part.get_content_type() == "text/html" and html is None:
                html = value
    return text, html, attachments


def _imap_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')
