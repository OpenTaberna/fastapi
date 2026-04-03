"""
Send Tracking Email

Sends a plain-text + HTML tracking notification to the customer after an
order is marked as SHIPPED. Uses Python's built-in smtplib wrapped in
asyncio.to_thread so the blocking socket I/O never stalls the event loop.

SMTP credentials are read from Settings (smtp_host, smtp_port, smtp_user,
smtp_password, email_from). When smtp_host is empty the function logs a
warning and returns without raising — this makes the endpoint work in
development environments without a live SMTP server.
"""

import asyncio
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from uuid import UUID

from app.shared.config.settings import Settings
from app.shared.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def send_tracking_email(
    to_email: str,
    customer_name: str,
    order_id: UUID,
    tracking_number: str | None,
    carrier: str,
    settings: Settings,
) -> None:
    """
    Send a shipping confirmation e-mail with the tracking number.

    Runs the blocking SMTP call in a thread via asyncio.to_thread so the
    async event loop is never blocked.  If smtp_host is not configured the
    function skips sending and logs a warning instead of raising.

    Args:
        to_email:        Recipient e-mail address (the customer's address).
        customer_name:   Customer's full name for the greeting.
        order_id:        UUID of the shipped order.
        tracking_number: Carrier tracking number, or None if not yet available.
        carrier:         Carrier name string (e.g. "manual", "dhl").
        settings:        Application settings (injected by caller).

    Returns:
        None. Errors are logged; SMTP failures do not surface as HTTP errors
        so the order status update is not rolled back.
    """
    if not settings.smtp_host:
        logger.warning(
            "SMTP host not configured — skipping tracking email",
            extra={"order_id": str(order_id), "to": to_email},
        )
        return

    subject = f"Your order {order_id} has been shipped!"
    text_body = _build_plain_text(customer_name, order_id, tracking_number, carrier)
    html_body = _build_html(customer_name, order_id, tracking_number, carrier)

    message = _build_message(
        from_addr=settings.email_from,
        to_addr=to_email,
        subject=subject,
        text_body=text_body,
        html_body=html_body,
    )

    await asyncio.to_thread(
        _send_via_smtp,
        host=settings.smtp_host,
        port=settings.smtp_port,
        user=settings.smtp_user,
        password=settings.smtp_password,
        from_addr=settings.email_from,
        to_addr=to_email,
        message=message,
        order_id=str(order_id),
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _build_message(
    from_addr: str,
    to_addr: str,
    subject: str,
    text_body: str,
    html_body: str,
) -> MIMEMultipart:
    """
    Compose a MIME multipart/alternative email message.

    Args:
        from_addr: Sender e-mail address.
        to_addr:   Recipient e-mail address.
        subject:   E-mail subject line.
        text_body: Plain-text fallback body.
        html_body: HTML body (displayed by modern clients).

    Returns:
        Fully assembled MIMEMultipart message ready for SMTP delivery.
    """
    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = from_addr
    message["To"] = to_addr
    message.attach(MIMEText(text_body, "plain", "utf-8"))
    message.attach(MIMEText(html_body, "html", "utf-8"))
    return message


def _send_via_smtp(
    host: str,
    port: int,
    user: str,
    password: str,
    from_addr: str,
    to_addr: str,
    message: MIMEMultipart,
    order_id: str,
) -> None:
    """
    Establish an SMTP connection and deliver the message.

    Uses STARTTLS when the port is 587; falls back to plain SMTP otherwise.
    This function is blocking and must only be called via asyncio.to_thread.

    Args:
        host:      SMTP server hostname.
        port:      SMTP server port (587 → STARTTLS, other → plain).
        user:      SMTP authentication username.
        password:  SMTP authentication password.
        from_addr: Envelope sender address.
        to_addr:   Envelope recipient address.
        message:   Assembled MIME message to send.
        order_id:  Order ID string used for structured log context only.

    Returns:
        None on success. Logs errors without re-raising so an SMTP failure
        does not roll back the order status update.
    """
    try:
        with smtplib.SMTP(host, port, timeout=10) as smtp:
            if port == 587:
                smtp.starttls()
            if user and password:
                smtp.login(user, password)
            smtp.sendmail(from_addr, to_addr, message.as_string())
        logger.info(
            "Tracking email sent",
            extra={"order_id": order_id, "to": to_addr},
        )
    except smtplib.SMTPException as exc:
        logger.error(
            "Failed to send tracking email",
            extra={"order_id": order_id, "to": to_addr, "error": str(exc)},
            exc_info=True,
        )


def _build_plain_text(
    customer_name: str,
    order_id: UUID,
    tracking_number: str | None,
    carrier: str,
) -> str:
    """
    Build the plain-text body of the tracking notification e-mail.

    Args:
        customer_name:   Customer's full name.
        order_id:        UUID of the shipped order.
        tracking_number: Carrier tracking number, or None.
        carrier:         Carrier name string.

    Returns:
        Plain-text email body as a string.
    """
    tracking_line = (
        f"Tracking number: {tracking_number}"
        if tracking_number
        else "Tracking number: not yet available"
    )
    return (
        f"Hi {customer_name},\n\n"
        f"Great news — your order {order_id} has been shipped via {carrier}!\n\n"
        f"{tracking_line}\n\n"
        "Thank you for your purchase.\n\n"
        "The OpenTaberna Team"
    )


def _build_html(
    customer_name: str,
    order_id: UUID,
    tracking_number: str | None,
    carrier: str,
) -> str:
    """
    Build the HTML body of the tracking notification e-mail.

    Args:
        customer_name:   Customer's full name.
        order_id:        UUID of the shipped order.
        tracking_number: Carrier tracking number, or None.
        carrier:         Carrier name string.

    Returns:
        HTML email body as a string.
    """
    tracking_display = tracking_number if tracking_number else "Not yet available"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Your order has been shipped</title>
</head>
<body style="font-family: Arial, sans-serif; font-size: 14px; color: #222; max-width: 600px; margin: 0 auto; padding: 20px;">
  <h2 style="color: #2c7a4b;">Your order is on its way!</h2>
  <p>Hi <strong>{customer_name}</strong>,</p>
  <p>Great news — your order has been shipped!</p>
  <table style="border-collapse: collapse; margin: 16px 0; width: 100%;">
    <tr>
      <td style="padding: 8px 12px; background: #f8f8f8; font-weight: bold; border: 1px solid #ddd;">Order ID</td>
      <td style="padding: 8px 12px; border: 1px solid #ddd;">{order_id}</td>
    </tr>
    <tr>
      <td style="padding: 8px 12px; background: #f8f8f8; font-weight: bold; border: 1px solid #ddd;">Carrier</td>
      <td style="padding: 8px 12px; border: 1px solid #ddd;">{carrier}</td>
    </tr>
    <tr>
      <td style="padding: 8px 12px; background: #f8f8f8; font-weight: bold; border: 1px solid #ddd;">Tracking Number</td>
      <td style="padding: 8px 12px; border: 1px solid #ddd;">{tracking_display}</td>
    </tr>
  </table>
  <p>Thank you for your purchase.</p>
  <p style="color: #888; font-size: 12px;">The OpenTaberna Team</p>
</body>
</html>"""
