from __future__ import annotations

import logging
import platform
import shutil
import subprocess
from pathlib import Path

from ..config import SoundsConfig
from .registry import Skill, object_schema

log = logging.getLogger(__name__)

IS_WINDOWS = platform.system() == "Windows"

_DEFAULT_SOUNDS: dict[str, str] = {
    "startup": "startup.wav",
    "shutdown": "shutdown.wav",
    "error": "error.wav",
    "timer": "timer.wav",
    "notification": "notify.wav",
}


def _get_sounds_dir(config: SoundsConfig) -> Path:
    custom = Path(config.sounds_dir).expanduser()
    if custom.is_dir():
        return custom
    return Path.home() / ".jarvis" / "sounds"


def _play_sound_file(filepath: str) -> str:
    """Воспроизводит звуковой файл."""
    if not Path(filepath).exists():
        return f"Файл {filepath} не найден, сэр."
    try:
        if IS_WINDOWS:
            import winsound  # type: ignore[import-not-found]
            winsound.PlaySound(filepath, winsound.SND_FILENAME | winsound.SND_ASYNC)
        elif platform.system() == "Darwin":
            subprocess.run(["afplay", filepath], check=False, timeout=10)
        else:
            if shutil.which("paplay"):
                subprocess.run(["paplay", filepath], check=False, timeout=10)
            elif shutil.which("aplay"):
                subprocess.run(["aplay", filepath], check=False, timeout=10)
            elif shutil.which("ffplay"):
                subprocess.run(["ffplay", "-nodisp", "-autoexit", filepath],
                               check=False, timeout=10, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                return "Нет аудио плеера (paplay/aplay/ffplay), сэр."
        return "Готово, сэр."
    except Exception as exc:
        return f"Ошибка воспроизведения: {exc}, сэр."


def play_sound(config: SoundsConfig, event: str = "") -> str:
    """Воспроизводит звук для события."""
    if not config.enabled:
        return "Звуки отключены в конфиге, сэр."
    event = event.lower().strip()
    if not event:
        return f"Доступные события: {', '.join(sorted(_DEFAULT_SOUNDS.keys()))}"
    sound_file = config.custom_sounds.get(event) or _DEFAULT_SOUNDS.get(event)
    if not sound_file:
        return f"Неизвестное событие '{event}', сэр."
    filepath = _get_sounds_dir(config) / sound_file
    return _play_sound_file(str(filepath))


def play_beep(config: SoundsConfig, freq: int = 440, duration_ms: int = 200) -> str:
    """Издать системный бип."""
    if not config.enabled:
        return "Звуки отключены, сэр."
    try:
        if IS_WINDOWS:
            import winsound  # type: ignore[import-not-found]
            winsound.Beep(freq, duration_ms)
        elif platform.system() == "Darwin":
            subprocess.run(["tput", "bel"], check=False, timeout=3)
        else:
            if shutil.which("beep"):
                subprocess.run(["beep", "-f", str(freq), "-l", str(duration_ms)],
                               check=False, timeout=5)
            else:
                print("\a", end="", flush=True)
        return "Бип, сэр."
    except Exception as exc:
        return f"Ошибка: {exc}, сэр."


def list_sounds(config: SoundsConfig) -> str:
    """Показать доступные звуковые файлы."""
    sounds_dir = _get_sounds_dir(config)
    if not sounds_dir.is_dir():
        return f"Директория {sounds_dir} не найдена, сэр."
    audio_exts = {".wav", ".mp3", ".ogg", ".flac", ".aac"}
    audio_files = [f for f in sounds_dir.iterdir() if f.suffix.lower() in audio_exts]
    if not audio_files:
        return f"В {sounds_dir} нет аудиофайлов, сэр."
    lines = [f"Звуковые файлы в {sounds_dir}:"]
    for f in sorted(audio_files):
        lines.append(f"  {f.name}")
    return "\n".join(lines)


def build_skills(config: SoundsConfig) -> list[Skill]:
    """Создаёт навыки звуков."""
    return [
        Skill(
            name="play_sound",
            description="Воспроизвести звук для события (startup, error, timer, notification).",
            parameters=object_schema(
                {
                    "event": {
                        "type": "string",
                        "description": "Событие (startup, shutdown, error, timer, notification)",
                    },
                },
            ),
            handler=lambda event="": play_sound(config, event),
        ),
        Skill(
            name="play_beep",
            description="Издать системный бип с заданной частотой и длительностью.",
            parameters=object_schema(
                {
                    "freq": {"type": "integer", "description": "Частота в Гц (по умолчанию 440)"},
                    "duration_ms": {"type": "integer", "description": "Длительность в мс (по умолчанию 200)"},
                },
            ),
            handler=lambda freq=440, duration_ms=200: play_beep(config, freq, duration_ms),
        ),
        Skill(
            name="list_sounds",
            description="Показать доступные звуковые файлы в ~/.jarvis/sounds/.",
            parameters=object_schema({}),
            handler=lambda: list_sounds(config),
        ),
    ]
