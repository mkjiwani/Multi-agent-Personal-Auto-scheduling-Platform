"""Email sending service with Jinja2 HTML templates."""

from __future__ import annotations

import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import aiosmtplib
from jinja2 import Environment, FileSystemLoader

from src.config import settings

logger = logging.getLogger(__name__)

# Template directory
TEMPLATE_DIR = Path(__file__).parent / "templates"
TEMPLATE_DIR.mkdir(exist_ok=True)

# Jinja2 environment
jinja_env = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    autoescape=True,
)


async def send_email(
    subject: str,
    html_body: str,
    to_email: str | None = None,
) -> bool:
    """Send an HTML email via SMTP."""
    to_email = to_email or settings.email_to

    if not settings.smtp_username or not settings.smtp_password:
        logger.warning("SMTP credentials not configured — skipping email send")
        return False

    message = MIMEMultipart("alternative")
    message["From"] = settings.email_from
    message["To"] = to_email
    message["Subject"] = subject
    message.attach(MIMEText(html_body, "html"))

    try:
        await aiosmtplib.send(
            message,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_username,
            password=settings.smtp_password,
            start_tls=True,
        )
        logger.info(f"Email sent: {subject} → {to_email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email: {e}")
        return False


def render_template(template_name: str, **context) -> str:
    """Render a Jinja2 HTML email template."""
    try:
        template = jinja_env.get_template(template_name)
        return template.render(**context)
    except Exception:
        # Fallback: return a simple HTML wrapper
        content = context.get("content", "")
        return f"<html><body>{content}</body></html>"
