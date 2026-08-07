"""Управление Bluetooth (Linux bluetoothctl, Windows, macOS)."""

from __future__ import annotations

import logging
import platform
import shutil
import subprocess

from .registry import Skill, object_schema

log = logging.getLogger(__name__)

IS_LINUX = platform.system() == "Linux"
IS_WINDOWS = platform.system() == "Windows"
IS_MACOS = platform.system() == "Darwin"


def bt_status() -> str:
    try:
        if IS_LINUX and shutil.which("bluetoothctl"):
            r = subprocess.run(["bluetoothctl", "show"], capture_output=True, text=True, timeout=10)
            return "Bluetooth включён, сэр." if "Powered: yes" in r.stdout else "Bluetooth выключен, сэр."
        if IS_MACOS:
            r = subprocess.run(["system_profiler", "SPBluetoothDataType"], capture_output=True, text=True, timeout=10)
            return "Bluetooth доступен (macOS), сэр." if r.stdout.strip() else "Не удалось получить статус, сэр."
        if IS_WINDOWS:
            r = subprocess.run(["powershell", "-NoProfile", "-Command", "Get-Service bthserv | Select-Object -ExpandProperty Status"],
                               capture_output=True, text=True, timeout=10)
            return f"Служба Bluetooth: {r.stdout.strip()}, сэр."
        return "Bluetooth не поддерживается на этой ОС, сэр."
    except Exception as exc:
        return f"Ошибка: {exc}, сэр."


def bt_toggle() -> str:
    try:
        if IS_LINUX and shutil.which("bluetoothctl"):
            subprocess.run(["bluetoothctl", "power", "toggle"], check=False, timeout=10)
            return "Bluetooth переключён, сэр."
        if IS_MACOS and shutil.which("blueutil"):
            subprocess.run(["blueutil", "--power", "toggle"], check=False, timeout=10)
            return "Bluetooth переключён, сэр."
        return "Переключение Bluetooth доступно только на Linux/macOS, сэр."
    except Exception as exc:
        return f"Ошибка: {exc}, сэр."


def bt_scan() -> str:
    try:
        if IS_LINUX and shutil.which("bluetoothctl"):
            subprocess.run(["bluetoothctl", "scan", "on"], capture_output=True, timeout=3)
            import time; time.sleep(3)
            r = subprocess.run(["bluetoothctl", "devices"], capture_output=True, text=True, timeout=10)
            lines = [l for l in r.stdout.strip().split("\n") if l.strip()]
            if not lines:
                return "Устройства не найдены, сэр."
            return "Найденные устройства:\n" + "\n".join(f"  {l}" for l in lines[:10]) + ", сэр."
        return "Сканирование Bluetooth доступно только на Linux, сэр."
    except Exception as exc:
        return f"Ошибка: {exc}, сэр."


def build_skills() -> list[Skill]:
    return [
        Skill(name="bt_status", description="Статус Bluetooth (включён/выключен).",
              parameters=object_schema({}), handler=bt_status),
        Skill(name="bt_toggle", description="Включить/выключить Bluetooth.",
              parameters=object_schema({}), handler=bt_toggle),
        Skill(name="bt_scan", description="Сканировать Bluetooth-устройства рядом.",
              parameters=object_schema({}), handler=bt_scan),
    ]
