"""Opt-in integration test against the GreenMail development container."""

import os
from uuid import uuid4

import pytest

from app.services.mail.adapters import ImapSmtpMailAdapter
from app.services.mail.models import SendMailRequest
from app.shared.config.settings import Settings

pytestmark = pytest.mark.integration


@pytest.mark.skipif(
    os.getenv("RUN_MAIL_INTEGRATION_TESTS") != "1",
    reason="Set RUN_MAIL_INTEGRATION_TESTS=1 with GreenMail running",
)
@pytest.mark.asyncio
async def test_greenmail_smtp_to_imap_round_trip():
    """Send through SMTP, retrieve through IMAP, then clean up the message."""
    settings = Settings(
        mail_imap_host="127.0.0.1",
        mail_imap_port=3143,
        mail_imap_ssl=False,
        mail_smtp_host="127.0.0.1",
        mail_smtp_port=3025,
        mail_smtp_starttls=False,
        mail_username="admin",
        mail_password="admin",
        mail_from="admin@example.com",
    )
    adapter = ImapSmtpMailAdapter(settings)
    subject = f"OpenTaberna integration {uuid4()}"

    message_id = await adapter.send(
        SendMailRequest(
            to=["admin@example.com"], subject=subject, text_body="Round trip"
        )
    )
    # GreenMail's deliberately small IMAP implementation rejects some long
    # SEARCH strings, so use a stable term and identify the exact result by ID.
    page = await adapter.list_messages("INBOX", 0, 50, "OpenTaberna")
    received = next(item for item in page.messages if item.message_id == message_id)

    message = await adapter.get_message("INBOX", received.uid)
    assert message.subject == subject
    assert message.text_body is not None
    assert message.text_body.strip() == "Round trip"

    await adapter.delete("INBOX", received.uid)


@pytest.mark.skipif(
    os.getenv("RUN_MAIL_INTEGRATION_TESTS") != "1",
    reason="Set RUN_MAIL_INTEGRATION_TESTS=1 with GreenMail running",
)
@pytest.mark.asyncio
async def test_greenmail_folder_lifecycle():
    """Create, rename, list, and delete a folder through real IMAP commands."""
    settings = Settings(
        mail_imap_host="127.0.0.1",
        mail_imap_port=3143,
        mail_imap_ssl=False,
        mail_username="admin",
        mail_password="admin",
    )
    adapter = ImapSmtpMailAdapter(settings)
    suffix = uuid4().hex
    original = f"Test-{suffix}"
    renamed = f"Renamed-{suffix}"

    created = await adapter.create_folder(original)
    updated = await adapter.rename_folder(original, renamed)
    folders = await adapter.list_folders()

    assert created.name == original
    assert updated.name == renamed
    assert renamed in {folder.name for folder in folders}

    await adapter.delete_folder(renamed)
    folders = await adapter.list_folders()
    assert renamed not in {folder.name for folder in folders}
