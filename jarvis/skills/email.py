"""Отправка email через SMTP."""

from __future__ import annotations

import logging
import os
import smtplib
from email.mime.text import MIMEText

from .registry import Skill, object_schema

log = logging.getLogger(__name__)


def send_email(to: str, subject: str, body: str) -> str:
    host = os.environ.get("JARVIS_SMTP_HOST", "")
    user = os.environ.get("JARVIS_SMTP_USER", "")
    pwd = os.environ.get("JARVIS_SMTP_PASS", "")
    if not host or not user:
        return "SMTP не настроен. Задайте JARVIS_SMTP_HOST/USER/PASS, сэр."
    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = user
        msg["To"] = to
        with smtplib.SMTP(host, 587) as server:
            server.starttls()
            server.login(user, pwd)
            server.send_message(msg)
        return f"Письмо отправлено на {to}, сэр."
    except Exception as exc:
        return f"Ошибка отправки: {exc}, сэр."


def build_skills() -> list[Skill]:
    return [
        Skill(name="send_email", description="Отправить email.",
              parameters=object_schema({
                  "to": {"type": "string", "description": "Адрес получателя"},
                  "subject": {"type": "string", "description": "Тема"},
                  "body": {"type": "string", "description": "Текст письма"},
              }, required=["to", "subject", "body"]),
              handler=lambda to, subject, body: send_email(to, subject, body)),
    ]
