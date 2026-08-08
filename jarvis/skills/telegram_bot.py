"""Telegram бот: полное управление через Telegram Bot API.

Навыки (голосовые команды):
  "Джарвис, отправь в телеграм Привет!"
  "Джарвис, пришли файл отчёт.pdf в телеграм"
  "Джарвис, перешли сообщение 123 в чат 456"
  "Джарвис, ответь на сообщение 42 текстом ОК"
  "Джарвис, удали сообщение 99 из телеграма"
  "Джарвис, пришли мою геолокацию"
  "Джарвис, закрепи сообщение 50"
  "Джарвис, покажи информацию о чате"
  "Джарвис, отправь кнопки Вопрос? Да/Нет в телеграм"
  "Джарвис, установи команды бота"
  "Джарвис, прочитай телеграм"

Конфигурация в config.yaml::

  telegram:
    enabled: true
    bot_token: "${TELEGRAM_BOT_TOKEN}"
    chat_id: "-1001234567890"
    allowed_users: ["username1"]  # пусто = все разрешены
    notify_on_start: true
    parse_mode: HTML
"""

from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from ..config import TelegramConfig
from .registry import Skill, object_schema

log = logging.getLogger(__name__)

_API = "https://api.telegram.org/bot{token}"


def _tg_request(config: TelegramConfig, method: str, data: dict | None = None) -> dict | list | None:
    """POST запрос к Telegram Bot API."""
    if not config.bot_token:
        return None
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
            log.warning("Telegram %s: %s", method, result.get("description"))
            return None
        return result.get("result")
    except Exception as exc:
        log.warning("Telegram API ошибка: %s", exc)
        return None


def _check_config(config: TelegramConfig) -> str | None:
    """Проверяет настроен ли Telegram. Возвращает ошибку или None."""
    if not config.bot_token or not config.chat_id:
        return "Telegram не настроен. Укажите bot_token и chat_id в конфиге, сэр."
    return None


def _parse_mode(config: TelegramConfig) -> str:
    """Возвращает parse_mode для API (пустая строка если не задан)."""
    mode = config.parse_mode.strip()
    return mode if mode in ("HTML", "Markdown", "MarkdownV2") else ""


# ── Отправка сообщений ────────────────────────────────────────────────


def tg_send_message(config: TelegramConfig, text: str, parse_mode: str = "") -> str:
    """Отправляет текстовое сообщение в чат."""
    err = _check_config(config)
    if err:
        return err
    payload: dict[str, Any] = {"chat_id": config.chat_id, "text": text}
    pm = parse_mode or _parse_mode(config)
    if pm:
        payload["parse_mode"] = pm
    result = _tg_request(config, "sendMessage", payload)
    if result:
        msg_id = result.get("message_id", "?")
        return f"Сообщение отправлено (ID {msg_id}), сэр."
    return "Не удалось отправить сообщение, сэр."


def tg_send_document(config: TelegramConfig, file_path: str, caption: str = "") -> str:
    """Отправляет документ/файл в чат через multipart/form-data."""
    err = _check_config(config)
    if err:
        return err
    p = Path(file_path).expanduser()
    if not p.is_file():
        return f"Файл {file_path} не найден, сэр."
    boundary = "----JarvisBoundary7394"
    with open(p, "rb") as f:
        file_data = f.read()
    filename = p.name
    parts = [
        f"--{boundary}\r\n",
        f'Content-Disposition: form-data; name="chat_id"\r\n\r\n',
        f"{config.chat_id}\r\n",
        f"--{boundary}\r\n",
        f'Content-Disposition: form-data; name="document"; filename="{filename}"\r\n',
        f"Content-Type: application/octet-stream\r\n\r\n",
    ]
    body = b""
    for part in parts:
        body += part.encode("utf-8")
    body += file_data
    if caption:
        body += f"\r\n--{boundary}\r\n".encode("utf-8")
        body += f'Content-Disposition: form-data; name="caption"\r\n\r\n'.encode("utf-8")
        body += caption.encode("utf-8")
    body += f"\r\n--{boundary}--\r\n".encode("utf-8")
    url = _API.format(token=config.bot_token) + "/sendDocument"
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        if result.get("ok"):
            return f"Документ {filename} отправлен, сэр."
        return f"Ошибка Telegram: {result.get('description', '?')}, сэр."
    except Exception as exc:
        return f"Не удалось отправить документ: {exc}, сэр."


def tg_send_photo(config: TelegramConfig, photo_path: str, caption: str = "") -> str:
    """Отправляет фото в чат."""
    err = _check_config(config)
    if err:
        return err
    p = Path(photo_path).expanduser()
    if not p.is_file():
        return f"Файл {photo_path} не найден, сэр."
    boundary = "----JarvisBoundary7394"
    with open(p, "rb") as f:
        file_data = f.read()
    filename = p.name
    parts = [
        f"--{boundary}\r\n",
        f'Content-Disposition: form-data; name="chat_id"\r\n\r\n',
        f"{config.chat_id}\r\n",
        f"--{boundary}\r\n",
        f'Content-Disposition: form-data; name="photo"; filename="{filename}"\r\n',
        f"Content-Type: application/octet-stream\r\n\r\n",
    ]
    body = b""
    for part in parts:
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
            return f"Фото отправлено, сэр."
        return f"Ошибка Telegram: {result.get('description', '?')}, сэр."
    except Exception as exc:
        return f"Не удалось отправить фото: {exc}, сэр."


def tg_send_location(config: TelegramConfig, latitude: float, longitude: float, title: str = "") -> str:
    """Отправляет геолокацию в чат."""
    err = _check_config(config)
    if err:
        return err
    payload: dict[str, Any] = {
        "chat_id": config.chat_id,
        "latitude": latitude,
        "longitude": longitude,
    }
    result = _tg_request(config, "sendLocation", payload)
    if result:
        loc = f"{latitude}, {longitude}"
        return f"Геолокация ({loc}) отправлена, сэр."
    return "Не удалось отправить геолокацию, сэр."


def tg_send_buttons(config: TelegramConfig, text: str, buttons: str = "") -> str:
    """Отправляет сообщение с inline-кнопками.

    buttons — кнопки через разделитель "/" для строк, "," для столбцов.
    Пример: "Да/Нет, Maybe" → [["Да"], ["Нет", "Maybe"]]
    """
    err = _check_config(config)
    if err:
        return err
    if not buttons:
        return "Укажите кнопки, сэр. Например: Да/Нет"
    # Парсинг кнопок из строки
    rows = []
    for row_str in buttons.split("/"):
        row = []
        for btn_text in row_str.split(","):
            btn_text = btn_text.strip()
            if btn_text:
                row.append({"text": btn_text})
        if row:
            rows.append(row)
    if not rows:
        return "Не удалось разобрать кнопки, сэр."
    payload: dict[str, Any] = {
        "chat_id": config.chat_id,
        "text": text,
        "reply_markup": {"inline_keyboard": rows},
    }
    pm = _parse_mode(config)
    if pm:
        payload["parse_mode"] = pm
    result = _tg_request(config, "sendMessage", payload)
    if result:
        btn_count = sum(len(r) for r in rows)
        return f"Сообщение с {btn_count} кнопками отправлено, сэр."
    return "Не удалось отправить кнопки, сэр."


# ── Управление сообщениями ───────────────────────────────────────────


def tg_reply(config: TelegramConfig, message_id: int, text: str) -> str:
    """Ответить на конкретное сообщение."""
    err = _check_config(config)
    if err:
        return err
    payload: dict[str, Any] = {
        "chat_id": config.chat_id,
        "text": text,
        "reply_to_message_id": message_id,
    }
    pm = _parse_mode(config)
    if pm:
        payload["parse_mode"] = pm
    result = _tg_request(config, "sendMessage", payload)
    if result:
        return f"Ответ на сообщение {message_id} отправлен, сэр."
    return "Не удалось отправить ответ, сэр."


def tg_forward(config: TelegramConfig, message_id: int, to_chat_id: str = "") -> str:
    """Переслать сообщение в другой чат."""
    err = _check_config(config)
    if err:
        return err
    target = to_chat_id or config.chat_id
    payload = {
        "chat_id": target,
        "from_chat_id": config.chat_id,
        "message_id": message_id,
    }
    result = _tg_request(config, "forwardMessage", payload)
    if result:
        return f"Сообщение {message_id} переслано в чат {target}, сэр."
    return "Не удалось переслать сообщение, сэр."


def tg_delete_message(config: TelegramConfig, message_id: int) -> str:
    """Удаляет сообщение из чата."""
    err = _check_config(config)
    if err:
        return err
    payload = {
        "chat_id": config.chat_id,
        "message_id": message_id,
    }
    result = _tg_request(config, "deleteMessage", payload)
    if result is True or (isinstance(result, dict) and result.get("ok")):
        return f"Сообщение {message_id} удалено, сэр."
    return f"Не удалось удалить сообщение {message_id}, сэр."


def tg_edit_message(config: TelegramConfig, message_id: int, text: str) -> str:
    """Редактирует отправленное сообщение."""
    err = _check_config(config)
    if err:
        return err
    payload: dict[str, Any] = {
        "chat_id": config.chat_id,
        "message_id": message_id,
        "text": text,
    }
    pm = _parse_mode(config)
    if pm:
        payload["parse_mode"] = pm
    result = _tg_request(config, "editMessageText", payload)
    if result:
        return f"Сообщение {message_id} отредактировано, сэр."
    return "Не удалось отредактировать сообщение, сэр."


# ── Управление чатом ──────────────────────────────────────────────────


def tg_pin_message(config: TelegramConfig, message_id: int, disable_notification: bool = False) -> str:
    """Закрепляет сообщение в чате."""
    err = _check_config(config)
    if err:
        return err
    payload = {
        "chat_id": config.chat_id,
        "message_id": message_id,
        "disable_notification": disable_notification,
    }
    result = _tg_request(config, "pinChatMessage", payload)
    if result is True or (isinstance(result, dict) and result.get("ok")):
        return f"Сообщение {message_id} закреплено, сэр."
    return f"Не удалось закрепить сообщение, сэр."


def tg_unpin_message(config: TelegramConfig, message_id: int | None = None) -> str:
    """Открепляет сообщение (конкретное или все, если не указано)."""
    err = _check_config(config)
    if err:
        return err
    if message_id is not None:
        payload = {"chat_id": config.chat_id, "message_id": message_id}
        result = _tg_request(config, "unpinChatMessage", payload)
        if result is True or (isinstance(result, dict) and result.get("ok")):
            return f"Сообщение {message_id} откреплено, сэр."
        return f"Не удалось открепить сообщение, сэр."
    else:
        result = _tg_request(config, "unpinAllChatMessages", {"chat_id": config.chat_id})
        if result is True or (isinstance(result, dict) and result.get("ok")):
            return "Все закреплённые сообщения откреплены, сэр."
        return "Не удалось открепить сообщения, сэр."


def tg_get_chat_info(config: TelegramConfig) -> str:
    """Информация о чате: название, тип, количество участников."""
    err = _check_config(config)
    if err:
        return err
    result = _tg_request(config, "getChat", {"chat_id": config.chat_id})
    if not isinstance(result, dict):
        return "Не удалось получить информацию о чате, сэр."
    title = result.get("title", "?")
    chat_type = result.get("type", "?")
    desc = result.get("description", "") or ""
    username = result.get("username", "") or ""
    lines = [f"Чат: {title} ({chat_type})"]
    if username:
        lines[0] += f" @{username}"
    if desc:
        lines.append(f"Описание: {desc[:200]}")
    # Количество участников
    if chat_type != "private":
        members = _tg_request(config, "getChatAdministrators", {"chat_id": config.chat_id})
        if isinstance(members, list):
            lines.append(f"Администраторов: {len(members)}")
    return "\n".join(lines)


def tg_set_commands(config: TelegramConfig) -> str:
    """Устанавливает меню команд бота."""
    err = _check_config(config)
    if err:
        return err
    commands = [
        	{"command": "status", "description": "Статус систем"},
        	{"command": "weather", "description": "Погода"},
        	{"command": "time", "description": "Текущее время"},
        	{"command": "skills", "description": "Доступные навыки"},
        	{"command": "help", "description": "Помощь"},
    ]
    result = _tg_request(config, "setMyCommands", {"commands": commands})
    if result is True or (isinstance(result, dict) and result.get("ok")):
        return "Меню команд бота установлено (5 команд), сэр."
    return "Не удалось установить команды бота, сэр."


# ── Чтение и информация ───────────────────────────────────────────────


def tg_get_updates(config: TelegramConfig, limit: int = 5) -> str:
    """Получает последние сообщения из чата."""
    err = _check_config(config)
    if err:
        return err
    result = _tg_request(config, "getUpdates", {
        "limit": limit,
        "allowed_updates": ["message"],
    })
    if not isinstance(result, list) or not result:
        return "Нет новых сообщений, сэр."
    lines = ["Последние сообщения:"]
    from datetime import datetime, timezone
    for update in reversed(result[-limit:]):
        msg = update.get("message", {})
        text = msg.get("text", "")
        from_user = msg.get("from", {}).get("first_name", "?")
        username = msg.get("from", {}).get("username", "")
        date_str = ""
        if "date" in msg:
            date_str = datetime.fromtimestamp(msg["date"], tz=timezone.utc).strftime("%H:%M")
        msg_id = msg.get("message_id", "?")
        sender = f"{from_user} (@{username})" if username else from_user
        if text:
            lines.append(f"  [{date_str}] #{msg_id} {sender}: {text[:80]}")
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


# ── Сборка навыков ────────────────────────────────────────────────────


def build_skills(config: TelegramConfig) -> list[Skill]:
    """Создаёт полный набор Telegram навыков."""
    return [
        # --- Отправка ---
        Skill(
            name="tg_send_message",
            description="Отправить текстовое сообщение в Telegram чат.",
            parameters=object_schema(
                {"text": {"type": "string", "description": "Текст сообщения"}},
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
            name="tg_send_document",
            description="Отправить документ/файл в Telegram чат.",
            parameters=object_schema(
                {
                    "file_path": {"type": "string", "description": "Путь к файлу"},
                    "caption": {"type": "string", "description": "Подпись к файлу"},
                },
                required=["file_path"],
            ),
            handler=lambda file_path, caption="": tg_send_document(config, file_path, caption),
        ),
        Skill(
            name="tg_send_location",
            description="Отправить геолокацию (координаты) в Telegram чат.",
            parameters=object_schema(
                {
                    "latitude": {"type": "number", "description": "Широта"},
                    "longitude": {"type": "number", "description": "Долгота"},
                    "title": {"type": "string", "description": "Название места (необязательно)"},
                },
                required=["latitude", "longitude"],
            ),
            handler=lambda latitude, longitude, title="": tg_send_location(config, latitude, longitude, title),
        ),
        Skill(
            name="tg_send_buttons",
            description=(
                "Отправить сообщение с inline-кнопками. Формат кнопок: "
                "строки через /, кнопки в строке через запятую. Пример: 'Да/Нет, Может быть'"
            ),
            parameters=object_schema(
                {
                    "text": {"type": "string", "description": "Текст сообщения"},
                    "buttons": {"type": "string", "description": "Кнопки: строки через /, столбцы через ,"},
                },
                required=["text", "buttons"],
            ),
            handler=lambda text, buttons: tg_send_buttons(config, text, buttons),
        ),
        # --- Управление сообщениями ---
        Skill(
            name="tg_reply",
            description="Ответить на конкретное сообщение в Telegram по его ID.",
            parameters=object_schema(
                {
                    "message_id": {"type": "integer", "description": "ID сообщения для ответа"},
                    "text": {"type": "string", "description": "Текст ответа"},
                },
                required=["message_id", "text"],
            ),
            handler=lambda message_id, text: tg_reply(config, message_id, text),
        ),
        Skill(
            name="tg_forward",
            description="Переслать сообщение из текущего чата в другой чат.",
            parameters=object_schema(
                {
                    "message_id": {"type": "integer", "description": "ID сообщения для пересылки"},
                    "to_chat_id": {"type": "string", "description": "ID целевого чата (по умолчанию — текущий)"},
                },
                required=["message_id"],
            ),
            handler=lambda message_id, to_chat_id="": tg_forward(config, message_id, to_chat_id),
        ),
        Skill(
            name="tg_delete_message",
            description="Удалить сообщение из Telegram чата по его ID.",
            parameters=object_schema(
                {"message_id": {"type": "integer", "description": "ID сообщения для удаления"}},
                required=["message_id"],
            ),
            handler=lambda message_id: tg_delete_message(config, message_id),
        ),
        Skill(
            name="tg_edit_message",
            description="Отредактировать ранее отправленное сообщение по его ID.",
            parameters=object_schema(
                {
                    "message_id": {"type": "integer", "description": "ID сообщения"},
                    "text": {"type": "string", "description": "Новый текст"},
                },
                required=["message_id", "text"],
            ),
            handler=lambda message_id, text: tg_edit_message(config, message_id, text),
        ),
        # --- Управление чатом ---
        Skill(
            name="tg_pin_message",
            description="Закрепить сообщение в Telegram чате.",
            parameters=object_schema(
                {"message_id": {"type": "integer", "description": "ID сообщения для закрепления"}},
                required=["message_id"],
            ),
            handler=lambda message_id: tg_pin_message(config, message_id),
        ),
        Skill(
            name="tg_unpin_message",
            description="Открепить сообщение (ID) или все закреплённые (без ID).",
            parameters=object_schema(
                {"message_id": {"type": "integer", "description": "ID сообщения (пусто = все)"}},
            ),
            handler=lambda message_id=None: tg_unpin_message(config, message_id),
        ),
        Skill(
            name="tg_chat_info",
            description="Показать информацию о Telegram чате (название, тип, описание).",
            parameters=object_schema({}),
            handler=lambda: tg_get_chat_info(config),
        ),
        Skill(
            name="tg_set_commands",
            description="Установить меню команд бота (status, weather, time, skills, help).",
            parameters=object_schema({}),
            handler=lambda: tg_set_commands(config),
        ),
        # --- Чтение и информация ---
        Skill(
            name="tg_get_updates",
            description="Прочитать последние сообщения из Telegram чата.",
            parameters=object_schema(
                {"limit": {"type": "integer", "description": "Сколько сообщений (по умолчанию 5)"}},
            ),
            handler=lambda limit=5: tg_get_updates(config, limit),
        ),
        Skill(
            name="tg_me",
            description="Информация о Telegram боте (имя, username).",
            parameters=object_schema({}),
            handler=lambda: tg_me(config),
        ),
    ]
