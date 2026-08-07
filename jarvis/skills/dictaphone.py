"""Диктофон: записать речь в текстовый файл."""

from __future__ import annotations

import logging
import time
from pathlib import Path

from ..audio.microphone import Microphone, SpeechRecorder
from ..config import MicConfig
from .registry import Skill, object_schema

log = logging.getLogger(__name__)


def _record_to_text(mic_config: MicConfig, max_seconds: int = 60) -> str:
    """Записывает с микрофона и возвращает распознанный текст."""
    try:
        import sounddevice as sd
    except ImportError:
        return "sounddevice не установлен. pip install sounddevice, сэр."
    recorder = SpeechRecorder(mic_config)
    with Microphone(mic_config) as mic:
        audio = recorder.record(mic)
    if audio.size == 0:
        return "Ничего не услышал, сэр."
    try:
        from ..audio.stt import SpeechToText
        from ..config import SttConfig
        stt = SpeechToText(SttConfig())
        text = stt.transcribe(audio, mic_config.sample_rate)
        if not text:
            return "Не удалось распознать речь, сэр."
        return text
    except Exception as exc:
        return f"Ошибка распознавания: {exc}, сэр."


def dictaphone(mic_config: MicConfig, filepath: str = "", max_seconds: int = 60) -> str:
    """Записывает речь и сохраняет в текстовый файл."""
    text = _record_to_text(mic_config, max_seconds)
    if text.startswith("sounddevice") or text.startswith("Ничего") or text.startswith("Не удалось"):
        return text
    if not filepath:
        filepath = f"~/.jarvis/dictaphone_{int(time.time())}.txt"
    fpath = Path(filepath).expanduser()
    fpath.parent.mkdir(parents=True, exist_ok=True)
    fpath.write_text(text, encoding="utf-8")
    return f"Записано и сохранено в {fpath}, сэр."


def build_skills(mic_config: MicConfig) -> list[Skill]:
    return [
        Skill(name="dictaphone", description="Записать речь с микрофона и сохранить текст в файл.",
              parameters=object_schema({
                  "filepath": {"type": "string", "description": "Путь к файлу (по умолчанию ~/.jarvis/dictaphone_...)"},
              }),
              handler=lambda filepath="": dictaphone(mic_config, filepath)),
    ]
