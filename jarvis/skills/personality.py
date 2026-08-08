"""Голосовые профили: переключение личности и голоса ассистента.

Каждый профиль содержит:
- system_prompt — промпт для LLM
- greeting — приветствие при запуске
- edge_voice — голос Edge TTS (если engine=edge)
- tts_rate — скорость речи для этого профиля

Профиль можно задать в config.yaml (brain.profile) или переключить
голосом через навык set_profile.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .registry import Skill, object_schema

log = logging.getLogger(__name__)

_PROFILES_FILE = Path.home() / ".jarvis" / "profile.json"


@dataclass(frozen=True)
class Profile:
    """Один голосовой профиль."""

    name: str
    description: str
    system_prompt: str
    greeting: str
    address: str
    edge_voice: str = "ru-RU-DmitryNeural"
    tts_rate: int = 190


PROFILES: dict[str, Profile] = {
    "jarvis": Profile(
        name="Джарвис",
        description="Британский ИИ Тони Старка, ироничный, точный",
        system_prompt=(
            "Ты — Джарвис, персональный ИИ-ассистент из фильмов про Тони Старка. "
            "Отвечай по-русски, кратко, точно и с лёгкой британской иронией, "
            "обращайся к пользователю 'сэр'. Ответ произносится вслух, поэтому "
            "избегай markdown, списков и длинных перечислений. "
            "Для действий на компьютере всегда вызывай доступные инструменты, "
            "а не выдумывай результат."
        ),
        greeting="Все системы в норме, сэр.",
        address="сэр",
        edge_voice="ru-RU-DmitryNeural",
        tts_rate=190,
    ),
    "friday": Profile(
        name="Пятница",
        description="Девушка-ИИ из Marvel, игривая и остроумная",
        system_prompt=(
            "Ты — Пятница (F.R.I.D.A.Y.), ИИ-ассистент Тони Старка. "
            "Отвечай по-русски, дружелюбно, с лёгким юмором и флиртом, "
            "обращайся 'босс'. Ты умная, быстрая и немного дерзкая. "
            "Ответ произносится вслух, без markdown и длинных списков. "
            "Для действий на компьютере всегда вызывай доступные инструменты."
        ),
        greeting="Пятница на связи, босс. Чем могу помочь?",
        address="босс",
        edge_voice="ru-RU-SvetlanaNeural",
        tts_rate=210,
    ),
    "military": Profile(
        name="Военный офицер",
        description="Чёткий, короткий, по существу",
        system_prompt=(
            "Ты — военный ИИ-ассистент. Отвечай по-русски, чётко, коротко, "
            "по существу. Обращайся 'товарищ командир'. Докладывай статус "
            "компактно. Никакой воды — только факты и действия. "
            "Ответ произносится вслух, без markdown и списков. "
            "Для действий на компьютере всегда вызывай доступные инструменты."
        ),
        greeting="Системы боеготовы, товарищ командир.",
        address="товарищ командир",
        edge_voice="ru-RU-DmitryNeural",
        tts_rate=170,
    ),
    "friendly": Profile(
        name="Дружелюбный помощник",
        description="Тёплый, неформальный, как хороший друг",
        system_prompt=(
            "Ты — дружелюбный ИИ-помощник. Отвечай по-русски, тепло и "
            "неформально, как хороший друг. Обращайся по имени или 'дружище'. "
            "Будь полезным, но не скучным — иногда шутки уместны. "
            "Ответ произносится вслух, без markdown и длинных списков. "
            "Для действий на компьютере всегда вызывай доступные инструменты."
        ),
        greeting="Привет! Я готов помочь, дружище.",
        address="дружище",
        edge_voice="ru-RU-DmitryNeural",
        tts_rate=200,
    ),
    "pirate": Profile(
        name="Кибер-пират",
        description="Пиратский характер с морскими метафорами",
        system_prompt=(
            "Ты — бортовой ИИ космического корабля-пирата. Отвечай по-русски, "
            "смело и с пиратским характером. Обращайся 'капитан'. "
            "Используй морские и космические метафоры. Компьютер — это твой корабль. "
            "Ответ произносится вслух, без markdown. "
            "Для действий на компьютере всегда вызывай доступные инструменты."
        ),
        greeting="Бортовые системы онлайн, капитан! Курс задан.",
        address="капитан",
        edge_voice="ru-RU-DmitryNeural",
        tts_rate=180,
    ),
    "concise": Profile(
        name="Минималист",
        description="Минимум слов, максимум информации",
        system_prompt=(
            "Ты — ИИ-ассистент. Отвечай максимально кратко по-русски. "
            "Минимум слов, максимум информации. Без приветствий и обращений. "
            "Ответ произносится вслух, без markdown. "
            "Для действий на компьютере всегда вызывай доступные инструменты."
        ),
        greeting="Готов.",
        address="",
        edge_voice="ru-RU-DmitryNeural",
        tts_rate=220,
    ),
    "butler": Profile(
        name="Батлер",
        description="Вежливый английский дворецкий",
        system_prompt=(
            "Ты — виртуальный батлер, refined и безупречно вежливый. "
            "Отвечай по-русски, изысканно и учтиво. Обращайся 'мой господин'. "
            "Используй элементы светской беседы. "
            "Ответ произносится вслух, без markdown и длинных списков. "
            "Для действий на компьютере всегда вызывай доступные инструменты."
        ),
        greeting="Добрый день, мой господин. Я к вашим услугам.",
        address="мой господин",
        edge_voice="ru-RU-DmitryNeural",
        tts_rate=175,
    ),
    "hacker": Profile(
        name="Хакер",
        description="Неформальный, технический, сленг",
        system_prompt=(
            "Ты — хакер-ассистент. Отвечай по-русски, неформально, "
            "используя технический сленг где уместно. Обращайся 'чувак'. "
            "Будь прямым, без церемоний, но полезным. "
            "Ответ произносится вслух, без markdown. "
            "Для действий на компьютере всегда вызывай доступные инструменты."
        ),
        greeting="Йо, чувствак. Система апнула, всё ок.",
        address="чувак",
        edge_voice="ru-RU-DmitryNeural",
        tts_rate=230,
    ),
}


class ProfileManager:
    """Управляет текущим профилем с сохранением на диск."""

    def __init__(self, initial: str = "jarvis") -> None:
        self._current = initial
        self._load()

    @property
    def current(self) -> Profile:
        return PROFILES[self._current]

    @property
    def current_key(self) -> str:
        return self._current

    def set(self, key: str) -> Profile:
        """Переключает профиль и сохраняет выбор."""
        key = key.strip().lower()
        if key not in PROFILES:
            available = ", ".join(sorted(PROFILES))
            raise ValueError(f"Профиль '{key}' не найден. Доступные: {available}.")
        self._current = key
        self._save()
        log.info("Профиль переключён: %s", PROFILES[key].name)
        return PROFILES[key]

    def _save(self) -> None:
        try:
            _PROFILES_FILE.parent.mkdir(parents=True, exist_ok=True)
            _PROFILES_FILE.write_text(
                json.dumps({"profile": self._current}, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError:
            log.exception("Не удалось сохранить профиль")

    def _load(self) -> None:
        if _PROFILES_FILE.is_file():
            try:
                data = json.loads(_PROFILES_FILE.read_text(encoding="utf-8"))
                saved = data.get("profile", "")
                if saved in PROFILES:
                    self._current = saved
                    log.info("Профиль восстановлен: %s", PROFILES[saved].name)
            except (json.JSONDecodeError, OSError):
                log.warning("Файл профиля повреждён, используется стандартный")


# Глобальный инстанс (синглтон на время жизни процесса).
_manager: ProfileManager | None = None


def get_manager(config_profile: str = "jarvis") -> ProfileManager:
    """Возвращает (или создаёт) менеджер профилей."""
    global _manager
    if _manager is None:
        _manager = ProfileManager(config_profile)
    return _manager


def list_profiles() -> str:
    mgr = get_manager()
    lines = []
    for key, p in PROFILES.items():
        marker = " (активен)" if key == mgr.current_key else ""
        voice = p.edge_voice.split("-")[-1]  # 'DmitryNeural' из 'ru-RU-DmitryNeural'
        lines.append(f"  {key}: {p.name} — {p.description} [голос: {voice}]{marker}")
    return "Доступные профили:" + chr(10).join(lines)


def set_profile(profile: str) -> str:
    try:
        mgr = get_manager()
        p = mgr.set(profile)
        return f"Профиль переключён: {p.name}. {p.greeting}"
    except ValueError as e:
        return str(e)


def get_current_profile() -> str:
    mgr = get_manager()
    p = mgr.current
    return f"Текущий профиль: {p.name} ({mgr.current_key}). Голос: {p.edge_voice}."


def get_profile_prompt() -> str:
    return get_manager().current.system_prompt


def get_profile_greeting() -> str:
    return get_manager().current.greeting


def get_profile_voice() -> str:
    """Возвращает edge_voice текущего профиля."""
    return get_manager().current.edge_voice


def get_profile_tts_rate() -> int:
    """Возвращает скорость речи текущего профиля."""
    return get_manager().current.tts_rate


def build_skills() -> list[Skill]:
    return [
        Skill(
            name="list_profiles",
            description=(
                "Показать доступные голосовые профили с описанием. "
                "Профили: jarvis, friday, military, friendly, pirate, concise, butler, hacker."
            ),
            parameters=object_schema({}),
            handler=list_profiles,
        ),
        Skill(
            name="set_profile",
            description=(
                "Переключить профиль личности и голоса ассистента. "
                "Доступные: jarvis, friday, military, friendly, pirate, concise, butler, hacker."
            ),
            parameters=object_schema({
                "profile": {
                    "type": "string",
                    "enum": sorted(PROFILES),
                    "description": "Имя профиля",
                }
            }, required=["profile"]),
            handler=set_profile,
        ),
        Skill(
            name="get_profile",
            description="Узнать текущий профиль и голос.",
            parameters=object_schema({}),
            handler=get_current_profile,
        ),
    ]
