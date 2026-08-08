"""YouTube Music контроль: pause/resume/next/previous/status через MPV IPC."""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile

from .registry import Skill, object_schema

log = logging.getLogger(__name__)

# MPV слушает команды через UNIX socket (Linux/macOS) или named pipe (Windows).
_IPC_PATH = os.path.join(tempfile.gettempdir(), "jarvis-mpv-ipc")


def _is_mpv_running() -> bool:
    """Проверяет, запущен ли MPV с нашим IPC."""
    if not os.path.exists(_IPC_PATH):
        return False
    if shutil.which("pkill"):
        r = subprocess.run(["pgrep", "-f", "mpv"], capture_output=True, timeout=3)
        return r.returncode == 0
    if shutil.which("tasklist"):
        r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq mpv.exe"],
                           capture_output=True, text=True, timeout=3)
        return "mpv.exe" in r.stdout
    return False


def _mpv_command(cmd: dict) -> dict | None:
    """Отправляет JSON-команду в MPV через IPC-сокет."""
    import socket
    if not os.path.exists(_IPC_PATH):
        return None
    try:
        if os.name == "nt":
            # Windows: named pipe
            import time
            try:
                pipe = open(_IPC_PATH, "w+b", 0)
            except Exception:
                log.debug("youtube_music: не удалось открыть IPC pipe")
                return None
            try:
                payload = (json.dumps(cmd) + chr(10)).encode()
                pipe.write(payload)
                pipe.seek(0)
                data = pipe.read(4096)
                if data:
                    return json.loads(data)
                return {}
            finally:
                pipe.close()
        else:
            # Linux/macOS: UNIX socket
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(2)
            try:
                sock.connect(_IPC_PATH)
                payload = (json.dumps(cmd) + chr(10)).encode()
                sock.sendall(payload)
                data = b""
                while True:
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    data += chunk
                    if data.rstrip().endswith(b"}"):
                        break
                if data:
                    return json.loads(data)
                return {}
            finally:
                sock.close()
    except Exception as exc:
        log.debug("MPV IPC ошибка: %s", exc)
        return None


def _get_status() -> dict:
    """Получает статус MPV: пауза, позиция, длительность, название."""
    result: dict = {"playing": False}
    if not _is_mpv_running():
        return result
    for prop in ("pause", "time-pos", "duration", "media-title"):
        resp = _mpv_command({"command": ["get_property", prop]})
        if resp and resp.get("data") is not None:
            result[prop] = resp["data"]
    result["playing"] = not result.get("pause", True)
    return result


def _format_time(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m}:{s:02d}"


def yt_music_status() -> str:
    """Статус текущего воспроизведения."""
    if not _is_mpv_running():
        return "Ничего не воспроизводится, сэр."
    st = _get_status()
    title = st.get("media-title", "неизвестно")
    pos = st.get("time-pos", 0)
    dur = st.get("duration", 0)
    state = "воспроизведение" if st.get("playing") else "пауза"
    time_info = ""
    if pos and dur:
        time_info = f" ({_format_time(pos)}/{_format_time(dur)})"
    return f"{state}: {title}{time_info}, сэр."


def yt_music_pause() -> str:
    """Пауза."""
    if not _is_mpv_running():
        return "Нечего ставить на паузу, сэр."
    _mpv_command({"command": ["set_property", "pause", True]})
    return "На паузе, сэр."


def yt_music_resume() -> str:
    """Продолжить воспроизведение."""
    if not _is_mpv_running():
        return "Нечего воспроизводить, сэр."
    _mpv_command({"command": ["set_property", "pause", False]})
    return "Воспроизвожу, сэр."


def yt_music_toggle() -> str:
    """Переключить пауза/воспроизведение."""
    if not _is_mpv_running():
        return "Ничего не играет, сэр."
    _mpv_command({"command": ["cycle", "pause"]})
    return "Переключил, сэр."


def yt_music_seek(seconds: int) -> str:
    """Перемотать на N секунд (отрицательное — назад)."""
    if not _is_mpv_running():
        return "Ничего не воспроизводится, сэр."
    _mpv_command({"command": ["seek", seconds]})
    direction = "вперёд" if seconds >= 0 else "назад"
    return f"Перемотал {abs(seconds)} сек. {direction}, сэр."


def yt_music_volume(level: int = 100) -> str:
    """Установить громкость MPV (0-100)."""
    if not _is_mpv_running():
        return "MPV не запущен, сэр."
    _mpv_command({"command": ["set_property", "volume", max(0, min(200, level))]})
    return f"Громкость MPV: {level}%, сэр."


def build_skills() -> list[Skill]:
    return [
        Skill(name="yt_music_status", description="Статус текущего воспроизведения MPV (название, позиция, пауза).",
              parameters=object_schema({}), handler=yt_music_status),
        Skill(name="yt_music_pause", description="Поставить текущее воспроизведение на паузу.",
              parameters=object_schema({}), handler=yt_music_pause),
        Skill(name="yt_music_resume", description="Продолжить воспроизведение после паузы.",
              parameters=object_schema({}), handler=yt_music_resume),
        Skill(name="yt_music_toggle", description="Переключить пауза/воспроизведение.",
              parameters=object_schema({}), handler=yt_music_toggle),
        Skill(name="yt_music_seek", description="Перемотать на N секунд (отрицательное — назад).",
              parameters=object_schema({
                  "seconds": {"type": "integer", "description": "Секунды для перемотки (отриц. = назад)"}
              }, required=["seconds"]), handler=lambda seconds: yt_music_seek(seconds)),
        Skill(name="yt_music_volume", description="Установить громкость MPV (0-200).",
              parameters=object_schema({
                  "level": {"type": "integer", "description": "Громкость 0-200 (100 = нормальная)"}
              }), handler=lambda level=100: yt_music_volume(level)),
    ]
