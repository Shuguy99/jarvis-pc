"""Двусторонний Telegram-чат: отправка, чтение и вебхуки.

В отличие от telegram_bot.py (только отправка), этот модуль также
читает обновления и позволяет настроить вебхук.

Токен и чат берутся из переменных окружения:
  TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.parse
import urllib.request
from typing import Any

from .registry import Skill, object_schema

log = logging.getLogger(__name__)

_API = "https://api.telegram.org/bot{token}"


def _get_token() -> str:
    return os.environ.get("TELEGRAM_BOT_TOKEN", "")


def _get_chat_id() -> str:
    return os.environ.get("TELEGRAM_CHAT_ID", "")


def _tg_request(method: str, data: dict[str, Any] | None = None) -> dict | None:
    """POST/GET запрос к Telegram Bot API."""
    token = _get_token()
    if not token:
        return None
    url = _API.format(token=token) + f"/{method}"
    try:
        if data is not None:
            payload = json.dumps(data).encode("utf-8")
            req = urllib.request.Request(
                url, data=payload,
                headers={"Content-Type": "application/json"},
            )
        else:
            req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        if not result.get("ok"):
            log.warning("Telegram API %s: %s", method, result.get("description"))
            return None
        return result.get("result")
    except Exception as exc:
        log.warning("Telegram API ошибка: %s", exc)
        return None


def tg_send(text: str, chat_id: str = "") -> str:
    """Отправить сообщение в Telegram чат."""
    token = _get_token()
    if not token:
        return "TELEGRAM_BOT_TOKEN не задан в окружении, сэр."
    target = chat_id or _get_chat_id()
    if not target:
        return "TELEGRAM_CHAT_ID не задан в окружении, сэр."
    result = _tg_request("sendMessage", {"chat_id": target, "text": text})
    if result:
        return f"Сообщение отправлено в чат {target}, сэр."
    return "Не удалось отправить сообщение, сэр."


def tg_read_updates(limit: int = 10) -> str:
    """Прочитать последние сообщения бота через getUpdates."""
    token = _get_token()
    if not token:
        return "TELEGRAM_BOT_TOKEN не задан в окружении, сэр."
    result = _tg_request("getUpdates", {
        "limit": limit,
        "allowed_updates": ["message"],
    })
    if not isinstance(result, list) or not result:
        return "Нет новых сообщений, сэр."
    lines = ["Последние сообщения из Telegram:"]
    for update in reversed(result[-limit:]):
        msg = update.get("message", {})
        text = msg.get("text", "")
        from_user = msg.get("from", {}).get("first_name", "?")
        chat_id = msg.get("chat", {}).get("id", "?")
        date_str = ""
        if "date" in msg:
            from datetime import datetime, timezone
            date_str = datetime.fromtimestamp(
                msg["date"], tz=timezone.utc
            ).strftime("%Y-%m-%d %H:%M")
        if text:
            lines.append(f"  [{date_str}] {from_user} (chat {chat_id}): {text[:100]}")
    return "\n".join(lines)


def tg_set_webhook(url: str) -> str:
    """Установить вебхук для получения сообщений."""
    token = _get_token()
    if not token:
        return "TELEGRAM_BOT_TOKEN не задан в окружении, сэр."
    result = _tg_request("setWebhook", {"url": url})
    if isinstance(result, bool) and result:
        return f"Вебхук установлен: {url}, сэр."
    if isinstance(result, dict):
        return f"Вебхук установлен: {url}, сэр."
    return "Не удалось установить вебхук, сэр."


def build_skills() -> list[Skill]:
    """Создаёт навыки двустороннего Telegram-чата."""
    return [
        Skill(
            name="tg_send",
            description="Отправить текстовое сообщение через Telegram бот API.",
            parameters=object_schema(
                {
                    "text": {"type": "string", "description": "Текст сообщения"},
                    "chat_id": {"type": "string", "description": "ID чата (если не указан — из env)"},
                },
                required=["text"],
            ),
            handler=lambda text, chat_id="": tg_send(text, chat_id),
        ),
        Skill(
            name="tg_read_updates",
            description="Прочитать последние входящие сообщения бота (getUpdates).",
            parameters=object_schema(
                {
                    "limit": {
                        "type": "integer",
                        "description": "Максимальное число сообщений (по умолчанию 10)",
                    },
                },
            ),
            handler=lambda limit=10: tg_read_updates(limit),
        ),
        Skill(
            name="tg_set_webhook",
            description="Установить вебхук для приёма сообщений Telegram.",
            parameters=object_schema(
                {
                    "url": {
                        "type": "string",
                        "description": "URL вебхука",
                    },
                },
                required=["url"],
            ),
            handler=lambda url: tg_set_webhook(url),
        ),
    ]
