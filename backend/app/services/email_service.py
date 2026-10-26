"""이메일 전송 서비스 (aiosmtplib 기반)."""

import html
import logging
from datetime import datetime

_logger = logging.getLogger(__name__)


async def send_email(to: str, subject: str, html_body: str, text_body: str) -> bool:
    """비동기 SMTP 이메일 전송. 실패 시 False 반환 (best-effort)."""
    from app.config import get_settings

    settings = get_settings()
    if not settings.smtp_enabled or not settings.smtp_host:
        _logger.warning("SMTP 미설정 — 이메일 전송 건너뜀 (to=%s, subject=%s)", to, subject)
        return False

    try:
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText

        import aiosmtplib

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{settings.smtp_from_name} <{settings.smtp_from_address}>"
        msg["To"] = to
        msg.attach(MIMEText(text_body, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        await aiosmtplib.send(
            msg,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_username or None,
            password=settings.smtp_password or None,
            use_tls=False,
            start_tls=settings.smtp_use_tls,
            timeout=settings.smtp_timeout_seconds,
        )
        _logger.info("이메일 전송 완료: to=%s, subject=%s", to, subject)
        return True
    except Exception:
        _logger.error("이메일 전송 실패: to=%s, subject=%s", to, subject, exc_info=True)
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
