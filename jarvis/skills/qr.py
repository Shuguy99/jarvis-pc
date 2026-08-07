from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path

from .registry import Skill, object_schema

log = logging.getLogger(__name__)


def _qr_available() -> bool:
    return subprocess.run(["which", "qrencode"], capture_output=True).returncode == 0


def _zbar_available() -> bool:
    return subprocess.run(["which", "zbarimg"], capture_output=True).returncode == 0


def generate_qr(text: str, output_path: str = "") -> str:
    """Генерирует QR-код и сохраняет как PNG."""
    if not _qr_available():
        return "qrencode не установлен. Установите: sudo apt install qrencode, сэр."
    if not output_path:
        output_path = str(Path(tempfile.mktemp(suffix=".png")))
    try:
        subprocess.run(
            ["qrencode", "-o", output_path, "-s", "6", text],
            capture_output=True, check=False, timeout=10,
        )
        if Path(output_path).is_file():
            return f"QR-код сохранён: {output_path}, сэр."
        return "Не удалось создать QR-код, сэр."
    except Exception as exc:
        return f"Ошибка: {exc}, сэр."


def wifi_qr(ssid: str, password: str = "", encryption: str = "WPA") -> str:
    """Генерирует QR-код для подключения к Wi-Fi."""
    wifi_str = f"WIFI:T:{encryption};S:{ssid};P:{password};;"
    if not _qr_available():
        return "qrencode не установлен, сэр."
    output = str(Path.home() / "Pictures" / "Jarvis" / f"wifi_{ssid}.png")
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            ["qrencode", "-o", output, "-s", "8", wifi_str],
            capture_output=True, check=False, timeout=10,
        )
        if Path(output).is_file():
            return f"Wi-Fi QR-код сохранён: {output}, сэр."
        return "Не удалось создать QR-код, сэр."
    except Exception as exc:
        return f"Ошибка: {exc}, сэр."


def read_qr(image_path: str) -> str:
    """Читает QR-код из файла изображения."""
    if not _zbar_available():
        return "zbarimg не установлен. Установите: sudo apt install zbar, сэр."
    p = Path(image_path).expanduser()
    if not p.is_file():
        return f"Файл {image_path} не найден, сэр."
    try:
        result = subprocess.run(
            ["zbarimg", "--raw", str(p)],
            capture_output=True, text=True, check=False, timeout=10,
        )
        text = result.stdout.strip()
        if text:
            return f"QR-код: {text}, сэр."
        return "QR-код не найден в изображении, сэр."
    except Exception as exc:
        return f"Ошибка: {exc}, сэр."


def build_skills() -> list[Skill]:
    return [
        Skill(
            name="generate_qr",
            description="Сгенерировать QR-код из текста и сохранить как PNG.",
            parameters=object_schema(
                {
                    "text": {"type": "string", "description": "Текст для кодирования"},
                    "output_path": {"type": "string", "description": "Путь к файлу (по умолчанию временный)"},
                },
                required=["text"],
            ),
            handler=lambda text, output_path="": generate_qr(text, output_path),
        ),
        Skill(
            name="wifi_qr",
            description="Сгенерировать QR-код для подключения к Wi-Fi сети.",
            parameters=object_schema(
                {
                    "ssid": {"type": "string", "description": "Название сети"},
                    "password": {"type": "string", "description": "Пароль"},
                    "encryption": {"type": "string", "description": "WPA | WEP | nopass"},
                },
                required=["ssid"],
            ),
            handler=lambda ssid, password="", encryption="WPA": wifi_qr(ssid, password, encryption),
        ),
        Skill(
            name="read_qr",
            description="Прочитать QR-код из файла изображения.",
            parameters=object_schema(
                {"image_path": {"type": "string", "description": "Путь к файлу"}},
                required=["image_path"],
            ),
            handler=lambda image_path: read_qr(image_path),
        ),
    ]
