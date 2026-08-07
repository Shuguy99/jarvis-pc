"""Telegram бот: отправка сообщений и команд через Telegram Bot API."""

from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from typing import Any

from ..config import TelegramConfig
from .registry import Skill, object_schema

log = logging.getLogger(__name__)

_API = "https://api.telegram.org/bot{token}"


def _tg_request(config: TelegramConfig, method: str, data: dict | None = None) -> dict | None:
    """POST запрос к Telegram Bot API."""
    url = _API.format(token=config.bot_token) + f"/{method}"
    payload = json.dumps(data or {}).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        if not result.get("ok"):
            log.warning("Telegram API %s: %s", method, result.get("description"))
            return None
        return result.get("result")
    except Exception as exc:
        log.warning("Telegram API ошибка: %s", exc)
        return None


def tg_send_message(config: TelegramConfig, text: str, parse_mode: str = "") -> str:
    """Отправляет текстовое сообщение в чат."""
    if not config.bot_token or not config.chat_id:
        return "Telegram не настроен. Укажите bot_token и chat_id в конфиге, сэр."
    payload: dict[str, Any] = {"chat_id": config.chat_id, "text": text}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    result = _tg_request(config, "sendMessage", payload)
    if result:
        return "Сообщение отправлено в Telegram, сэр."
    return "Не удалось отправить сообщение, сэр."


def tg_send_photo(config: TelegramConfig, photo_path: str, caption: str = "") -> str:
    """Отправляет фото в чат. Файл должен быть доступен по пути."""
    if not config.bot_token or not config.chat_id:
        return "Telegram не настроен, сэр."
    # Отправка файла через multipart/form-data
    from pathlib import Path
    p = Path(photo_path).expanduser()
    if not p.is_file():
        return f"Файл {photo_path} не найден, сэр."
    boundary = "----JarvisBoundary7394"
    with open(p, "rb") as f:
        file_data = f.read()
    filename = p.name
    body_parts = [
        f"--{boundary}\r\n",
        f'Content-Disposition: form-data; name="chat_id"\r\n\r\n',
        f"{config.chat_id}\r\n",
        f"--{boundary}\r\n",
        f'Content-Disposition: form-data; name="photo"; filename="{filename}"\r\n',
        f"Content-Type: application/octet-stream\r\n\r\n",
    ]
    body = b""
    for part in body_parts:
        body += part.encode("utf-8")
    body += file_data
    if caption:
        body += f"\r\n--{boundary}\r\n".encode("utf-8")
        body += f'Content-Disposition: form-data; name="caption"\r\n\r\n'.encode("utf-8")
        body += caption.encode("utf-8")
    body += f"\r\n--{boundary}--\r\n".encode("utf-8")
    url = _API.format(token=config.bot_token) + "/sendPhoto"
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        if result.get("ok"):
            return f"Фото отправлено в Telegram, сэр."
        return f"Ошибка Telegram: {result.get('description', '?')}, сэр."
    except Exception as exc:
        return f"Не удалось отправить фото: {exc}, сэр."


def tg_get_updates(config: TelegramConfig, limit: int = 5) -> str:
    """Получает последние сообщения из чата (для простых сценариев)."""
    if not config.bot_token or not config.chat_id:
        return "Telegram не настроен, сэр."
    result = _tg_request(config, "getUpdates", {"limit": limit, "allowed_updates": ["message"]})
    if not isinstance(result, list) or not result:
        return "Нет новых сообщений, сэр."
    lines = ["Последние сообщения:"]
    for update in reversed(result[-limit:]):
        msg = update.get("message", {})
        text = msg.get("text", "")
        from_user = msg.get("from", {}).get("first_name", "?")
        date_str = ""
        if "date" in msg:
            from datetime import datetime, timezone
            date_str = datetime.fromtimestamp(msg["date"], tz=timezone.utc).strftime("%H:%M")
        if text:
            lines.append(f"  [{date_str}] {from_user}: {text[:80]}")
    return "\n".join(lines)


def tg_me(config: TelegramConfig) -> str:
    """Информация о боте."""
    if not config.bot_token:
        return "Telegram не настроен, сэр."
    result = _tg_request(config, "getMe")
    if isinstance(result, dict):
        name = result.get("first_name", "?")
        username = result.get("username", "?")
        return f"Бот: {name} (@{username}), сэр."
    return "Не удалось получить информацию о боте, сэр."


def build_skills(config: TelegramConfig) -> list[Skill]:
    """Создаёт навыки Telegram."""
    return [
        Skill(
            name="tg_send_message",
            description="Отправить текстовое сообщение в Telegram чат.",
            parameters=object_schema(
                {
                    "text": {"type": "string", "description": "Текст сообщения"},
                },
                required=["text"],
            ),
            handler=lambda text: tg_send_message(config, text),
        ),
        Skill(
            name="tg_send_photo",
            description="Отправить фото/скриншот в Telegram чат.",
            parameters=object_schema(
                {
                    "photo_path": {"type": "string", "description": "Путь к файлу"},
                    "caption": {"type": "string", "description": "Подпись к фото"},
                },
                required=["photo_path"],
            ),
            handler=lambda photo_path, caption="": tg_send_photo(config, photo_path, caption),
        ),
        Skill(
            name="tg_get_updates",
            description="Прочитать последние сообщения из Telegram чата.",
            parameters=object_schema(
                {"limit": {"type": "integer", "description": "Сколько сообщений (по умолчанию 5)"}}
            ),
            handler=lambda limit=5: tg_get_updates(config, limit),
        ),
        Skill(
            name="tg_me",
            description="Информация о Telegram боте.",
            parameters=object_schema({}),
            handler=lambda: tg_me(config),
        ),
    ]
