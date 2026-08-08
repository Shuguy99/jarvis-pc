"""Распознавание музыки: запись фрагмента и опознание трека."""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import tempfile
import urllib.request
from pathlib import Path

from ..config import MusicRecognitionConfig
from .registry import Skill, object_schema

log = logging.getLogger(__name__)


def _record_fragment(duration: int = 5) -> str | None:
    """Записывает аудио фрагмент с микрофона."""
    recorder = None
    if shutil.which("arecord"):
        recorder = "arecord"
    elif shutil.which("sox"):
        recorder = "sox"
    if not recorder:
        return None
    tmp = Path(tempfile.mktemp(suffix=".wav"))
    if recorder == "arecord":
        cmd = ["arecord", "-d", str(duration), "-f", "S16_LE", "-r", "16000", "-c", "1", str(tmp)]
    else:
        cmd = ["sox", "-d", "-r", "16000", "-c", "1", str(tmp), "trim", "0", str(duration)]
    try:
        subprocess.run(cmd, capture_output=True, check=False, timeout=duration + 5)
        if tmp.is_file() and tmp.stat().st_size > 1000:
            return str(tmp)
    except Exception as exc:
        log.warning("Запись аудио: %s", exc)
    return None


def _recognize_audd(audio_path: str, api_key: str) -> str:
    """Распознаёт через AudD API."""
    try:
        with open(audio_path, "rb") as f:
            audio_data = f.read()
    except Exception as exc:
        return f"Не удалось прочитать аудио: {exc}, сэр."
    boundary = "----JarvisAudioBoundary"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="api_token"\r\n\r\n'
        f"{api_key}\r\n"
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="audio.wav"\r\n'
        f"Content-Type: audio/wav\r\n\r\n"
    ).encode("utf-8") + audio_data + f"\r\n--{boundary}--\r\n".encode("utf-8")
    url = "https://api.audd.io/"
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        if result.get("result"):
            r = result["result"]
            artist = r.get("artist", "?")
            title = r.get("title", "?")
            album = r.get("album", "")
            album_str = f" (альбом: {album})" if album else ""
            return f"Это {artist} — {title}{album_str}, сэр."
        if result.get("error"):
            return f"Не удалось распознать: {result['error']['error_message']}, сэр."
        return "Трек не распознан, сэр."
    except Exception as exc:
        return f"Ошибка распознавания: {exc}, сэр."


def recognize(config: MusicRecognitionConfig) -> str:
    """Записывает фрагмент и распознаёт трек."""
    if not config.api_key:
        return "Для распознавания музыки нужен AudD API ключ (audd.io), сэр."
    audio = _record_fragment(config.record_seconds)
    if not audio:
        return "Не удалось записать аудио. Установите sox или alsa-utils, сэр."
    result = _recognize_audd(audio, config.api_key)
    try:
        Path(audio).unlink(missing_ok=True)
    except Exception:
        log.debug("music_recognition: не критичная ошибка при Path(audio).unlink(missing_ok=True)")
    return result


def build_skills(config: MusicRecognitionConfig) -> list[Skill]:
    return [
        Skill(
            name="recognize_music",
            description="Записать фрагмент и распознать играющую музыку.",
            parameters=object_schema({}),
            handler=lambda: recognize(config),
        ),
    ]
