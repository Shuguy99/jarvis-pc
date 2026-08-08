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
  "Джарвис, отправь голосовое в телеграм"
  "Джарвис, пришли видео в телеграм"
  "Джарвис, создай опрос Кто лучший?/Джарвис, Тони, Брюс"
  "Джарвис, покажи что я печатаю"
  "Джарвис, забань пользователя 123456"
  "Джарвис, замьють пользователя 123456 на 1 час"
  "Джарвис, скопируй сообщение 50 в чат 789"
  "Джарвис, сколько участников в чате"
  "Джарвис, отправь стикер с file_id"

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
import mimetypes
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from ..config import TelegramConfig
from ..rate_limit import rate_limiter
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
    rate_limiter.wait("telegram_api")
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


# ── Медиа-хелперы ──────────────────────────────────────────────────


def _build_multipart(fields: dict[str, str | bytes], files: dict[str, tuple[str, bytes, str]]) -> tuple[bytes, str]:
    """Строит multipart/form-data тело для загрузки файлов.

    Args:
        fields: текстовые поля {name: value}
        files: файловые поля {name: (filename, data, mime_type)}
    Returns:
        (body, content_type) кортеж
    """
    boundary = "----JarvisBoundary7394"
    body = b""
    for name, value in fields.items():
        body += f"--{boundary}\r\n".encode("utf-8")
        body += f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8")
        body += str(value).encode("utf-8")
        body += b"\r\n"
    for name, (filename, data, mime) in files.items():
        body += f"--{boundary}\r\n".encode("utf-8")
        body += f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode("utf-8")
        body += f"Content-Type: {mime}\r\n\r\n".encode("utf-8")
        body += data
        body += b"\r\n"
    body += f"--{boundary}--\r\n".encode("utf-8")
    return body, f"multipart/form-data; boundary={boundary}"


def _send_media(config: TelegramConfig, method: str, field_name: str,
                file_path: str, caption: str = "", extra_fields: dict[str, str] | None = None) -> str:
    """Универсальная отправка медиа-файла через multipart/form-data.

    Args:
        method: API метод (sendVoice, sendVideo, sendAudio, sendSticker...)
        field_name: имя файлового поля (voice, video, audio, sticker...)
        file_path: путь к файлу
        caption: подпись (не для всех типов)
        extra_fields: дополнительные текстовые поля
    """
    err = _check_config(config)
    if err:
        return err
    p = Path(file_path).expanduser()
    if not p.is_file():
        return f"Файл {file_path} не найден, сэр."
    with open(p, "rb") as f:
        file_data = f.read()
    mime = mimetypes.guess_type(str(p))[0] or "application/octet-stream"
    fields: dict[str, str | bytes] = {"chat_id": config.chat_id}
    if caption:
        fields["caption"] = caption
    if extra_fields:
        fields.update(extra_fields)
    files = {field_name: (p.name, file_data, mime)}
    body, content_type = _build_multipart(fields, files)
    url = _API.format(token=config.bot_token) + f"/{method}"
    req = urllib.request.Request(url, data=body, headers={"Content-Type": content_type})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        if result.get("ok"):
            kind = _MEDIA_LABELS.get(field_name, field_name)
            return f"{kind} {p.name} отправлен(о), сэр."
        return f"Ошибка Telegram: {result.get('description', '?')}, сэр."
    except Exception as exc:
        return f"Не удалось отправить {field_name}: {exc}, сэр."


_MEDIA_LABELS = {
    "voice": "Голосовое сообщение",
    "video": "Видео",
    "audio": "Аудио",
    "sticker": "Стикер",
    "animation": "Анимация",
    "video_note": "Видеосообщение",
}


def _parse_duration(duration_str: str) -> int | None:
    """Парсит длительность мута из строки.

    Форматы: "30s", "5m", "1h", "1d", "7d", или число (секунды).
    """
    s = duration_str.strip().lower()
    if not s:
        return None
    # Просто число — секунды
    if s.isdigit():
        return int(s)
    # Формат с суффиксом
    multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    if len(s) >= 2 and s[-1] in multipliers:
        try:
            return int(s[:-1]) * multipliers[s[-1]]
        except ValueError:
            return None
    return None


# ── Новые медиа ────────────────────────────────────────────────────


def tg_send_voice(config: TelegramConfig, file_path: str, caption: str = "") -> str:
    """Отправляет голосовое сообщение/аудиофайл как voice."""
    return _send_media(config, "sendVoice", "voice", file_path, caption)


def tg_send_video(config: TelegramConfig, file_path: str, caption: str = "") -> str:
    """Отправляет видео в чат."""
    return _send_media(config, "sendVideo", "video", file_path, caption)


def tg_send_audio(config: TelegramConfig, file_path: str, caption: str = "") -> str:
    """Отправляет аудиофайл (MP3 и др.) как audio."""
    return _send_media(config, "sendAudio", "audio", file_path, caption)


def tg_send_sticker(config: TelegramConfig, file_id: str = "", file_path: str = "") -> str:
    """Отправляет стикер по file_id или пути к файлу.

    Prioritises file_id (server-side sticker), falls back to file upload.
    """
    err = _check_config(config)
    if err:
        return err
    if file_id:
        payload = {"chat_id": config.chat_id, "sticker": file_id}
        result = _tg_request(config, "sendSticker", payload)
        if result:
            return "Стикер отправлен, сэр."
        return "Не удалось отправить стикер, сэр."
    if file_path:
        return _send_media(config, "sendSticker", "sticker", file_path)
    return "Укажите file_id или file_path для стикера, сэр."


def tg_send_animation(config: TelegramConfig, file_path: str, caption: str = "") -> str:
    """Отправляет GIF-анимацию в чат."""
    return _send_media(config, "sendAnimation", "animation", file_path, caption)


def tg_send_video_note(config: TelegramConfig, file_path: str) -> str:
    """Отправляет круглые видеосообщения (video note)."""
    return _send_media(config, "sendVideoNote", "video_note", file_path)


# ── Опросы и интерактив ───────────────────────────────────────────


def tg_send_poll(config: TelegramConfig, question: str, options: str,
                  is_anonymous: bool = True, is_quiz: bool = False) -> str:
    """Создаёт опрос в чате.

    Args:
        question: вопрос опроса
        options: варианты через "," (запятую)
        is_anonymous: анонимный ли опрос
        is_quiz: режим викторины (нужен correct_option_id)
    """
    err = _check_config(config)
    if err:
        return err
    choices = [o.strip() for o in options.split(",") if o.strip()]
    if len(choices) < 2:
        return "Нужно минимум 2 варианта ответа, сэр."
    if len(choices) > 10:
        return "Максимум 10 вариантов ответа, сэр."
    payload: dict[str, Any] = {
        "chat_id": config.chat_id,
        "question": question,
        "options": [{"text": c} for c in choices],
        "is_anonymous": is_anonymous,
        "type": "quiz" if is_quiz else "regular",
    }
    result = _tg_request(config, "sendPoll", payload)
    if result:
        poll_type = "викторину" if is_quiz else "опрос"
        return f"{poll_type.capitalize()} с {len(choices)} вариантами создан(а), сэр."
    return "Не удалось создать опрос, сэр."


def tg_stop_poll(config: TelegramConfig, message_id: int) -> str:
    """Останавливает опрос по ID сообщения."""
    err = _check_config(config)
    if err:
        return err
    payload = {
        "chat_id": config.chat_id,
        "message_id": message_id,
    }
    result = _tg_request(config, "stopPoll", payload)
    if isinstance(result, dict):
        return f"Опрос {message_id} остановлен, сэр."
    return "Не удалось остановить опрос, сэр."


def tg_answer_callback_query(config: TelegramConfig, callback_query_id: str,
                               text: str = "", show_alert: bool = False) -> str:
    """Отвечает на нажатие inline-кнопки (callback query).

    Позволяет показать уведомление или всплывающее окно пользователю.
    """
    if not config.bot_token:
        return "Telegram не настроен, сэр."
    payload: dict[str, Any] = {
        "callback_query_id": callback_query_id,
        "text": text,
        "show_alert": show_alert,
    }
    result = _tg_request(config, "answerCallbackQuery", payload)
    if result is True:
        return "Ответ на callback отправлен, сэр."
    return "Не удалось ответить на callback, сэр."


def tg_send_chat_action(config: TelegramConfig, action: str) -> str:
    """Показывает действие бота в чате (typing, upload_photo, record_video...).

    Действия: typing, upload_photo, record_video, upload_video,
    record_audio, upload_audio, upload_document, find_location,
    record_video_note, upload_video_note.
    """
    err = _check_config(config)
    if err:
        return err
    valid = {
        "typing", "upload_photo", "record_video", "upload_video",
        "record_audio", "upload_audio", "upload_document",
        "find_location", "record_video_note", "upload_video_note",
    }
    action = action.strip().lower()
    if action not in valid:
        return f"Неизвестное действие. Доступные: {', '.join(sorted(valid))}, сэр."
    payload = {"chat_id": config.chat_id, "action": action}
    result = _tg_request(config, "sendChatAction", payload)
    if result is True:
        action_labels = {
        "typing": "печатает...",
        "upload_photo": "отправляет фото...",
        "record_video": "записывает видео...",
        "upload_video": "отправляет видео...",
        "record_audio": "записывает аудио...",
        "upload_audio": "отправляет аудио...",
        "upload_document": "отправляет документ...",
        "find_location": "отправляет локацию...",
        "record_video_note": "записывает видеосообщение...",
        "upload_video_note": "отправляет видеосообщение...",
    }
        return f"Статус: {action_labels.get(action, action)}, сэр."
    return "Не удалось установить статус действия, сэр."


# ── Админ-функции ──────────────────────────────────────────────────


def tg_ban_user(config: TelegramConfig, user_id: int, until_date: str = "") -> str:
    """Банит пользователя в чате.

    Args:
        user_id: ID пользователя для бана
        until_date: длительность бана ("30s", "1h", "7d") или пусто = навсегда
    """
    err = _check_config(config)
    if err:
        return err
    payload: dict[str, Any] = {
        "chat_id": config.chat_id,
        "user_id": user_id,
    }
    if until_date:
        from datetime import datetime, timezone, timedelta
        seconds = _parse_duration(until_date)
        if seconds:
            until_ts = int((datetime.now(tz=timezone.utc) + timedelta(seconds=seconds)).timestamp())
            payload["until_date"] = until_ts
    result = _tg_request(config, "banChatMember", payload)
    if result is True:
        dur = f" на {until_date}" if until_date else " навсегда"
        return f"Пользователь {user_id} забанен{dur}, сэр."
    return f"Не удалось забанить пользователя {user_id}, сэр."


def tg_unban_user(config: TelegramConfig, user_id: int) -> str:
    """Разбанивает пользователя в чате."""
    err = _check_config(config)
    if err:
        return err
    payload = {
        "chat_id": config.chat_id,
        "user_id": user_id,
        "only_if_banned": True,
    }
    result = _tg_request(config, "unbanChatMember", payload)
    if result is True:
        return f"Пользователь {user_id} разбанен, сэр."
    return f"Не удалось разбанить пользователя {user_id}, сэр."


def tg_mute_user(config: TelegramConfig, user_id: int, duration: str = "") -> str:
    """Ограничивает пользователя (мьют): запрещает отправку сообщений.

    Args:
        user_id: ID пользователя
        duration: длительность ("30s", "5m", "1h", "1d") или пусто = навсегда
    """
    err = _check_config(config)
    if err:
        return err
    from datetime import datetime, timezone, timedelta
    permissions = {
        "can_send_messages": False,
        "can_send_audios": False,
        "can_send_documents": False,
        "can_send_photos": False,
        "can_send_videos": False,
        "can_send_video_notes": False,
        "can_send_voice_notes": False,
        "can_add_web_page_previews": False,
    }
    payload: dict[str, Any] = {
        "chat_id": config.chat_id,
        "user_id": user_id,
        "permissions": permissions,
    }
    if duration:
        seconds = _parse_duration(duration)
        if seconds:
            until_ts = int((datetime.now(tz=timezone.utc) + timedelta(seconds=seconds)).timestamp())
            payload["until_date"] = until_ts
    result = _tg_request(config, "restrictChatMember", payload)
    if result is True:
        dur = f" на {duration}" if duration else " навсегда"
        return f"Пользователь {user_id} замьючен{dur}, сэр."
    return f"Не удалось замьютировать пользователя {user_id}, сэр."


def tg_unmute_user(config: TelegramConfig, user_id: int) -> str:
    """Снимает все ограничения с пользователя (размьют)."""
    err = _check_config(config)
    if err:
        return err
    permissions = {
        "can_send_messages": True,
        "can_send_audios": True,
        "can_send_documents": True,
        "can_send_photos": True,
        "can_send_videos": True,
        "can_send_video_notes": True,
        "can_send_voice_notes": True,
        "can_add_web_page_previews": True,
        "can_invite_users": True,
        "can_pin_messages": True,
        "can_manage_topics": True,
    }
    payload = {
        "chat_id": config.chat_id,
        "user_id": user_id,
        "permissions": permissions,
    }
    result = _tg_request(config, "restrictChatMember", payload)
    if result is True:
        return f"Пользователь {user_id} размьючен, сэр."
    return f"Не удалось размьютировать пользователя {user_id}, сэр."


def tg_promote_user(config: TelegramConfig, user_id: int,
                     can_manage_chat: bool = False, can_delete_messages: bool = False,
                     can_manage_video_chats: bool = False,
                     can_restrict_members: bool = False,
                     can_promote_members: bool = False,
                     can_change_info: bool = False,
                     can_invite_users: bool = False,
                     can_post_messages: bool = False,
                     can_edit_messages: bool = False,
                     can_pin_messages: bool = False) -> str:
    """Повышает права пользователя (делает админом с указанными правами)."""
    err = _check_config(config)
    if err:
        return err
    payload: dict[str, Any] = {
        "chat_id": config.chat_id,
        "user_id": user_id,
        "can_manage_chat": can_manage_chat,
        "can_delete_messages": can_delete_messages,
        "can_manage_video_chats": can_manage_video_chats,
        "can_restrict_members": can_restrict_members,
        "can_promote_members": can_promote_members,
        "can_change_info": can_change_info,
        "can_invite_users": can_invite_users,
        "can_post_messages": can_post_messages,
        "can_edit_messages": can_edit_messages,
        "can_pin_messages": can_pin_messages,
    }
    result = _tg_request(config, "promoteChatMember", payload)
    if result is True:
        return f"Пользователь {user_id} повышен до администратора, сэр."
    return f"Не удалось повысить пользователя {user_id}, сэр."


def tg_demote_user(config: TelegramConfig, user_id: int) -> str:
    """Снимает права администратора с пользователя."""
    err = _check_config(config)
    if err:
        return err
    payload = {
        "chat_id": config.chat_id,
        "user_id": user_id,
        "can_manage_chat": False,
        "can_delete_messages": False,
        "can_manage_video_chats": False,
        "can_restrict_members": False,
        "can_promote_members": False,
        "can_change_info": False,
        "can_invite_users": False,
        "can_post_messages": False,
        "can_edit_messages": False,
        "can_pin_messages": False,
        "can_manage_topics": False,
    }
    result = _tg_request(config, "promoteChatMember", payload)
    if result is True:
        return f"Пользователь {user_id} снят с администратора, сэр."
    return f"Не удалось снять права администратора у {user_id}, сэр."


def tg_set_chat_title(config: TelegramConfig, title: str) -> str:
    """Меняет название чата/группы."""
    err = _check_config(config)
    if err:
        return err
    if not title.strip():
        return "Укажите новое название чата, сэр."
    payload = {"chat_id": config.chat_id, "title": title.strip()}
    result = _tg_request(config, "setChatTitle", payload)
    if result is True:
        return f"Название чата изменено на «{title.strip()}», сэр."
    return "Не удалось изменить название чата, сэр."


def tg_set_chat_description(config: TelegramConfig, description: str) -> str:
    """Меняет описание чата/группы."""
    err = _check_config(config)
    if err:
        return err
    payload = {"chat_id": config.chat_id, "description": description}
    result = _tg_request(config, "setChatDescription", payload)
    if result is True:
        return "Описание чата обновлено, сэр."
    return "Не удалось изменить описание чата, сэр."


def tg_leave_chat(config: TelegramConfig) -> str:
    """Бот покидает чат."""
    err = _check_config(config)
    if err:
        return err
    result = _tg_request(config, "leaveChat", {"chat_id": config.chat_id})
    if result is True:
        return "Бот покинул чат, сэр."
    return "Не удалось покинуть чат, сэр."


# ── Утилиты ────────────────────────────────────────────────────────


def tg_copy_message(config: TelegramConfig, message_id: int, to_chat_id: str = "") -> str:
    """Копирует сообщение в другой чат (без подписи пересылки)."""
    err = _check_config(config)
    if err:
        return err
    target = to_chat_id or config.chat_id
    payload = {
        "chat_id": target,
        "from_chat_id": config.chat_id,
        "message_id": message_id,
    }
    result = _tg_request(config, "copyMessage", payload)
    if isinstance(result, dict):
        new_id = result.get("message_id", "?")
        return f"Сообщение скопировано (новый ID {new_id}) в чат {target}, сэр."
    return "Не удалось скопировать сообщение, сэр."


def tg_get_member_count(config: TelegramConfig) -> str:
    """Возвращает количество участников в чате."""
    err = _check_config(config)
    if err:
        return err
    result = _tg_request(config, "getChatMemberCount", {"chat_id": config.chat_id})
    if isinstance(result, int):
        return f"Участников в чате: {result}, сэр."
    return "Не удалось получить количество участников, сэр."


def tg_delete_webhook(config: TelegramConfig) -> str:
    """Удаляет вебхук бота (полезно перед переходом на polling)."""
    if not config.bot_token:
        return "Telegram не настроен, сэр."
    result = _tg_request(config, "deleteWebhook", {"drop_pending_updates": True})
    if result is True:
        return "Вебхук удалён, pending updates сброшены, сэр."
    return "Не удалось удалить вебхук, сэр."


def tg_get_webhook_info(config: TelegramConfig) -> str:
    """Возвращает информацию о текущем вебхуке бота."""
    if not config.bot_token:
        return "Telegram не настроен, сэр."
    result = _tg_request(config, "getWebhookInfo")
    if not isinstance(result, dict):
        return "Не удалось получить информацию о вебхуке, сэр."
    url = result.get("url", "")
    has_custom = result.get("has_custom_certificate", False)
    pending = result.get("pending_update_count", 0)
    last_err = result.get("last_error_date", 0)
    if not url:
        return f"Вебхук не установлен. Pending updates: {pending}, сэр."
    lines = [f"Вебхук: {url}", f"Custom cert: {has_custom}", f"Pending updates: {pending}"]
    if last_err:
        from datetime import datetime, timezone
        err_time = datetime.fromtimestamp(last_err, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
        lines.append(f"Последняя ошибка: {err_time}")
    return "\n".join(lines) + ", сэр."


def tg_export_chat_invite(config: TelegramConfig) -> str:
    """Создаёт ссылку-приглашение в чат."""
    err = _check_config(config)
    if err:
        return err
    result = _tg_request(config, "exportChatInviteLink", {"chat_id": config.chat_id})
    if isinstance(result, str):
        return f"Ссылка-приглашение: {result}, сэр."
    return "Не удалось создать ссылку-приглашение, сэр."


def tg_revoke_chat_invite(config: TelegramConfig, invite_link: str) -> str:
    """Отзывает ссылку-приглашение."""
    err = _check_config(config)
    if err:
        return err
    payload = {"chat_id": config.chat_id, "invite_link": invite_link}
    result = _tg_request(config, "revokeChatInviteLink", payload)
    if isinstance(result, dict) and result.get("invite_link"):
        return "Ссылка-приглашение отозвана, сэр."
    return "Не удалось отозвать ссылку-приглашение, сэр."


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
            name="tg_send_voice",
            description="Отправить голосовое сообщение (voice) в Telegram чат.",
            parameters=object_schema(
                {
                    "file_path": {"type": "string", "description": "Путь к аудиофайлу (ogg/mp3)"},
                    "caption": {"type": "string", "description": "Подпись (необязательно)"},
                },
                required=["file_path"],
            ),
            handler=lambda file_path, caption="": tg_send_voice(config, file_path, caption),
        ),
        Skill(
            name="tg_send_video",
            description="Отправить видео в Telegram чат.",
            parameters=object_schema(
                {
                    "file_path": {"type": "string", "description": "Путь к видеофайлу"},
                    "caption": {"type": "string", "description": "Подпись (необязательно)"},
                },
                required=["file_path"],
            ),
            handler=lambda file_path, caption="": tg_send_video(config, file_path, caption),
        ),
        Skill(
            name="tg_send_audio",
            description="Отправить аудиофайл (MP3) как audio в Telegram чат.",
            parameters=object_schema(
                {
                    "file_path": {"type": "string", "description": "Путь к аудиофайлу"},
                    "caption": {"type": "string", "description": "Подпись (необязательно)"},
                },
                required=["file_path"],
            ),
            handler=lambda file_path, caption="": tg_send_audio(config, file_path, caption),
        ),
        Skill(
            name="tg_send_sticker",
            description="Отправить стикер по file_id (из чата) или по пути к файлу.",
            parameters=object_schema(
                {
                    "file_id": {"type": "string", "description": "file_id стикера из чата"},
                    "file_path": {"type": "string", "description": "Путь к файлу стикера (если нет file_id)"},
                },
            ),
            handler=lambda file_id="", file_path="": tg_send_sticker(config, file_id, file_path),
        ),
        Skill(
            name="tg_send_animation",
            description="Отправить GIF-анимацию в Telegram чат.",
            parameters=object_schema(
                {
                    "file_path": {"type": "string", "description": "Путь к GIF файлу"},
                    "caption": {"type": "string", "description": "Подпись (необязательно)"},
                },
                required=["file_path"],
            ),
            handler=lambda file_path, caption="": tg_send_animation(config, file_path, caption),
        ),
        Skill(
            name="tg_send_video_note",
            description="Отправить круглое видеосообщение (video note) в Telegram чат.",
            parameters=object_schema(
                {"file_path": {"type": "string", "description": "Путь к видеофайлу"}},
                required=["file_path"],
            ),
            handler=lambda file_path: tg_send_video_note(config, file_path),
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
        # --- Опросы ---
        Skill(
            name="tg_send_poll",
            description=(
                "Создать опрос в чате. Варианты через запятую. "
                "Пример: question='Кто лучший?', options='Джарвис, Тони, Брюс'"
            ),
            parameters=object_schema(
                {
                    "question": {"type": "string", "description": "Вопрос опроса"},
                    "options": {"type": "string", "description": "Варианты через запятую (мин 2, макс 10)"},
                    "is_anonymous": {"type": "boolean", "description": "Анонимный (true/false)"},
                    "is_quiz": {"type": "boolean", "description": "Режим викторины (true/false)"},
                },
                required=["question", "options"],
            ),
            handler=lambda question, options, is_anonymous=True, is_quiz=False: tg_send_poll(
                config, question, options, is_anonymous, is_quiz,
            ),
        ),
        Skill(
            name="tg_stop_poll",
            description="Остановить опрос по ID сообщения с опросом.",
            parameters=object_schema(
                {"message_id": {"type": "integer", "description": "ID сообщения с опросом"}},
                required=["message_id"],
            ),
            handler=lambda message_id: tg_stop_poll(config, message_id),
        ),
        # --- Интерактив ---
        Skill(
            name="tg_answer_callback_query",
            description=(
                "Ответить на нажатие inline-кнопки. Показывает toast-уведомление. "
                "callback_query_id берётся из updates."
            ),
            parameters=object_schema(
                {
                    "callback_query_id": {"type": "string", "description": "ID callback query"},
                    "text": {"type": "string", "description": "Текст уведомления"},
                    "show_alert": {"type": "boolean", "description": "Показать как всплывающее окно"},
                },
                required=["callback_query_id"],
            ),
            handler=lambda callback_query_id, text="", show_alert=False: tg_answer_callback_query(
                config, callback_query_id, text, show_alert,
            ),
        ),
        Skill(
            name="tg_send_chat_action",
            description=(
                "Показать действие бота в чате. Действия: typing, upload_photo, "
                "record_video, upload_video, record_audio, upload_audio, "
                "upload_document, find_location."
            ),
            parameters=object_schema(
                {"action": {"type": "string", "description": "Тип действия (typing, upload_photo...)"}},
                required=["action"],
            ),
            handler=lambda action: tg_send_chat_action(config, action),
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
            name="tg_copy_message",
            description="Копировать сообщение в другой чат без подписи пересылки.",
            parameters=object_schema(
                {
                    "message_id": {"type": "integer", "description": "ID сообщения"},
                    "to_chat_id": {"type": "string", "description": "ID целевого чата (по умолчанию — текущий)"},
                },
                required=["message_id"],
            ),
            handler=lambda message_id, to_chat_id="": tg_copy_message(config, message_id, to_chat_id),
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
        Skill(
            name="tg_set_chat_title",
            description="Изменить название чата/группы в Telegram.",
            parameters=object_schema(
                {"title": {"type": "string", "description": "Новое название чата"}},
                required=["title"],
            ),
            handler=lambda title: tg_set_chat_title(config, title),
        ),
        Skill(
            name="tg_set_chat_description",
            description="Изменить описание чата/группы в Telegram.",
            parameters=object_schema(
                {"description": {"type": "string", "description": "Новое описание чата"}},
                required=["description"],
            ),
            handler=lambda description: tg_set_chat_description(config, description),
        ),
        Skill(
            name="tg_leave_chat",
            description="Бот покидает текущий Telegram чат.",
            parameters=object_schema({}),
            handler=lambda: tg_leave_chat(config),
        ),
        # --- Админ-функции ---
        Skill(
            name="tg_ban_user",
            description=(
                "Забанить пользователя в чате по user_id. "
                "until_date: '30s', '1h', '7d' или пусто = навсегда."
            ),
            parameters=object_schema(
                {
                    "user_id": {"type": "integer", "description": "ID пользователя"},
                    "until_date": {"type": "string", "description": "Длительность (30s/1h/7d), пусто = навсегда"},
                },
                required=["user_id"],
            ),
            handler=lambda user_id, until_date="": tg_ban_user(config, user_id, until_date),
        ),
        Skill(
            name="tg_unban_user",
            description="Разбанить пользователя в чате по user_id.",
            parameters=object_schema(
                {"user_id": {"type": "integer", "description": "ID пользователя"}},
                required=["user_id"],
            ),
            handler=lambda user_id: tg_unban_user(config, user_id),
        ),
        Skill(
            name="tg_mute_user",
            description=(
                "Замьютить пользователя (запретить отправку сообщений). "
                "duration: '30s', '5m', '1h', '1d' или пусто = навсегда."
            ),
            parameters=object_schema(
                {
                    "user_id": {"type": "integer", "description": "ID пользователя"},
                    "duration": {"type": "string", "description": "Длительность (30s/5m/1h/1d), пусто = навсегда"},
                },
                required=["user_id"],
            ),
            handler=lambda user_id, duration="": tg_mute_user(config, user_id, duration),
        ),
        Skill(
            name="tg_unmute_user",
            description="Размьютить пользователя (снять все ограничения).",
            parameters=object_schema(
                {"user_id": {"type": "integer", "description": "ID пользователя"}},
                required=["user_id"],
            ),
            handler=lambda user_id: tg_unmute_user(config, user_id),
        ),
        Skill(
            name="tg_promote_user",
            description="Повысить пользователя до администратора чата.",
            parameters=object_schema(
                {
                    "user_id": {"type": "integer", "description": "ID пользователя"},
                },
                required=["user_id"],
            ),
            handler=lambda user_id: tg_promote_user(config, user_id),
        ),
        Skill(
            name="tg_demote_user",
            description="Снять права администратора с пользователя.",
            parameters=object_schema(
                {"user_id": {"type": "integer", "description": "ID пользователя"}},
                required=["user_id"],
            ),
            handler=lambda user_id: tg_demote_user(config, user_id),
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
        Skill(
            name="tg_get_member_count",
            description="Узнать количество участников в Telegram чате.",
            parameters=object_schema({}),
            handler=lambda: tg_get_member_count(config),
        ),
        # --- Утилиты ---
        Skill(
            name="tg_delete_webhook",
            description="Удалить вебхук бота и сбросить pending updates.",
            parameters=object_schema({}),
            handler=lambda: tg_delete_webhook(config),
        ),
        Skill(
            name="tg_get_webhook_info",
            description="Показать информацию о вебхуке бота.",
            parameters=object_schema({}),
            handler=lambda: tg_get_webhook_info(config),
        ),
        Skill(
            name="tg_export_chat_invite",
            description="Создать ссылку-приглашение в Telegram чат.",
            parameters=object_schema({}),
            handler=lambda: tg_export_chat_invite(config),
        ),
        Skill(
            name="tg_revoke_chat_invite",
            description="Отозвать ссылку-приглашение по URL.",
            parameters=object_schema(
                {"invite_link": {"type": "string", "description": "URL ссылки-приглашения"}},
                required=["invite_link"],
            ),
            handler=lambda invite_link: tg_revoke_chat_invite(config, invite_link),
        ),
    ]
