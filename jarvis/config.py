"""Конфигурация Джарвиса: загрузка YAML + переменных окружения."""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from dataclasses import MISSING, dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any, TypeVar, get_type_hints

import yaml

log = logging.getLogger(__name__)

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
class MonitorConfig:
    """Проактивный мониторинг состояния компьютера."""

    enabled: bool = True
    interval_s: float = 60.0
    # Ассистент сообщает о проблеме не чаще, чем раз в этот период.
    repeat_after_s: float = 900.0
    battery_low: int = 20
    battery_critical: int = 10
    memory_high: int = 90
    disk_high: int = 92
    cpu_high: int = 95
    # Сколько подряд замеров CPU должны превысить порог, чтобы это был не всплеск.
    cpu_samples: int = 3


@dataclass
class VisionConfig:
    """«Зрение»: OCR и анализ экрана мультимодальной моделью."""

    enabled: bool = True
    # auto повторяет brain.backend; иначе ollama | openai
    backend: str = "auto"
    ollama_model: str = "llava:7b"
    openai_model: str = "gpt-4o-mini"
    # Языки Tesseract, например "rus+eng".
    ocr_languages: str = "rus+eng"
    # Путь к tesseract.exe, если он не в PATH.
    tesseract_cmd: str = ""
    max_side_px: int = 1600


@dataclass
class MemoryConfig:
    """Долговременная память с семантическим поиском."""

    enabled: bool = True
    # auto: ChromaDB, если установлена, иначе локальный JSON-индекс.
    backend: str = "auto"
    path: str = str(Path.home() / ".jarvis" / "memory")
    top_k: int = 3


@dataclass
class BrowserConfig:
    """Автоматизация браузера через Playwright."""

    enabled: bool = True
    engine: str = "chromium"
    headless: bool = False
    # Профиль сохраняется, поэтому логины переживают перезапуск.
    user_data_dir: str = str(Path.home() / ".jarvis" / "browser")
    timeout_ms: int = 15000
    max_text_chars: int = 2000


@dataclass
class SpotifyConfig:
    """Управление Spotify через Web API (spotipy)."""

    enabled: bool = False
    # Ключи берём из окружения: SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET.
    redirect_uri: str = "http://127.0.0.1:8888/callback"
    cache_path: str = str(Path.home() / ".jarvis" / "spotify.json")
    # Запускать приложение Spotify, если нет активного устройства.
    launch_app: bool = True


@dataclass
class WeatherConfig:
    """Настройки погоды: wttr.in (без ключа) или OpenWeatherMap."""

    enabled: bool = True
    default_city: str = "Москва"
    api_key: str = ""  # OpenWeatherMap API ключ (необязательно)


@dataclass
class CalendarConfig:
    """Настройки локального календаря через ICS файлы."""

    enabled: bool = True
    ics_dir: str = str(Path.home() / ".jarvis" / "calendar")


@dataclass
class GitHubConfig:
    """GitHub интеграция через REST API."""

    enabled: bool = True
    token: str = ""  # GITHUB_TOKEN из окружения или прямой
    default_repo: str = ""  # owner/repo по умолчанию


@dataclass
class VpnConfig:
    """VPN: WireGuard и OpenVPN."""

    enabled: bool = False
    backend: str = "auto"  # auto | wireguard | openvpn
    default_config: str = ""  # имя конфигурации по умолчанию
    ovpn_dir: str = ""  # директория с .ovpn файлами


@dataclass
class SoundsConfig:
    """Звуковые эффекты при событиях."""

    enabled: bool = False
    sounds_dir: str = str(Path.home() / ".jarvis" / "sounds")
    custom_sounds: dict[str, str] = field(default_factory=dict)


@dataclass
class PomodoroConfig:
    """Помодоро-таймер."""

    enabled: bool = True
    work_min: int = 25
    break_min: int = 5
    long_break_min: int = 15
    stats_file: str = str(Path.home() / ".jarvis" / "pomodoro_stats.json")


@dataclass
class NewsConfig:
    """RSS / Новости."""

    enabled: bool = True
    feeds: list[dict[str, str]] = field(default_factory=list)  # [{name, url}]


@dataclass
class CurrencyConfig:
    """Конвертер валют."""

    enabled: bool = True


@dataclass
class HomeAssistantConfig:
    """Home Assistant умный дом."""

    enabled: bool = False
    url: str = "http://homeassistant.local:8123"
    token: str = ""  # Long-lived access token


@dataclass
class TelegramConfig:
    """Telegram бот."""

    enabled: bool = False
    bot_token: str = ""  # от @BotFather
    chat_id: str = ""  # ID чата или группы


@dataclass
class AlarmConfig:
    """Будильники."""

    enabled: bool = True
    snooze_min: int = 5


@dataclass
class FilesConfig:
    """Файловый менеджер."""

    enabled: bool = True
    home_dir: str = str(Path.home())
    max_search_results: int = 20


@dataclass
class YouTubeConfig:
    """YouTube Music через yt-dlp + MPV."""

    enabled: bool = True
    audio_only: bool = True
    volume: int = 100


@dataclass
class FaceConfig:
    """Распознавание лиц через OpenCV."""

    enabled: bool = False
    camera_index: int = 0
    photo_dir: str = str(Path.home() / "Pictures" / "Jarvis")


@dataclass
class SkillsConfig:
    """Настройки навыков."""

    allow_shutdown: bool = False
    screenshot_dir: str = str(Path.home() / "Pictures" / "Jarvis")
    notes_file: str = str(Path.home() / ".jarvis" / "notes.md")
    search_engine: str = "https://duckduckgo.com/?q={query}"
    apps: dict[str, str] = field(default_factory=dict)
    # Алиасы: короткая фраза -> подсказка для LLM
    # Например: "тихо" -> "установи громкость на 20 процентов"
    aliases: dict[str, str] = field(default_factory=dict)
    vision: VisionConfig = field(default_factory=VisionConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    browser: BrowserConfig = field(default_factory=BrowserConfig)
    spotify: SpotifyConfig = field(default_factory=SpotifyConfig)
    weather: WeatherConfig = field(default_factory=WeatherConfig)
    calendar: CalendarConfig = field(default_factory=CalendarConfig)
    files: FilesConfig = field(default_factory=FilesConfig)
    youtube: YouTubeConfig = field(default_factory=YouTubeConfig)
    face: FaceConfig = field(default_factory=FaceConfig)
    github: GitHubConfig = field(default_factory=GitHubConfig)
    vpn: VpnConfig = field(default_factory=VpnConfig)
    sounds: SoundsConfig = field(default_factory=SoundsConfig)
    pomodoro: PomodoroConfig = field(default_factory=PomodoroConfig)
    news: NewsConfig = field(default_factory=NewsConfig)
    currency: CurrencyConfig = field(default_factory=CurrencyConfig)
    homeassistant: HomeAssistantConfig = field(default_factory=HomeAssistantConfig)
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    alarm: AlarmConfig = field(default_factory=AlarmConfig)


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
    monitor: MonitorConfig = field(default_factory=MonitorConfig)
    skills: SkillsConfig = field(default_factory=SkillsConfig)
    aliases: dict[str, str] = field(default_factory=lambda: {
        # Алиасы верхнего уровня (если не заданы в skills.aliases)
    })

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


# Правила валидации: (имя_поля, тип_или_кортеж_типов, мин, макс).
# None означает «не проверять».
_VALIDATION_RULES: dict[str, tuple[type | tuple[type, ...] | None, Any, Any]] = {
    # MicConfig
    "sample_rate": (int, 8000, 48000),
    "frame_ms": (int, 10, 100),
    "vad_aggressiveness": (int, 0, 3),
    "silence_ms": (int, 100, 5000),
    "max_utterance_s": ((int, float), 1.0, 120.0),
    "preroll_ms": (int, 0, 2000),
    # TtsConfig
    "rate": (int, 50, 450),
    "volume": ((int, float), 0.0, 1.0),
    # WakeWordConfig
    "threshold": ((int, float), 0.1, 1.0),
    # BrainConfig
    "temperature": ((int, float), 0.0, 2.0),
    "max_history": (int, 2, 100),
    "max_tool_iterations": (int, 1, 20),
    # UiConfig
    "opacity": ((int, float), 0.1, 1.0),
    "width": (int, 100, 2000),
    "height": (int, 80, 1000),
    # MonitorConfig
    "interval_s": ((int, float), 5.0, 3600.0),
    "repeat_after_s": ((int, float), 10.0, 86400.0),
    "battery_low": (int, 5, 95),
    "battery_critical": (int, 1, 50),
    "memory_high": (int, 50, 99),
    "disk_high": (int, 50, 99),
    "cpu_high": (int, 50, 100),
    "cpu_samples": (int, 1, 30),
    # VisionConfig
    "max_side_px": (int, 200, 7680),
    # MemoryConfig
    "top_k": (int, 1, 50),
    # BrowserConfig
    "timeout_ms": (int, 1000, 120000),
    "max_text_chars": (int, 100, 100000),
}


def _sanitize(cls: type[Any], data: Mapping[str, Any], prefix: str = "") -> dict[str, Any]:
    """Проверяет типы и диапазоны, возвращая исправленную копию данных."""
    hints = get_type_hints(cls)
    out: dict[str, Any] = dict(data)  # mutable copy
    for f in fields(cls):  # type: ignore[arg-type]
        if f.name not in out:
            continue
        value = out[f.name]
        full_name = f"{prefix}{f.name}"
        hint = hints.get(f.name)

        # Рекурсивная обработка вложенных dataclass.
        if is_dataclass(hint) and isinstance(value, Mapping):
            out[f.name] = _sanitize(hint, value, full_name + ".")  # type: ignore[arg-type]
            continue

        rule = _VALIDATION_RULES.get(f.name)
        if rule is None:
            continue
        expected_types, min_val, max_val = rule

        # Проверка типа: при несоответствии — сбрасываем в default.
        if expected_types is not None and not isinstance(value, expected_types):
            log.warning(
                "Конфиг %s: ожидается %s, получено %s (%r). Берётся значение по умолчанию.",
                full_name,
                expected_types,
                type(value).__name__,
                value,
            )
            if f.default is not MISSING:
                out[f.name] = f.default
            elif f.default_factory is not MISSING:
                out[f.name] = f.default_factory()
            continue

        # Проверка диапазона: clamp к [min, max].
        if min_val is not None and value < min_val:
            log.warning(
                "Конфиг %s: значение %r меньше минимума %s. Исправляю на %s.",
                full_name,
                value,
                min_val,
                min_val,
            )
            out[f.name] = min_val
        if max_val is not None and value > max_val:
            log.warning(
                "Конфиг %s: значение %r больше максимума %s. Исправляю на %s.",
                full_name,
                value,
                max_val,
                max_val,
            )
            out[f.name] = max_val
    return out


def load_config(path: str | os.PathLike[str] | None = None) -> Config:
    """Загружает конфигурацию из YAML-файла, возвращая значения по умолчанию."""
    candidates = [Path(path)] if path else list(DEFAULT_CONFIG_PATHS)
    for candidate in candidates:
        if candidate.is_file():
            raw = yaml.safe_load(candidate.read_text(encoding="utf-8")) or {}
            if not isinstance(raw, Mapping):
                raise ValueError(f"Некорректный конфиг: {candidate}")
            sanitized = _sanitize(Config, raw)
            return _build(Config, sanitized)
    return Config()
