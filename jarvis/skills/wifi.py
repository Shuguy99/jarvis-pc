from __future__ import annotations

import logging
import shutil
import subprocess
import platform

from .registry import Skill, object_schema

log = logging.getLogger(__name__)

IS_LINUX = platform.system() == "Linux"
IS_WINDOWS = platform.system() == "Windows"


def _nmcli(command: str) -> str:
    """Выполняет nmcli команду."""
    if not shutil.which("nmcli"):
        return "nmcli не найден. Установите NetworkManager, сэр."
    try:
        result = subprocess.run(
            command.split(), capture_output=True, text=True, check=False, timeout=10,
        )
        return result.stdout.strip() or result.stderr.strip()
    except Exception as exc:
        return f"Ошибка: {exc}, сэр."


def wifi_list() -> str:
    """Показывает доступные Wi-Fi сети."""
    if IS_LINUX:
        output = _nmcli("nmcli -t -f SSID,SIGNAL,SECURITY device wifi list")
        if "не найден" in output or "Ошибка" in output:
            return output
        if not output:
            return "Нет доступных Wi-Fi сетей, сэр."
        lines = ["Доступные Wi-Fi сети:"]
        for entry in output.split("\n")[:15]:
            parts = entry.split(":")
            if len(parts) >= 2:
                ssid, signal = parts[0], parts[1]
                security = parts[2] if len(parts) > 2 else "открытая"
                lines.append(f"  {ssid} — сигнал {signal}% ({security})")
        return "\n".join(lines)
    if IS_WINDOWS:
        try:
            result = subprocess.run(
                ["netsh", "wlan", "show", "networks"],
                capture_output=True, text=True, check=False, timeout=10,
            )
            return result.stdout.strip() or "Нет сетей, сэр."
        except Exception as exc:
            return f"Ошибка: {exc}, сэр."
    return "Wi-Fi управление доступно только на Linux и Windows, сэр."


def wifi_status() -> str:
    """Показывает текущее Wi-Fi подключение."""
    if IS_LINUX:
        output = _nmcli("nmcli -t -f NAME,TYPE,DEVICE connection show --active")
        if "не найден" in output or "Ошибка" in output:
            return output
        if not output:
            return "Нет активных подключений, сэр."
        lines = ["Активные подключения:"]
        for entry in output.split("\n"):
            if "wifi" in entry.lower():
                lines.append(f"  {entry.replace(':', ' — ')}")
        if len(lines) == 1:
            return "Wi-Fi не подключён, сэр."
        return "\n".join(lines)
    if IS_WINDOWS:
        try:
            result = subprocess.run(
                ["netsh", "wlan", "show", "interfaces"],
                capture_output=True, text=True, check=False, timeout=10,
            )
            return result.stdout.strip() or "Wi-Fi не подключён, сэр."
        except Exception as exc:
            return f"Ошибка: {exc}, сэр."
    return "Wi-Fi управление доступно только на Linux и Windows, сэр."


def wifi_connect(ssid: str, password: str = "") -> str:
    """Подключается к Wi-Fi сети."""
    if IS_LINUX:
        if not shutil.which("nmcli"):
            return "nmcli не найден. Установите NetworkManager, сэр."
        cmd = ["nmcli", "device", "wifi", "connect", ssid]
        if password:
            cmd.extend(["password", password])
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=15)
            output = result.stdout.strip() or result.stderr.strip()
            if result.returncode != 0:
                return f"Ошибка подключения: {output[:100]}, сэр."
            return f"Подключён к {ssid}, сэр."
        except Exception as exc:
            return f"Ошибка: {exc}, сэр."
    if IS_WINDOWS:
        try:
            subprocess.run(
                ["netsh", "wlan", "connect", f"name={ssid}"],
                check=False, timeout=15,
            )
            return f"Подключаюсь к {ssid}, сэр."
        except Exception as exc:
            return f"Ошибка: {exc}, сэр."
    return "Wi-Fi управление доступно только на Linux и Windows, сэр."


def _get_wifi_device() -> str:
    """Определяет имя Wi-Fi интерфейса через nmcli."""
    try:
        result = subprocess.run(
            ["nmcli", "-t", "-f", "DEVICE,TYPE", "device", "status"],
            capture_output=True, text=True, check=False, timeout=5,
        )
        for line in result.stdout.strip().split("\n"):
            parts = line.split(":")
            if len(parts) >= 2 and parts[1].strip().lower() == "wifi":
                return parts[0].strip()
    except Exception:
        pass
    return "wlan0"


def wifi_disconnect() -> str:
    """Отключает текущее Wi-Fi подключение."""
    if IS_LINUX:
        if not shutil.which("nmcli"):
            return "nmcli не найден. Установите NetworkManager, сэр."
        device = _get_wifi_device()
        try:
            result = subprocess.run(
                ["nmcli", "device", "disconnect", device],
                capture_output=True, text=True, check=False, timeout=10,
            )
            output = result.stdout.strip() or result.stderr.strip()
            if result.returncode != 0:
                return f"Ошибка отключения: {output[:100]}, сэр."
            return "Wi-Fi отключён, сэр."
        except Exception as exc:
            return f"Ошибка: {exc}, сэр."
    if IS_WINDOWS:
        try:
            subprocess.run(
                ["netsh", "wlan", "disconnect"],
                check=False, timeout=10,
            )
            return "Wi-Fi отключён, сэр."
        except Exception as exc:
            return f"Ошибка: {exc}, сэр."
    return "Wi-Fi управление доступно только на Linux и Windows, сэр."


def build_skills() -> list[Skill]:
    """Создаёт Wi-Fi навыки."""
    return [
        Skill(
            name="wifi_list",
            description="Показать доступные Wi-Fi сети.",
            parameters=object_schema({}),
            handler=wifi_list,
        ),
        Skill(
            name="wifi_status",
            description="Показать текущее Wi-Fi подключение.",
            parameters=object_schema({}),
            handler=wifi_status,
        ),
        Skill(
            name="wifi_connect",
            description="Подключиться к Wi-Fi сети.",
            parameters=object_schema(
                {
                    "ssid": {"type": "string", "description": "Название сети"},
                    "password": {"type": "string", "description": "Пароль (если нужно)"},
                },
                required=["ssid"],
            ),
            handler=wifi_connect,
        ),
        Skill(
            name="wifi_disconnect",
            description="Отключить Wi-Fi.",
            parameters=object_schema({}),
            handler=wifi_disconnect,
        ),
    ]