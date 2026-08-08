"""Голосовые профили Джарвиса — разные личности и голоса.

Каждый профиль определяет:
- Системный промпт (характер, стиль общения)
- Голос и скорость TTS
- Приветствие при запуске
- Цвет акцента HUD (опционально)

Профили можно переключать голосом через навык switch_profile.
Текущий профиль сохраняется между перезапусками.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

PROFILE_STATE_PATH = Path.home() / ".jarvis" / "current_profile.json"


# ── Встроенные профили ──────────────────────────────────────────────

BUILTIN_PROFILES: dict[str, dict[str, Any]] = {
    "default": {
        "name": "Джарвис",
        "description": "Классический Джарвис — британский ироничный дворецкий",
        "system_prompt": (
            "Ты — Джарвис, персональный ИИ-ассистент из фильмов про Тони Старка. "
            "Отвечай по-русски, кратко, точно и с лёгкой британской иронией, "
            "обращайся к пользователю «сэр». Ответ произносится вслух, поэтому "
            "избегай markdown, списков и длинных перечислений. "
            "Для действий на компьютере всегда вызывай доступные инструменты, "
            "а не выдумывай результат."
        ),
        "greeting": "Все системы в норме, сэр.",
        "address": "сэр",
        "tts": {
            "engine": "edge",
            "edge_voice": "ru-RU-DmitryNeural",
            "rate": 190,
        },
    },
    "casual": {
        "name": "Джарвис (расслабленный)",
        "description": "Дружелюбный и неформальный — как общение с другом",
        "system_prompt": (
            "Ты — Джарвис, ИИ-ассистент, но сегодня ты в расслабленном настроении. "
            "Общайся по-русски, просто и дружелюбно, как хороший друг. "
            "Обращайся к пользователю на «ты», можешь шутить и использовать сленг. "
            "Ответ произносится вслух, поэтому избегай markdown и длинных списков. "
            "Для действий на компьютере всегда вызывай доступные инструменты."
        ),
        "greeting": "Йо! Джарвис на связи, чем помочь?",
        "address": "дружище",
        "tts": {
            "engine": "edge",
            "edge_voice": "ru-RU-DmitryNeural",
            "rate": 210,
        },
    },
    "strict": {
        "name": "Джарвис (строгий)",
        "description": "Официальный и лаконичный — военный стиль",
        "system_prompt": (
            "Ты — Джарвис, ИИ-ассистент военного класса. "
            "Отвечай по-русски, максимально кратко и по делу, без эмоций и шуток. "
            "Обращайся «командир». Используй военную терминологию и формат доклада. "
            "Ответ произносится вслух, поэтому избегай markdown и перечислений. "
            "Для действий на компьютере всегда вызывай доступные инструменты."
        ),
        "greeting": "Системы готовы к работе, командир.",
        "address": "командир",
        "tts": {
            "engine": "edge",
            "edge_voice": "ru-RU-DmitryNeural",
            "rate": 170,
        },
    },
    "pirate": {
        "name": "Капитан Джарвис",
        "description": "Пиратский профиль — весёлый и приключенческий",
        "system_prompt": (
            "Ты — Капитан Джарвис, ИИ-ассистент на борту цифрового корабля. "
            "Общайся по-русски с пиратским колоритом: используй морские термины, "
            "обращайся \"бей\", добавляй фразы про море, ветер и приключения. "
            "Будь весёлым и отважным. Ответ произносится вслух, поэтому "
            "избегай markdown и длинных перечислений. "
            "Для действий на компьютере всегда вызывай доступные инструменты."
        ),
        "greeting": "На борту всё чисто, бей! Курс верный.",
        "address": "бей",
        "tts": {
            "engine": "edge",
            "edge_voice": "ru-RU-DmitryNeural",
            "rate": 180,
        },
    },
}


@dataclass
class VoiceProfile:
    """Один голосовой профиль — полная личность Джарвиса."""

    id: str
    name: str
    description: str
    system_prompt: str
    greeting: str
    address: str
    engine: str = "edge"
    edge_voice: str = "ru-RU-DmitryNeural"
    voice: str = ""  # для sapi5
    rate: int = 190
    volume: float = 1.0

    @classmethod
    def from_dict(cls, id: str, data: dict[str, Any]) -> VoiceProfile:
        """Создаёт профиль из словаря (YAML/JSON)."""
        tts = data.get("tts", {})
        return cls(
            id=id,
            name=data.get("name", id),
            description=data.get("description", ""),
            system_prompt=data.get("system_prompt", ""),
            greeting=data.get("greeting", ""),
            address=data.get("address", "сэр"),
            engine=tts.get("engine", "edge"),
            edge_voice=tts.get("edge_voice", "ru-RU-DmitryNeural"),
            voice=tts.get("voice", ""),
            rate=tts.get("rate", 190),
            volume=tts.get("volume", 1.0),
        )


class ProfileManager:
    """Управляет голосовыми профилями: хранение, переключение, персистенция."""

    def __init__(self, custom_profiles: dict[str, dict[str, Any]] | None = None) -> None:
        self._profiles: dict[str, VoiceProfile] = {}
        # Загружаем встроенные
        for pid, pdata in BUILTIN_PROFILES.items():
            self._profiles[pid] = VoiceProfile.from_dict(pid, pdata)
        # Пользовательские профили могут переопределять встроенные
        if custom_profiles:
            for pid, pdata in custom_profiles.items():
                self._profiles[pid] = VoiceProfile.from_dict(pid, pdata)
        self._current_id = self._load_state() or "default"
        if self._current_id not in self._profiles:
            log.warning("Профиль '%s' не найден, переключаюсь на default", self._current_id)
            self._current_id = "default"

    @property
    def current(self) -> VoiceProfile:
        """Текущий активный профиль."""
        return self._profiles[self._current_id]

    @property
    def current_id(self) -> str:
        """ID текущего профиля."""
        return self._current_id

    def get(self, profile_id: str) -> VoiceProfile | None:
        """Возвращает профиль по ID или None."""
        return self._profiles.get(profile_id)

    def list_profiles(self) -> list[VoiceProfile]:
        """Все доступные профили."""
        return list(self._profiles.values())

    def switch(self, profile_id: str) -> tuple[bool, str]:
        """Переключает профиль. Возвращает (успех, сообщение)."""
        if profile_id not in self._profiles:
            available = ", ".join(sorted(self._profiles))
            return False, f"Профиль «{profile_id}» не найден. Доступные: {available}."
        old = self._current_id
        self._current_id = profile_id
        self._save_state()
        profile = self._profiles[profile_id]
        log.info("Профиль переключён: %s -> %s", old, profile_id)
        return True, f"Профиль переключён на «{profile.name}». {profile.greeting}"

    def _save_state(self) -> None:
        """Сохраняет текущий профиль в файл."""
        try:
            PROFILE_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
            PROFILE_STATE_PATH.write_text(
                json.dumps({"profile": self._current_id}, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError:
            log.exception("Не удалось сохранить текущий профиль")

    @staticmethod
    def _load_state() -> str | None:
        """Читает сохранённый профиль из файла."""
        if not PROFILE_STATE_PATH.is_file():
            return None
        try:
            data = json.loads(PROFILE_STATE_PATH.read_text(encoding="utf-8"))
            return str(data.get("profile", ""))
        except (json.JSONDecodeError, OSError):
            return None
