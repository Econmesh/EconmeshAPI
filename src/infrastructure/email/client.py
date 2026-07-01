"""Async SMTP email sender.

Wraps ``aiosmtplib`` behind a small, dependency-injectable class. Transport is
always encrypted (STARTTLS on 587 or implicit TLS/SSL on 465); plaintext SMTP is
intentionally unsupported. Credentials come exclusively from settings/secrets.
"""

from __future__ import annotations

from email.message import EmailMessage
from email.utils import formataddr
from html import escape

import aiosmtplib

from src.core.config import Settings, get_settings
from src.core.exceptions import ExternalServiceError
from src.core.logging import get_logger

logger = get_logger(__name__)


class EmailSender:
    """Sends transactional emails over an authenticated, encrypted SMTP channel."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    @property
    def enabled(self) -> bool:
        return self._settings.MAIL_ENABLED

    # --------------------------------------------------------------- transport
    async def send(
        self,
        *,
        to: str,
        subject: str,
        text_body: str,
        html_body: str | None = None,
    ) -> None:
        """Send an email. No-op (logged) when mail is disabled.

        Raises :class:`ExternalServiceError` on transport failure so callers can
        decide how to react without leaking SMTP internals to the client.
        """
        if not self.enabled:
            logger.info("email_skipped_disabled", to=to, subject=subject)
            return

        message = self._build_message(to=to, subject=subject, text_body=text_body, html_body=html_body)

        try:
            await aiosmtplib.send(
                message,
                hostname=self._settings.SMTP_HOST,
                port=self._settings.SMTP_PORT,
                username=self._settings.SMTP_USERNAME or None,
                password=self._settings.SMTP_PASSWORD or None,
                start_tls=self._settings.SMTP_USE_TLS,
                use_tls=self._settings.SMTP_USE_SSL,
                timeout=self._settings.SMTP_TIMEOUT_SECONDS,
            )
        except Exception as exc:  # noqa: BLE001 — normalise all SMTP failures
            # Never log the message body/token; only the recipient + subject.
            logger.exception("email_send_failed", to=to, subject=subject)
            raise ExternalServiceError(
                "Failed to send the email.", code="email_send_failed"
            ) from exc

        logger.info("email_sent", to=to, subject=subject)

    def _build_message(
        self,
        *,
        to: str,
        subject: str,
        text_body: str,
        html_body: str | None,
    ) -> EmailMessage:
        message = EmailMessage()
        message["From"] = formataddr((self._settings.MAIL_FROM_NAME, self._settings.MAIL_FROM))
        message["To"] = to
        message["Subject"] = subject
        message.set_content(text_body)
        if html_body is not None:
            message.add_alternative(html_body, subtype="html")
        return message

    # ------------------------------------------------------------- templates
    async def send_account_verification(self, *, to: str, verify_url: str) -> None:
        """Send the account-confirmation email with a one-time link."""
        subject = "Confirm your Econmesh account"
        text_body = (
            "Welcome to Econmesh!\n\n"
            "Confirm your account by opening the link below:\n"
            f"{verify_url}\n\n"
            "This link expires in 24 hours. If you did not create this account, "
            "you can safely ignore this email."
        )
        safe_url = escape(verify_url, quote=True)
        html_body = (
            "<p>Welcome to <strong>Econmesh</strong>!</p>"
            "<p>Confirm your account by clicking the button below:</p>"
            f'<p><a href="{safe_url}" '
            'style="display:inline-block;padding:10px 18px;background:#0f766e;'
            'color:#fff;text-decoration:none;border-radius:6px">Confirm account</a></p>'
            f'<p>Or paste this URL into your browser:<br><a href="{safe_url}">{safe_url}</a></p>'
            "<p style=\"color:#666;font-size:12px\">This link expires in 24 hours. "
            "If you did not create this account, you can safely ignore this email.</p>"
        )
        await self.send(to=to, subject=subject, text_body=text_body, html_body=html_body)

    async def send_notification(self, *, to: str, subject: str, body: str) -> None:
        """Send a platform notification email."""
        safe_subject = escape(subject)
        safe_body = escape(body).replace("\n", "<br>")
        text_body = f"{subject}\n\n{body}"
        html_body = (
            "<div style=\"font-family:sans-serif;max-width:600px\">"
            f"<h2 style=\"color:#0f766e\">{safe_subject}</h2>"
            f"<p>{safe_body}</p>"
            "<p style=\"color:#666;font-size:12px\">"
            "Esta é uma notificação da plataforma Econmesh.</p>"
            "</div>"
        )
        await self.send(to=to, subject=subject, text_body=text_body, html_body=html_body)


email_sender = EmailSender()
"""Process-wide singleton."""


__all__ = ["EmailSender", "email_sender"]
