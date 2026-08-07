"""Управление яркостью монитора."""

from __future__ import annotations

import logging
import platform
import re
import shutil
import subprocess

from .registry import Skill, object_schema

log = logging.getLogger(__name__)

IS_LINUX = platform.system() == "Linux"
IS_WINDOWS = platform.system() == "Windows"
IS_MACOS = platform.system() == "Darwin"


def get_brightness() -> str:
    try:
        if IS_LINUX:
            if shutil.which("brightnessctl"):
                r = subprocess.run(["brightnessctl", "info"], capture_output=True, text=True, timeout=5)
                for part in r.stdout.split():
                    if "%" in part:
                        return f"Яркость: {int(part.rstrip('(%),'))}%, сэр."
            if shutil.which("xrandr"):
                r = subprocess.run(["xrandr", "--verbose"], capture_output=True, text=True, timeout=5)
                m = re.search(r"Brightness:\s*([\d.]+)", r.stdout)
                if m:
                    return f"Яркость: {int(float(m.group(1)) * 100)}%, сэр."
            return "Не удалось определить яркость (нужен brightnessctl или xrandr), сэр."
        if IS_MACOS and shutil.which("brightness"):
            r = subprocess.run(["brightness", "-l"], capture_output=True, text=True, timeout=5)
            m = re.search(r"brightness\s+([\d.]+)", r.stdout)
            if m:
                return f"Яркость: {int(float(m.group(1)) * 100)}%, сэр."
            return "Установите brightness, сэр."
        if IS_WINDOWS:
            r = subprocess.run(["powershell", "-NoProfile", "-Command",
                               "(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightness).CurrentBrightness"],
                              capture_output=True, text=True, timeout=10)
            if r.stdout.strip():
                return f"Яркость: {r.stdout.strip()}%, сэр."
        return "Яркость: не поддерживается, сэр."
    except Exception as exc:
        return f"Ошибка: {exc}, сэр."


def set_brightness(level: int = 50) -> str:
    level = max(0, min(100, level))
    try:
        if IS_LINUX:
            if shutil.which("brightnessctl"):
                subprocess.run(["brightnessctl", "set", f"{level}%"], check=False, timeout=5)
                return f"Яркость: {level}%, сэр."
            if shutil.which("xrandr"):
                r = subprocess.run(["xrandr", "--current"], capture_output=True, text=True, timeout=5)
                displays = re.findall(r"^(\S+) connected", r.stdout, re.MULTILINE)
                if displays:
                    subprocess.run(["xrandr", "--output", displays[0], "--brightness", str(level / 100)],
                                   check=False, timeout=5)
                    return f"Яркость: {level}%, сэр."
            return "Не удалось изменить яркость, сэр."
        if IS_MACOS and shutil.which("brightness"):
            subprocess.run(["brightness", str(level / 100)], check=False, timeout=5)
            return f"Яркость: {level}%, сэр."
        if IS_WINDOWS:
            subprocess.run(["powershell", "-NoProfile", "-Command",
                           f"(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1,{level})"],
                          check=False, timeout=10)
            return f"Яркость: {level}%, сэр."
        return "Яркость: не поддерживается, сэр."
    except Exception as exc:
        return f"Ошибка: {exc}, сэр."


def build_skills() -> list[Skill]:
    return [
        Skill(name="get_brightness", description="Узнать текущую яркость монитора.",
              parameters=object_schema({}), handler=get_brightness),
        Skill(name="set_brightness", description="Установить яркость монитора (0-100).",
              parameters=object_schema({"level": {"type": "integer", "description": "Яркость 0-100"}}),
              handler=lambda level=50: set_brightness(level)),
    ]
