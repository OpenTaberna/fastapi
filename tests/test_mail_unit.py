"""Unit tests for mail schemas, use cases, routing, and MIME helpers."""

from email.message import EmailMessage
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app as main_app
from app.services.admin.dependencies import require_admin
from app.services.mail import mail_api_router
from app.services.mail.adapters.imap_smtp_adapter import (
    ImapSmtpMailAdapter,
    _content,
    _date,
    _decode,
)
from app.services.mail.dependencies import get_mail_operations
from app.services.mail.functions import MailOperations
from app.services.mail.models import (
    CreateFolderRequest,
    MailFlag,
    MailFolder,
    MailMessagePage,
    MoveMailRequest,
    RenameFolderRequest,
    SendMailRequest,
    UpdateFlagsRequest,
)
from app.shared.config.settings import Settings
from app.shared.exceptions import BusinessRuleError


def test_send_request_requires_a_body():
    with pytest.raises(ValidationError):
        SendMailRequest(to=["admin@example.com"])


def test_send_request_accepts_html_only():
    request = SendMailRequest(to=["admin@example.com"], html_body="<p>Hello</p>")
    assert request.html_body == "<p>Hello</p>"


def test_flags_are_stable_api_values():
    assert MailFlag.SEEN.value == "seen"
    assert MailFlag.FLAGGED.value == "flagged"


def test_folder_names_are_trimmed_and_control_characters_rejected():
    assert CreateFolderRequest(name="  Archive  ").name == "Archive"
    with pytest.raises(ValidationError):
        CreateFolderRequest(name="Bad\nFolder")


def test_list_messages_endpoint_wraps_operations_result():
    operations = AsyncMock(spec=MailOperations)
    operations.list_messages.return_value = MailMessagePage(
        messages=[], total=0, offset=0, limit=10
    )
    app = FastAPI()
    app.include_router(mail_api_router, prefix="/v1")
    app.dependency_overrides[require_admin] = lambda: {"sub": "admin"}
    app.dependency_overrides[get_mail_operations] = lambda: operations

    response = TestClient(app).get("/v1/admin/mail/folders/INBOX/messages?limit=10")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["messages"] == []
    operations.list_messages.assert_awaited_once_with("INBOX", 0, 10, None)


@pytest.mark.asyncio
async def test_mail_operations_delegates_provider_neutral_flags():
    adapter = AsyncMock()
    operations = MailOperations(adapter, Settings())

    await operations.update_flags(
        "INBOX",
        7,
        UpdateFlagsRequest(add=[MailFlag.SEEN], remove=[MailFlag.FLAGGED]),
    )

    adapter.update_flags.assert_awaited_once_with(
        "INBOX", 7, [MailFlag.SEEN], [MailFlag.FLAGGED]
    )


def test_mail_operations_status_returns_domain_model():
    settings = Settings(
        mail_imap_host="imap.example.com",
        mail_smtp_host="smtp.example.com",
        mail_username="admin",
    )

    result = MailOperations(AsyncMock(), settings).status()

    assert result.configured is True
    assert result.provider == "imap_smtp"


@pytest.mark.asyncio
async def test_mail_operations_delegates_mutations():
    adapter = AsyncMock()
    operations = MailOperations(adapter, Settings())

    await operations.move("INBOX", 3, MoveMailRequest(destination="Archive"))
    await operations.delete("Archive", 3)

    adapter.move.assert_awaited_once_with("INBOX", 3, "Archive")
    adapter.delete.assert_awaited_once_with("Archive", 3)


@pytest.mark.asyncio
async def test_mail_operations_manage_folders():
    adapter = AsyncMock()
    adapter.create_folder.return_value = MailFolder(name="Archive")
    adapter.rename_folder.return_value = MailFolder(name="Processed")
    operations = MailOperations(adapter, Settings())

    created = await operations.create_folder(CreateFolderRequest(name="Archive"))
    renamed = await operations.rename_folder(
        "Archive", RenameFolderRequest(name="Processed")
    )
    await operations.delete_folder("Processed")

    assert created.name == "Archive"
    assert renamed.name == "Processed"
    adapter.create_folder.assert_awaited_once_with("Archive")
    adapter.rename_folder.assert_awaited_once_with("Archive", "Processed")
    adapter.delete_folder.assert_awaited_once_with("Processed")


@pytest.mark.asyncio
async def test_mail_operations_protect_inbox():
    operations = MailOperations(AsyncMock(), Settings())

    with pytest.raises(BusinessRuleError):
        await operations.rename_folder("INBOX", RenameFolderRequest(name="InboxOld"))
    with pytest.raises(BusinessRuleError):
        await operations.delete_folder("inbox")
    with pytest.raises(BusinessRuleError):
        await operations.create_folder(CreateFolderRequest(name="INBOX"))


def test_message_delete_route_is_not_captured_by_folder_delete():
    operations = AsyncMock(spec=MailOperations)
    app = FastAPI()
    app.include_router(mail_api_router, prefix="/v1")
    app.dependency_overrides[require_admin] = lambda: {"sub": "admin"}
    app.dependency_overrides[get_mail_operations] = lambda: operations

    response = TestClient(app).delete("/v1/admin/mail/folders/INBOX/messages/9")

    assert response.status_code == 204
    operations.delete.assert_awaited_once_with("INBOX", 9)
    operations.delete_folder.assert_not_awaited()


def test_send_openapi_response_uses_concrete_data_schema():
    schema = main_app.openapi()
    response_schema = schema["components"]["schemas"]["DataResponse_SendMailResponse_"]

    assert "example" not in response_schema
    assert response_schema["properties"]["data"]["$ref"].endswith("/SendMailResponse")


def test_mail_openapi_documents_provider_errors():
    operation = main_app.openapi()["paths"]["/v1/admin/mail/folders"]["get"]
    assert {"200", "403", "422", "500", "502"} <= set(operation["responses"])
    create = main_app.openapi()["paths"]["/v1/admin/mail/folders"]["post"]
    assert {"201", "400", "403", "422", "500", "502"} <= set(create["responses"])


def test_sent_message_contains_date_header():
    settings = Settings(
        mail_smtp_host="mail.example.com",
        mail_username="admin",
        mail_password="secret",
        mail_from="admin@example.com",
    )
    smtp = MagicMock()
    smtp.__enter__.return_value = smtp
    with patch(
        "app.services.mail.adapters.imap_smtp_adapter.smtplib.SMTP",
        return_value=smtp,
    ):
        ImapSmtpMailAdapter(settings)._send(
            SendMailRequest(to=["admin@example.com"], text_body="Hello")
        )

    sent_message = smtp.send_message.call_args.args[0]
    assert sent_message["Date"] is not None


def test_mail_parsing_helpers_decode_headers_and_dates():
    assert _decode("=?utf-8?q?Gr=C3=BC=C3=9Fe?=") == "Grüße"
    assert _date("Tue, 26 Aug 2026 13:00:00 +0000").year == 2026
    assert _date("not-a-date") is None


def test_content_parser_separates_bodies_and_attachments():
    message = EmailMessage()
    message.set_content("Plain body")
    message.add_alternative("<p>HTML body</p>", subtype="html")
    message.add_attachment(
        b"report data",
        maintype="application",
        subtype="octet-stream",
        filename="report.bin",
    )

    text, html, attachments = _content(message)

    assert text.strip() == "Plain body"
    assert html.strip() == "<p>HTML body</p>"
    assert attachments[0].filename == "report.bin"
    assert attachments[0].size == len(b"report data")
