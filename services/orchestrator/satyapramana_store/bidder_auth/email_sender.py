"""Sends the email-verification and password-reset emails. Same honest
plug-in shape as explain/gemini.py and adapters/sandbox_co_in.py: a real
sender when configured, an UnconfiguredEmailSender that reports exactly why
it can't act when it isn't -- never a fabricated "email sent".

Uses stdlib smtplib/email only, matching auth/passwords.py's own reasoning
for staying dependency-free where a few dozen correct lines already do the
job -- SMTP is a standard, not a provider-specific API, so there is no
provider SDK to add here at all.
"""
from __future__ import annotations

import os
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage


@dataclass(frozen=True)
class EmailSendOutcome:
    delivered: bool
    detail: str


class SmtpEmailSender:
    def __init__(self, *, host: str, port: int, username: str | None,
                 password: str | None, from_address: str, use_tls: bool):
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._from_address = from_address
        self._use_tls = use_tls

    def send(self, *, to_address: str, subject: str, body: str) -> EmailSendOutcome:
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = self._from_address
        message["To"] = to_address
        message.set_content(body)
        try:
            with smtplib.SMTP(self._host, self._port, timeout=10) as smtp:
                if self._use_tls:
                    smtp.starttls()
                if self._username and self._password:
                    smtp.login(self._username, self._password)
                smtp.send_message(message)
        except (smtplib.SMTPException, OSError) as exc:
            # A real, specific failure (bad credentials, host unreachable,
            # recipient refused) -- surfaced to the caller, never swallowed
            # into a fabricated "sent".
            return EmailSendOutcome(delivered=False, detail=f"{type(exc).__name__}: {exc}")
        return EmailSendOutcome(delivered=True, detail="sent")


class UnconfiguredEmailSender:
    """No SMTP credentials -- an honest, visible absence, not a mock send.
    The verification token/reset token this deployment generates is real
    and still gets recorded; it just cannot be delivered anywhere until an
    operator configures SATYAPRAMANA_SMTP_*."""

    def send(self, *, to_address: str, subject: str, body: str) -> EmailSendOutcome:
        return EmailSendOutcome(
            delivered=False,
            detail="SATYAPRAMANA_SMTP_HOST is not configured on this deployment -- "
                   "email delivery is unavailable. The account and token were still "
                   "created for real.",
        )


def build_from_env():
    host = os.environ.get("SATYAPRAMANA_SMTP_HOST")
    if not host:
        return UnconfiguredEmailSender()
    port = int(os.environ.get("SATYAPRAMANA_SMTP_PORT") or "587")
    username = os.environ.get("SATYAPRAMANA_SMTP_USERNAME") or None
    password = os.environ.get("SATYAPRAMANA_SMTP_PASSWORD") or None
    from_address = os.environ.get("SATYAPRAMANA_SMTP_FROM_ADDRESS") or "no-reply@satyapramana.local"
    use_tls = (os.environ.get("SATYAPRAMANA_SMTP_USE_TLS") or "1") != "0"
    return SmtpEmailSender(host=host, port=port, username=username,
                            password=password, from_address=from_address, use_tls=use_tls)
