"""Service simple d'envoi d'emails HTML via SMTP."""

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import smtplib

from backend.core.config import Config


def send_html_email(config: Config, to_email: str, subject: str, html_body: str, text_body: str) -> None:
    if not config.smtp_host or not config.smtp_sender:
        raise RuntimeError("SMTP non configure: definir SMTP_HOST et SMTP_SENDER.")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = config.smtp_sender
    msg["To"] = to_email
    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=30) as server:
        if config.smtp_use_tls:
            server.starttls()
        if config.smtp_user and config.smtp_password:
            server.login(config.smtp_user, config.smtp_password)
        server.sendmail(config.smtp_sender, [to_email], msg.as_string())

