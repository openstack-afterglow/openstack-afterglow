"""Central bounded SMTP transport; acceptance is not mailbox receipt."""

import asyncio
import html
import logging
from dataclasses import dataclass
from datetime import datetime
from email.message import EmailMessage
from email.utils import formataddr

import aiosmtplib

import app.config
from app.services import mail_settings

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TransportResult:
    status: str
    code: str | None = None


def smtp_client(smtp):
    """Explicit TLS modes prevent opportunistic plaintext authentication."""
    if smtp.security not in {"tls", "starttls", "none"} or (
        smtp.security == "none" and (smtp.username or smtp.password)
    ):
        raise ValueError("mail_transport_security_invalid")
    return aiosmtplib.SMTP(
        hostname=smtp.host,
        port=smtp.port,
        username=smtp.username or None,
        password=smtp.password or None,
        use_tls=smtp.security == "tls",
        start_tls=smtp.security == "starttls",
        validate_certs=True,
        timeout=smtp.timeout_seconds,
    )


async def send_message(message, *, smtp=None):
    """Send once. Lost final DATA acknowledgement is unknown, never retried."""
    smtp = (
        smtp
        if smtp is not None
        else (await mail_settings.effective_settings(base_settings=app.config.get_settings())).smtp
    )
    if not smtp.enabled or not smtp.host:
        return TransportResult("failed", "smtp_disabled")
    client = None
    dispatching = False
    try:
        client = smtp_client(smtp)
        async with asyncio.timeout(smtp.timeout_seconds):
            await client.connect()
        dispatching = True
        async with asyncio.timeout(smtp.timeout_seconds):
            refused, _ = await client.send_message(message, sender=smtp.from_address)
        return TransportResult("failed", "smtp_recipient_rejected") if refused else TransportResult("accepted")
    except aiosmtplib.SMTPResponseException:
        return TransportResult("failed", "smtp_rejected")
    except aiosmtplib.SMTPRecipientsRefused:
        return TransportResult("failed", "smtp_recipient_rejected")
    except Exception as exc:
        # Provider diagnostics may echo credentials and DATA. Log only the class.
        _logger.warning("Mail transport failed (%s)", type(exc).__name__)
        return TransportResult(
            "unknown" if dispatching else "failed", "smtp_outcome_unknown" if dispatching else "smtp_connection_failed"
        )
    finally:
        if client is not None:
            client.close()


async def send_email(to: str, subject: str, html_body: str, text_body: str) -> bool:
    """Legacy proof flows remain delivery-before-pending and best-effort Boolean."""
    try:
        smtp = (await mail_settings.effective_settings(base_settings=app.config.get_settings())).smtp
        if not smtp.enabled or not smtp.host:
            return False
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = formataddr((smtp.from_name, smtp.from_address))
        message["To"] = to
        message.set_content(text_body)
        message.add_alternative(html_body, subtype="html")
        return (await send_message(message, smtp=smtp)).status == "accepted"
    except Exception as exc:
        _logger.warning("Mail unavailable (%s)", type(exc).__name__)
        return False


async def send_invitation_email(
    to_email: str,
    project_name: str,
    inviter_name: str,
    accept_url: str,
    expires_at: datetime,
    *,
    projects: list[dict] | None = None,
) -> bool:
    """프로젝트 초대 이메일 전송."""
    from app.config import get_settings

    settings = get_settings()
    site_name = settings.site_name
    expires_str = expires_at.strftime("%Y년 %m월 %d일")

    safe_inviter = html.escape(inviter_name)
    safe_project = html.escape(project_name)
    safe_url = html.escape(accept_url)
    project_text = ""
    project_html = ""
    if projects is not None:
        entries = [
            f"{project['project_name']} ({project['project_id']}): {', '.join(project['role_ids'])}"
            for project in projects
        ]
        project_text = "Default: project_reader\n" + "\n".join(entries) + "\n\n"
        project_html = (
            "<p>Default: project_reader</p><ul>"
            + "".join(f"<li>{html.escape(entry)}</li>" for entry in entries)
            + "</ul>"
        )

    subject = f"[{site_name}] {project_name} 프로젝트 초대"

    text_body = (
        f"{inviter_name}님이 {site_name}의 '{project_name}' 프로젝트에 초대했습니다.\n\n"
        f"{project_text}"
        f"아래 링크를 클릭하여 초대를 수락하세요:\n{accept_url}\n\n"
        f"초대 링크는 {expires_str}까지 유효합니다.\n\n"
        f"이 이메일을 예상하지 못했다면 무시하세요."
    )

    html_body = f"""<!DOCTYPE html>
<html lang="ko">
<head><meta charset="utf-8"></head>
<body style="font-family: sans-serif; color: #1a1a1a; max-width: 480px; margin: 0 auto; padding: 24px;">
  <h2 style="font-size: 18px; margin-bottom: 8px;">{site_name} 프로젝트 초대</h2>
  <p style="color: #555; margin-bottom: 24px;">
    <strong>{safe_inviter}</strong>님이 <strong>{safe_project}</strong> 프로젝트에 초대했습니다.
  </p>
  {project_html}
  <a href="{safe_url}"
     style="display: inline-block; background: #3b82f6; color: #fff; text-decoration: none;
            padding: 12px 24px; border-radius: 6px; font-weight: 600;">
    초대 수락
  </a>
  <p style="color: #999; font-size: 12px; margin-top: 24px;">
    이 링크는 {expires_str}까지 유효합니다.<br>
    이 이메일을 예상하지 못했다면 무시하세요.
  </p>
</body>
</html>"""

    return await send_email(to_email, subject, html_body, text_body)
