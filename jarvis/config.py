"""Конфигурация Джарвиса: загрузка YAML + переменных окружения."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any, TypeVar, get_type_hints

import yaml

DEFAULT_CONFIG_PATHS = (
    Path("config.yaml"),
    Path.home() / ".jarvis" / "config.yaml",
)

T = TypeVar("T")


@dataclass
class WakeWordConfig:
    """Настройки пробуждения по ключевому слову."""

    enabled: bool = True
    # Модель openWakeWord: "hey_jarvis" поставляется предобученной.
    model: str = "hey_jarvis"
    threshold: float = 0.5
    # Резервный режим: если openWakeWord недоступен, ищем эти слова в тексте.
    fallback_phrases: list[str] = field(default_factory=lambda: ["джарвис", "jarvis", "джарвиc"])


@dataclass
class SttConfig:
    """Настройки распознавания речи (faster-whisper)."""

    model: str = "small"
    language: str = "ru"
    device: str = "auto"
    compute_type: str = "int8"
    beam_size: int = 1


@dataclass
class TtsConfig:
    """Настройки синтеза речи."""

    # sapi5 - офлайн голос Windows; edge - облачный neural-голос Microsoft.
    engine: str = "sapi5"
    voice: str = ""
    edge_voice: str = "ru-RU-DmitryNeural"
    rate: int = 190
    volume: float = 1.0


@dataclass
class MicConfig:
    """Настройки микрофона и детектора речи."""

    device: int | None = None
    sample_rate: int = 16000
    frame_ms: int = 30
    vad_aggressiveness: int = 2
    silence_ms: int = 800
    max_utterance_s: float = 15.0
    preroll_ms: int = 300


@dataclass
class BrainConfig:
    """Выбор и параметры LLM-бэкенда."""

    # openai | ollama | offline
    backend: str = "ollama"
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str = ""
    ollama_model: str = "qwen2.5:7b-instruct"
    ollama_host: str = "http://127.0.0.1:11434"
    temperature: float = 0.4
    max_history: int = 20
    max_tool_iterations: int = 5
    system_prompt: str = (
        "Ты — Джарвис, персональный ИИ-ассистент из фильмов про Тони Старка. "
        "Отвечай по-русски, кратко, точно и с лёгкой британской иронией, "
        "обращайся к пользователю «сэр». Ответ произносится вслух, поэтому "
        "избегай markdown, списков и длинных перечислений. "
        "Для действий на компьютере всегда вызывай доступные инструменты, "
        "а не выдумывай результат."
    )


@dataclass
class UiConfig:
    """Настройки HUD-оверлея."""

    enabled: bool = True
    opacity: float = 0.85
    accent: str = "#3fd0ff"
    corner: str = "bottom-right"
    width: int = 380
    height: int = 220


@dataclass
class SkillsConfig:
    """Настройки навыков."""

    allow_shutdown: bool = False
    screenshot_dir: str = str(Path.home() / "Pictures" / "Jarvis")
    notes_file: str = str(Path.home() / ".jarvis" / "notes.md")
    search_engine: str = "https://duckduckgo.com/?q={query}"
    apps: dict[str, str] = field(default_factory=dict)


@dataclass
class Config:
    """Корневая конфигурация приложения."""

    hotkey: str = "ctrl+alt+j"
    greeting: str = "Все системы в норме, сэр."
    log_level: str = "INFO"
    wake_word: WakeWordConfig = field(default_factory=WakeWordConfig)
    stt: SttConfig = field(default_factory=SttConfig)
    tts: TtsConfig = field(default_factory=TtsConfig)
    mic: MicConfig = field(default_factory=MicConfig)
    brain: BrainConfig = field(default_factory=BrainConfig)
    ui: UiConfig = field(default_factory=UiConfig)
    skills: SkillsConfig = field(default_factory=SkillsConfig)

    @property
    def openai_api_key(self) -> str:
        """Ключ OpenAI берём только из окружения, чтобы не хранить в конфиге."""
        return os.environ.get("OPENAI_API_KEY", "")


def _build(cls: type[T], data: Mapping[str, Any]) -> T:
    """Рекурсивно собирает dataclass из словаря, игнорируя лишние ключи."""
    hints = get_type_hints(cls)
    kwargs: dict[str, Any] = {}
    for f in fields(cls):  # type: ignore[arg-type]
        if f.name not in data:
            continue
        value = data[f.name]
        hint = hints.get(f.name)
        if is_dataclass(hint) and isinstance(value, Mapping):
            kwargs[f.name] = _build(hint, value)  # type: ignore[arg-type]
        else:
            kwargs[f.name] = value
    return cls(**kwargs)


def load_config(path: str | os.PathLike[str] | None = None) -> Config:
    """Загружает конфигурацию из YAML-файла, возвращая значения по умолчанию."""
    candidates = [Path(path)] if path else list(DEFAULT_CONFIG_PATHS)
    for candidate in candidates:
        if candidate.is_file():
            raw = yaml.safe_load(candidate.read_text(encoding="utf-8")) or {}
            if not isinstance(raw, Mapping):
                raise ValueError(f"Некорректный конфиг: {candidate}")
            return _build(Config, raw)
    return Config()
