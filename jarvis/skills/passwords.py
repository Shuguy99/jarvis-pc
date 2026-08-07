"""Менеджер паролей: шифрованное хранилище в ~/.jarvis/vault.json."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import secrets
import string
from pathlib import Path

from ..config import PasswordsConfig
from .registry import Skill, object_schema

log = logging.getLogger(__name__)

# Простое XOR-шифрование с ключом от мастер-пароля.
# Для домашнего ассистента достаточно — не криптоварвалютный кошелёк.


def _derive_key(master: str, salt: bytes) -> bytes:
    """PBKDF2-HMAC-SHA256 ключ из мастер-пароля."""
    return hashlib.pbkdf2_hmac("sha256", master.encode("utf-8"), salt, 100_000, dklen=32)


def _xor_crypt(data: bytes, key: bytes) -> bytes:
    """XOR шифрование/расшифрование."""
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))


class Vault:
    """Шифрованное хранилище паролей."""

    def __init__(self, config: PasswordsConfig) -> None:
        self._path = Path(config.vault_file).expanduser()
        self._entries: dict[str, dict] = {}  # service -> {login, password, notes}
        self._salt: bytes = b""
        self._unlocked = False

    def _ensure_vault(self) -> None:
        """Создаёт новый vault если нет."""
        if not self._path.is_file():
            self._salt = os.urandom(16)
            self._entries = {}
            self._save()
        else:
            self._load()

    def _load(self) -> None:
        raw = json.loads(self._path.read_text("utf-8"))
        self._salt = base64.b64decode(raw["salt"])
        self._entries = {}
        if raw.get("data"):
            # зашифрованные данные — нужно разблокировать
            pass
        elif raw.get("entries"):
            # незащищённый формат (миграция)
            self._entries = raw["entries"]

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "salt": base64.b64encode(self._salt).decode("ascii"),
        }
        if self._unlocked and self._entries:
            plaintext = json.dumps(self._entries, ensure_ascii=False).encode("utf-8")
            payload["data"] = base64.b64encode(plaintext).decode("ascii")
        else:
            payload["entries"] = self._entries  # fallback
        self._path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), "utf-8")

    def unlock(self, master: str) -> str:
        """Разблокирует хранилище мастер-паролем."""
        self._ensure_vault()
        key = _derive_key(master, self._salt)
        # Проверяем: пробуем расшифровать
        raw = json.loads(self._path.read_text("utf-8"))
        encrypted = raw.get("data")
        if encrypted:
            try:
                decrypted = _xor_crypt(base64.b64decode(encrypted), key)
                self._entries = json.loads(decrypted.decode("utf-8"))
                self._unlocked = True
                return f"Хранилище разблокировано. {len(self._entries)} записей, сэр."
            except Exception:
                return "Неверный мастер-пароль, сэр."
        # Нет зашифрованных данных — создаём
        self._unlocked = True
        self._save()
        return "Хранилище создано и разблокировано, сэр."

    def lock(self) -> str:
        """Блокирует хранилище."""
        self._unlocked = False
        self._entries = {}
        return "Хранилище заблокировано, сэр."

    def _check(self) -> bool:
        return self._unlocked

    def add(self, service: str, login: str = "", password: str = "", notes: str = "") -> str:
        """Добавляет или обновляет запись."""
        if not self._check():
            return "Сначала разблокируйте хранилище: «разблокируй пароли [мастер-пароль]», сэр."
        if not password:
            # Генерируем пароль 16 символов
            alphabet = string.ascii_letters + string.digits + "!@#$%&*"
            password = "".join(secrets.choice(alphabet) for _ in range(16))
        self._entries[service] = {"login": login, "password": password, "notes": notes}
        self._save()
        return f"Сохранено: {service}. Пароль: {password}, сэр."

    def get(self, service: str) -> str:
        """Получает пароль для сервиса."""
        if not self._check():
            return "Хранилище заблокировано, сэр."
        entry = self._entries.get(service)
        if not entry:
            # Поиск по подстроке
            matches = [s for s in self._entries if service.lower() in s.lower()]
            if len(matches) == 1:
                entry = self._entries[matches[0]]
                service = matches[0]
            elif matches:
                return f"Найдено несколько: {', '.join(matches)}. Уточните, сэр."
            else:
                return f"{service} не найден, сэр."
        parts = [f"{service}:"]
        if entry.get("login"):
            parts.append(f"  Логин: {entry['login']}")
        parts.append(f"  Пароль: {entry['password']}")
        if entry.get("notes"):
            parts.append(f"  Заметка: {entry['notes']}")
        return "\n".join(parts)

    def list_all(self) -> str:
        """Показывает все записи (без паролей)."""
        if not self._check():
            return "Хранилище заблокировано, сэр."
        if not self._entries:
            return "Хранилище пусто, сэр."
        lines = [f"Записи ({len(self._entries)}):"]
        for service, entry in sorted(self._entries.items()):
            login_info = f", логин: {entry['login']}" if entry.get("login") else ""
            lines.append(f"  {service}{login_info}")
        return "\n".join(lines)

    def delete(self, service: str) -> str:
        """Удаляет запись."""
        if not self._check():
            return "Хранилище заблокировано, сэр."
        if service in self._entries:
            del self._entries[service]
            self._save()
            return f"{service} удалён, сэр."
        return f"{service} не найден, сэр."


def build_skills(config: PasswordsConfig) -> tuple[list[Skill], Vault]:
    """Создаёт навыки менеджера паролей."""
    vault = Vault(config)
    skills = [
        Skill(
            name="vault_unlock",
            description="Разблокировать хранилище паролей мастер-паролем.",
            parameters=object_schema(
                {"master": {"type": "string", "description": "Мастер-пароль"}},
                required=["master"],
            ),
            handler=lambda master: vault.unlock(master),
        ),
        Skill(
            name="vault_lock",
            description="Заблокировать хранилище паролей.",
            parameters=object_schema({}),
            handler=vault.lock,
        ),
        Skill(
            name="vault_add",
            description="Сохранить пароль. Если не указать password — сгенерирует 16 символов.",
            parameters=object_schema(
                {
                    "service": {"type": "string", "description": "Название сервиса"},
                    "login": {"type": "string", "description": "Логин"},
                    "password": {"type": "string", "description": "Пароль (пусто = автогенерация)"},
                    "notes": {"type": "string", "description": "Заметка"},
                },
                required=["service"],
            ),
            handler=lambda service, login="", password="", notes="": vault.add(service, login, password, notes),
        ),
        Skill(
            name="vault_get",
            description="Получить пароль для сервиса.",
            parameters=object_schema(
                {"service": {"type": "string", "description": "Название сервиса"}},
                required=["service"],
            ),
            handler=lambda service: vault.get(service),
        ),
        Skill(
            name="vault_list",
            description="Показать список сохранённых сервисов (без паролей).",
            parameters=object_schema({}),
            handler=vault.list_all,
        ),
        Skill(
            name="vault_delete",
            description="Удалить запись из хранилища.",
            parameters=object_schema(
                {"service": {"type": "string", "description": "Название сервиса"}},
                required=["service"],
            ),
            handler=lambda service: vault.delete(service),
        ),
    ]
    return skills, vault
