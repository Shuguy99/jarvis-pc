"""Управление громкостью системы."""

from __future__ import annotations

import logging
import platform
import shutil
import subprocess

from .registry import Skill, object_schema

log = logging.getLogger(__name__)

IS_WINDOWS = platform.system() == "Windows"
IS_MACOS = platform.system() == "Darwin"
IS_LINUX = platform.system() == "Linux"


def _get_volume() -> int:
    try:
        if IS_WINDOWS:
            try:
                from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
                devices = AudioUtilities.GetSpeakers()
                interface = devices.Activate(IAudioEndpointVolume._iid_, 0, None, None)
                return int(interface.GetMasterVolumeLevelScalar() * 100)
            except Exception:
                pass
            return 50
        if IS_MACOS:
            r = subprocess.run(["osascript", "-e", "output volume of (get volume settings)"],
                               capture_output=True, text=True, timeout=5)
            return int(r.stdout.strip()) if r.stdout.strip().isdigit() else 50
        if shutil.which("pactl"):
            r = subprocess.run(["pactl", "get-sink-volume", "@DEFAULT_SINK@"],
                               capture_output=True, text=True, timeout=5)
            for part in r.stdout.split():
                if part.endswith("%"):
                    return int(part.rstrip("%"))
        return 50
    except Exception:
        return 50


def _set_volume(level: int) -> str:
    level = max(0, min(100, level))
    try:
        if IS_WINDOWS:
            try:
                from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
                devices = AudioUtilities.GetSpeakers()
                interface = devices.Activate(IAudioEndpointVolume._iid_, 0, None, None)
                interface.SetMasterVolumeLevelScalar(level / 100, None)
            except Exception:
                pass
        elif IS_MACOS:
            subprocess.run(["osascript", "-e", f"set volume output volume {level}"],
                           check=False, timeout=5)
        elif shutil.which("pactl"):
            subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{level}%"],
                           check=False, timeout=5)
        elif shutil.which("amixer"):
            subprocess.run(["amixer", "set", "Master", f"{level}%"], check=False, timeout=5)
        else:
            return "Нет pactl/amixer, сэр."
        return f"Громкость: {level}%, сэр."
    except Exception as exc:
        return f"Ошибка: {exc}, сэр."


def _mute() -> str:
    try:
        if IS_WINDOWS:
            subprocess.run(["powershell", "-NoProfile", "-Command",
                           "(New-Object -ComObject WScript.Shell).SendKeys([char]173)"],
                           check=False, timeout=5)
        elif IS_MACOS:
            subprocess.run(["osascript", "-e", "set volume output muted not output muted"],
                           check=False, timeout=5)
        elif shutil.which("pactl"):
            subprocess.run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"], check=False, timeout=5)
        elif shutil.which("amixer"):
            subprocess.run(["amixer", "set", "Master", "toggle"], check=False, timeout=5)
        return "Звук переключён, сэр."
    except Exception as exc:
        return f"Ошибка: {exc}, сэр."


def get_volume() -> str:
    return f"Текущая громкость: {_get_volume()}%, сэр."


def set_volume(level: int = 50) -> str:
    return _set_volume(level)


def volume_up(step: int = 10) -> str:
    return _set_volume(_get_volume() + step)


def volume_down(step: int = 10) -> str:
    return _set_volume(_get_volume() - step)


def toggle_mute() -> str:
    return _mute()


def build_skills() -> list[Skill]:
    return [
        Skill(name="get_system_volume", description="Узнать текущую громкость (0-100).",
              parameters=object_schema({}), handler=get_volume),
        Skill(name="system_volume", description="Установить громкость (0-100).",
              parameters=object_schema({"level": {"type": "integer", "description": "Громкость 0-100"}}),
              handler=lambda level=50: set_volume(level)),
        Skill(name="system_volume_up", description="Увеличить громкость.",
              parameters=object_schema({"step": {"type": "integer", "description": "Шаг (по умолчанию 10)"}}),
              handler=lambda step=10: volume_up(step)),
        Skill(name="system_volume_down", description="Уменьшить громкость.",
              parameters=object_schema({"step": {"type": "integer", "description": "Шаг (по умолчанию 10)"}}),
              handler=lambda step=10: volume_down(step)),
        Skill(name="system_toggle_mute", description="Переключить звук (mute/unmute).",
              parameters=object_schema({}), handler=toggle_mute),
    ]
