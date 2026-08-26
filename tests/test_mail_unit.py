from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.services.admin.dependencies import require_admin
from app.services.mail import mail_api_router
from app.services.mail.models.mail_models import (
    MailFlag,
    MailMessagePage,
    SendMailRequest,
)
from app.services.mail.adapters.imap_smtp_adapter import ImapSmtpMailAdapter
from app.shared.config.settings import Settings
from app.services.mail.services import get_mail_adapter


def test_send_request_requires_a_body():
    with pytest.raises(ValidationError):
        SendMailRequest(to=["admin@example.com"])


def test_send_request_accepts_html_only():
    request = SendMailRequest(to=["admin@example.com"], html_body="<p>Hello</p>")
    assert request.html_body == "<p>Hello</p>"


def test_flags_are_stable_api_values():
    assert MailFlag.SEEN.value == "seen"
    assert MailFlag.FLAGGED.value == "flagged"


def test_list_messages_endpoint_uses_adapter():
    adapter = AsyncMock()
    adapter.list_messages.return_value = MailMessagePage(
        messages=[], total=0, offset=0, limit=10
    )
    app = FastAPI()
    app.include_router(mail_api_router, prefix="/v1")
    app.dependency_overrides[require_admin] = lambda: {"sub": "admin"}
    app.dependency_overrides[get_mail_adapter] = lambda: adapter

    response = TestClient(app).get("/v1/admin/mail/folders/INBOX/messages?limit=10")

    assert response.status_code == 200
    assert response.json()["messages"] == []
    adapter.list_messages.assert_awaited_once_with("INBOX", 0, 10, None)


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
