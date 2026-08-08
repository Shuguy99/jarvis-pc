"""Конфигурация Джарвиса: загрузка YAML + переменные окружения.

Особенности:
- Пути с ~ автоматически разворачиваются (expanduser)
- Неизвестные ключи в YAML логгятся как предупреждения
- Поддержка переменных окружения: ${VAR} подставляется из os.environ
- ``python -m jarvis config init`` создаёт config.yaml из шаблона
"""

from __future__ import annotations

import logging
import os
import re
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import MISSING, dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any, TypeVar, get_type_hints

import yaml

log = logging.getLogger(__name__)

DEFAULT_CONFIG_PATHS = (
    Path.home() / ".jarvis" / "config.yaml",
    Path("config.yaml"),
)

T = TypeVar("T")

# Поля-пути: имена, оканчивающиеся на эти суффиксы, авто-раскрывают ~.
_PATH_SUFFIXES = ("_dir", "_file", "_path", "_db", "_cmd", "cache_path", "path")
# Поля-URL: не трогаем expanduser.
_URL_FIELDS = {"url", "api_base", "ollama_host", "openai_base_url", "sd_url", "redirect_uri", "search_engine"}

# Паттерн ${ENV_VAR} — подстановка переменных окружения.
_ENV_RE = re.compile(r"\$\{([^}]+)\}")


# ── Dataclass-ы конфигурации ─────────────────────────────────────────


@dataclass
class WakeWordConfig:
    """Настройки пробуждения по ключевому слову."""

    enabled: bool = True
    model: str = "hey_jarvis"
    threshold: float = 0.5
    fallback_phrases: list[str] = field(default_factory=lambda: ["джарвис", "jarvis", "джарвиc"])


@dataclass
class SttConfig:
    """Настройки распознавания речи (faster-whisper)."""

    model: str = "small"           # tiny | base | small | medium | large-v3
    language: str = "ru"
    device: str = "auto"           # auto | cpu | cuda
    compute_type: str = "int8"     # int8 для CPU, float16 для GPU
    beam_size: int = 1


@dataclass
class TtsConfig:
    """Настройки синтеза речи."""

    engine: str = "sapi5"          # sapi5 (офлайн, Windows) | edge (neural, нужен интернет)
    voice: str = ""                # часть имени голоса SAPI, например "Irina"
    edge_voice: str = "ru-RU-DmitryNeural"
    rate: int = 190
    volume: float = 1.0


@dataclass
class MicConfig:
    """Настройки микрофона и детектора речи."""

    device: int | None = None       # индекс из `python -m jarvis devices`
    sample_rate: int = 16000
    frame_ms: int = 30
    vad_aggressiveness: int = 2
    silence_ms: int = 800
    max_utterance_s: float = 15.0
    preroll_ms: int = 300


@dataclass
class BrainConfig:
    """Выбор и параметры LLM-бэкенда."""

    backend: str = "ollama"         # ollama | openai | offline
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str = ""      # для совместимых API (OpenRouter и т.п.)
    ollama_model: str = "qwen2.5:7b-instruct"
    ollama_host: str = "http://127.0.0.1:11434"
    temperature: float = 0.4
    max_history: int = 20
    max_tool_iterations: int = 5
    system_prompt: str = ""
    profile: str = "jarvis"  # jarvis | military | friendly | pirate | concise


@dataclass
class UiConfig:
    """Настройки HUD-оверлея."""

    enabled: bool = True
    opacity: float = 0.85
    accent: str = "#3fd0ff"
    corner: str = "bottom-right"   # top-left | top-right | bottom-left | bottom-right
    width: int = 380
    height: int = 220


@dataclass
class MonitorConfig:
    """Проактивный мониторинг состояния компьютера."""

    enabled: bool = True
    interval_s: float = 60.0
    repeat_after_s: float = 900.0
    battery_low: int = 20
    battery_critical: int = 10
    memory_high: int = 90
    disk_high: int = 92
    cpu_high: int = 95
    cpu_samples: int = 3


@dataclass
class VisionConfig:
    """«Зрение»: OCR и анализ экрана мультимодальной моделью."""

    enabled: bool = True
    backend: str = "auto"           # auto (как brain.backend) | ollama | openai
    ollama_model: str = "llava:7b"
    openai_model: str = "gpt-4o-mini"
    ocr_languages: str = "rus+eng"
    tesseract_cmd: str = ""         # путь к tesseract.exe, если не в PATH
    max_side_px: int = 1600


@dataclass
class MemoryConfig:
    """Долговременная память с семантическим поиском."""

    enabled: bool = True
    backend: str = "auto"           # auto | chroma | json
    path: str = "~/.jarvis/memory"
    top_k: int = 3


@dataclass
class BrowserConfig:
    """Автоматизация браузера через Playwright."""

    enabled: bool = True
    engine: str = "chromium"        # chromium | firefox | webkit
    headless: bool = False
    user_data_dir: str = "~/.jarvis/browser"
    timeout_ms: int = 15000
    max_text_chars: int = 2000


@dataclass
class SpotifyConfig:
    """Управление Spotify через Web API (spotipy)."""

    enabled: bool = False           # нужно SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET
    redirect_uri: str = "http://127.0.0.1:8888/callback"
    cache_path: str = "~/.jarvis/spotify.json"
    launch_app: bool = True


@dataclass
class WeatherConfig:
    """Настройки погоды: wttr.in (без ключа) или OpenWeatherMap."""

    enabled: bool = True
    default_city: str = "Москва"
    api_key: str = ""               # OpenWeatherMap API ключ (необязательно)


@dataclass
class CalendarConfig:
    """Настройки локального календаря через ICS файлы."""

    enabled: bool = True
    ics_dir: str = "~/.jarvis/calendar"


@dataclass
class GitHubConfig:
    """GitHub интеграция через REST API."""

    enabled: bool = True
    token: str = ""                 # GITHUB_TOKEN из окружения или прямой
    default_repo: str = ""          # owner/repo по умолчанию


@dataclass
class VpnConfig:
    """VPN: WireGuard и OpenVPN."""

    enabled: bool = False
    backend: str = "auto"           # auto | wireguard | openvpn
    default_config: str = ""
    ovpn_dir: str = ""


@dataclass
class SoundsConfig:
    """Звуковые эффекты при событиях."""

    enabled: bool = False
    sounds_dir: str = "~/.jarvis/sounds"
    custom_sounds: dict[str, str] = field(default_factory=dict)


@dataclass
class PomodoroConfig:
    """Помодоро-таймер."""

    enabled: bool = True
    work_min: int = 25
    break_min: int = 5
    long_break_min: int = 15
    stats_file: str = "~/.jarvis/pomodoro_stats.json"


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
    token: str = ""                 # Long-lived access token


@dataclass
class TelegramConfig:
    """Telegram бот."""

    enabled: bool = False
    bot_token: str = ""              # от @BotFather
    chat_id: str = ""                # ID чата или группы
    allowed_users: list[str] = field(default_factory=list)  # разрешённые username (пусто = все)
    notify_on_start: bool = True     # уведомление при запуске Джарвиса
    parse_mode: str = "HTML"         # HTML | Markdown | MarkdownV2 | пусто


@dataclass
class AlarmConfig:
    """Будильники."""

    enabled: bool = True
    snooze_min: int = 5


@dataclass
class PasswordsConfig:
    """Менеджер паролей."""

    enabled: bool = False
    vault_file: str = "~/.jarvis/vault.json"


@dataclass
class NotesConfig:
    """Заметки с тегами."""

    enabled: bool = True
    notes_db: str = "~/.jarvis/tagged_notes.json"


@dataclass
class AgendaConfig:
    """Ежедневник."""

    enabled: bool = True
    ics_dir: str = "~/.jarvis/calendar"
    notes_file: str = "~/.jarvis/notes.md"


@dataclass
class HabitsConfig:
    """Трекер привычек."""

    enabled: bool = True
    habits_file: str = "~/.jarvis/habits.json"


@dataclass
class ExpensesConfig:
    """Трекер расходов."""

    enabled: bool = True
    expenses_file: str = "~/.jarvis/expenses.json"


@dataclass
class MusicRecognitionConfig:
    """Распознавание музыки (AudD API)."""

    enabled: bool = False
    api_key: str = ""               # audd.io API token
    record_seconds: int = 5


@dataclass
class QrConfig:
    """QR-коды."""

    enabled: bool = True


@dataclass
class ImageGenConfig:
    """Генерация изображений."""

    enabled: bool = False
    backend: str = "auto"           # auto | openai | stable_diffusion
    model: str = "dall-e-3"
    api_key: str = ""
    api_base: str = ""
    sd_url: str = "http://127.0.0.1:7860"
    sd_steps: int = 20
    size: str = "1024x1024"


@dataclass
class RadioConfig:
    """Интернет-радио."""

    enabled: bool = True


@dataclass
class NetworkConfig:
    """Сетевые утилиты."""

    enabled: bool = True


@dataclass
class WindowsConfig:
    """Менеджер окон."""

    enabled: bool = True


@dataclass
class DiskConfig:
    """Анализ диска."""

    enabled: bool = True


@dataclass
class SysupdateConfig:
    """Обновление системы."""

    enabled: bool = True


@dataclass
class ProcessesConfig:
    """Процесс-менеджер."""

    enabled: bool = True


@dataclass
class FilesConfig:
    """Файловый менеджер."""

    enabled: bool = True
    home_dir: str = "~"
    max_search_results: int = 20


@dataclass
class YouTubeConfig:
    """YouTube Music через yt-dlp + MPV."""

    enabled: bool = True
    audio_only: bool = True
    volume: int = 100


@dataclass
class FaceConfig:
    """Распознавание лиц через face_recognition + OpenCV."""

    enabled: bool = False
    camera_index: int = 0
    photo_dir: str = "~/Pictures/Jarvis"
    tolerance: float = 0.5          # 0.0=строгий, 0.6=мягкий порог распознавания
    auto_greeting: bool = True     # Приветствовать по имени при запуске
    auto_switch_profile: bool = True  # Переключать профиль по лицу


@dataclass
class ProfilesConfig:
    """Голосовые профили — разные личности Джарвиса."""

    enabled: bool = True
    custom: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass
class PluginStoreConfig:
    """Магазин плагинов: поиск и установка из GitHub."""

    enabled: bool = True
    topic: str = "jarvis-skill"    # GitHub topic для поиска плагинов
    token: str = ""              # GITHUB_TOKEN (для повышенных лимитов)


@dataclass
class RagConfig:
    """RAG: загрузка документов и поиск по ним."""

    enabled: bool = True
    documents_dir: str = "~/.jarvis/documents"
    chunk_size: int = 500
    chunk_overlap: int = 100
    top_k: int = 5
    backend: str = "auto"           # auto | chroma | json
    auto_ingest: bool = True       # загружать documents_dir при старте


@dataclass
class ScenesConfig:
    """Автоматизации и сцены: последовательности вызова навыков."""

    enabled: bool = True
    scenes_file: str = "~/.jarvis/scenes.json"  # пользовательские сцены


@dataclass
class SkillsConfig:
    """Настройки навыков."""

    allow_shutdown: bool = False
    screenshot_dir: str = "~/Pictures/Jarvis"
    notes_file: str = "~/.jarvis/notes.md"
    search_engine: str = "https://duckduckgo.com/?q={query}"
    apps: dict[str, str] = field(default_factory=dict)
    aliases: dict[str, str] = field(default_factory=dict)
    profiles: ProfilesConfig = field(default_factory=ProfilesConfig)
    plugin_store: PluginStoreConfig = field(default_factory=PluginStoreConfig)
    rag: RagConfig = field(default_factory=RagConfig)
    scenes: ScenesConfig = field(default_factory=ScenesConfig)
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
    passwords: PasswordsConfig = field(default_factory=PasswordsConfig)
    notes: NotesConfig = field(default_factory=NotesConfig)
    agenda: AgendaConfig = field(default_factory=AgendaConfig)
    habits: HabitsConfig = field(default_factory=HabitsConfig)
    expenses: ExpensesConfig = field(default_factory=ExpensesConfig)
    network: NetworkConfig = field(default_factory=NetworkConfig)
    windows: WindowsConfig = field(default_factory=WindowsConfig)
    disk: DiskConfig = field(default_factory=DiskConfig)
    sysupdate: SysupdateConfig = field(default_factory=SysupdateConfig)
    processes: ProcessesConfig = field(default_factory=ProcessesConfig)
    music_recognition: MusicRecognitionConfig = field(default_factory=MusicRecognitionConfig)
    qr: QrConfig = field(default_factory=QrConfig)
    image_gen: ImageGenConfig = field(default_factory=ImageGenConfig)
    radio: RadioConfig = field(default_factory=RadioConfig)


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
    aliases: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _expand_all_paths(self)

    @property
    def openai_api_key(self) -> str:
        """Ключ OpenAI берём только из окружения, чтобы не хранить в конфиге."""
        return os.environ.get("OPENAI_API_KEY", "")


# ── Загрузка и валидация ─────────────────────────────────────────────


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


def _is_path_field(field_name: str, parent_fields: set[str]) -> bool:
    """Определяет, является ли поле путём к файлу/папке."""
    if field_name in _URL_FIELDS:
        return False
    return any(field_name.endswith(s) for s in _PATH_SUFFIXES)


def _expand_env(value: str) -> str:
    """Подставляет ${VAR} из переменных окружения."""
    def _replacer(m: re.Match) -> str:
        return os.environ.get(m.group(1), m.group(0))
    return _ENV_RE.sub(_replacer, value)


def _warn_unknown(cls: type[Any], data: Mapping[str, Any], prefix: str = "") -> None:
    """Логгит предупреждения о ключах в YAML, которых нет в dataclass."""
    known = {f.name for f in fields(cls)}  # type: ignore[arg-type]
    hints = get_type_hints(cls)
    for key in data:
        full = f"{prefix}{key}"
        if key not in known:
            log.warning("Конфиг: неизвестный ключ «%s» — будет проигнорирован", full)
            continue
        hint = hints.get(key)
        if is_dataclass(hint) and isinstance(data[key], Mapping):
            _warn_unknown(hint, data[key], full + ".")  # type: ignore[arg-type]


def _expand_all_paths(obj: Any) -> None:
    """Рекурсивно раскрывает ~ в строковых полях-путях для dataclass-объекта."""
    if not is_dataclass(obj) or isinstance(obj, type):
        return
    for f in fields(obj):  # type: ignore[arg-type]
        value = getattr(obj, f.name)
        if is_dataclass(value) and not isinstance(value, type):
            _expand_all_paths(value)
        elif isinstance(value, str) and _is_path_field(f.name, set()):
            expanded = os.path.expanduser(value)
            if expanded != value:
                object.__setattr__(obj, f.name, expanded)


def _build(cls: type[T], data: Mapping[str, Any]) -> T:
    """Рекурсивно собирает dataclass из словаря.

    - Поля-пути с ~ автоматически разворачиваются через expanduser.
    - Строковые значения поддерживают ${ENV_VAR} подстановку.
    """
    hints = get_type_hints(cls)
    parent_field_names = {f.name for f in fields(cls)}  # type: ignore[arg-type]
    kwargs: dict[str, Any] = {}
    for f in fields(cls):  # type: ignore[arg-type]
        if f.name not in data:
            continue
        value = data[f.name]
        hint = hints.get(f.name)
        if is_dataclass(hint) and isinstance(value, Mapping):
            kwargs[f.name] = _build(hint, value)  # type: ignore[arg-type]
        elif isinstance(value, str) and _is_path_field(f.name, parent_field_names):
            kwargs[f.name] = _expand_env(value).expanduser()
        elif isinstance(value, str):
            kwargs[f.name] = _expand_env(value)
        else:
            kwargs[f.name] = value
    return cls(**kwargs)


def _sanitize(cls: type[Any], data: Mapping[str, Any], prefix: str = "") -> dict[str, Any]:
    """Проверяет типы и диапазоны, возвращая исправленную копию данных."""
    hints = get_type_hints(cls)
    out: dict[str, Any] = dict(data)
    for f in fields(cls):  # type: ignore[arg-type]
        if f.name not in out:
            continue
        value = out[f.name]
        full_name = f"{prefix}{f.name}"
        hint = hints.get(f.name)

        if is_dataclass(hint) and isinstance(value, Mapping):
            out[f.name] = _sanitize(hint, value, full_name + ".")  # type: ignore[arg-type]
            continue

        rule = _VALIDATION_RULES.get(f.name)
        if rule is None:
            continue
        expected_types, min_val, max_val = rule

        if expected_types is not None and not isinstance(value, expected_types):
            log.warning(
                "Конфиг %s: ожидается %s, получено %s (%r). Берётся значение по умолчанию.",
                full_name, expected_types, type(value).__name__, value,
            )
            if f.default is not MISSING:
                out[f.name] = f.default
            elif f.default_factory is not MISSING:
                out[f.name] = f.default_factory()
            continue

        if min_val is not None and value < min_val:
            log.warning("Конфиг %s: значение %r меньше минимума %s. Исправляю на %s.",
                        full_name, value, min_val, min_val)
            out[f.name] = min_val
        if max_val is not None and value > max_val:
            log.warning("Конфиг %s: значение %r больше максимума %s. Исправляю на %s.",
                        full_name, value, max_val, max_val)
            out[f.name] = max_val
    return out


def load_config(path: str | os.PathLike[str] | None = None) -> Config:
    """Загружает конфигурацию из YAML-файла, возвращая значения по умолчанию.

    Приоритет: явный --config > ~/.jarvis/config.yaml > ./config.yaml > дефолты.
    """
    candidates = [Path(path)] if path else list(DEFAULT_CONFIG_PATHS)
    loaded_from: Path | None = None
    for candidate in candidates:
        if candidate.is_file():
            loaded_from = candidate
            break
    if loaded_from is not None:
        raw = yaml.safe_load(loaded_from.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, Mapping):
            raise ValueError(f"Некорректный конфиг: {loaded_from}")
        _warn_unknown(Config, raw)
        sanitized = _sanitize(Config, raw)
        log.debug("Конфиг загружен: %s", loaded_from)
        return _build(Config, sanitized)
    log.debug("Конфиг не найден, используются значения по умолчанию")
    return Config()


def init_config(target: Path | None = None) -> Path:
    """Копирует config.example.yaml в config.yaml (или указанный путь).

    Возвращает путь созданного файла.
    """
    dest = target or Path("config.yaml")
    if dest.is_file():
        raise FileExistsError(f"{dest} уже существует. Удалите или переименуйте его.")
    # Ищем шаблон рядом с этим файлом (config.py) или в корне проекта.
    this_dir = Path(__file__).resolve().parent
    example_candidates = [
        this_dir.parent / "config.example.yaml",
        Path("config.example.yaml"),
    ]
    for src in example_candidates:
        if src.is_file():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            return dest
    raise FileNotFoundError(
        "config.example.yaml не найден. Создайте config.yaml вручную."
    )
