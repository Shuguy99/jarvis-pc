from __future__ import annotations

import logging
import platform
import shutil
import subprocess

from .registry import Skill, object_schema

log = logging.getLogger(__name__)

IS_LINUX = platform.system() == "Linux"
IS_WINDOWS = platform.system() == "Windows"


def _pkg_count() -> str:
    """Количество пакетов для обновления (Linux)."""
    if shutil.which("apt"):
        result = subprocess.run(
            ["apt", "list", "--upgradable"],
            capture_output=True, text=True, check=False, timeout=15,
        )
        lines = [l for l in result.stdout.strip().split("\n") if "upgradable" in l]
        if not lines:
            return "Все пакеты актуальны, сэр."
        return f"Пакетов для обновления: {len(lines)}, сэр."
    if shutil.which("dnf"):
        result = subprocess.run(
            ["dnf", "check-update"],
            capture_output=True, text=True, check=False, timeout=30,
        )
        lines = [l for l in result.stdout.strip().split("\n") if l and not l.startswith("Last")]
        count = max(0, len(lines) - 1)
        return f"Пакетов для обновления: {count}, сэр." if count else "Все пакеты актуальны, сэр."
    if shutil.which("pacman"):
        result = subprocess.run(
            ["checkupdates"], capture_output=True, text=True, check=False, timeout=30,
        )
        lines = [l for l in result.stdout.strip().split("\n") if l]
        return f"Пакетов для обновления: {len(lines)}, сэр." if lines else "Все пакеты актуальны, сэр."
    return "Не удалось проверить обновления (apt/dnf/pacman не найдены), сэр."


def check_updates() -> str:
    """Проверяет наличие обновлений."""
    if IS_LINUX:
        return _pkg_count()
    if IS_WINDOWS:
        return "На Windows используйте настройки Windows Update, сэр."
    return "Не поддерживается, сэр."


def run_update() -> str:
    """Запускает обновление системы."""
    if IS_LINUX:
        if shutil.which("sudo") and shutil.which("apt"):
            result = subprocess.run(
                ["sudo", "apt", "update", "-y"],
                capture_output=True, text=True, check=False, timeout=60,
            )
            result2 = subprocess.run(
                ["sudo", "apt", "upgrade", "-y"],
                capture_output=True, text=True, check=False, timeout=300,
            )
            if result2.returncode == 0:
                return "Обновление завершено, сэр."
            err = result2.stderr.strip()[-100:] if result2.stderr else ""
            return f"Обновление завершено с ошибкой: {err}, сэр."
        return "Поддерживается только apt (Ubuntu/Debian) с sudo, сэр."
    if IS_WINDOWS:
        try:
            subprocess.Popen(["powershell", "-Command", "Start-WUScan"], check=False)
            return "Windows Update запущен, сэр."
        except Exception:
            pass
    return "Не поддерживается, сэр."


def pip_update(package: str = "") -> str:
    """Обновляет Python-пакет."""
    if not shutil.which("pip") and not shutil.which("pip3"):
        return "pip не найден, сэр."
    pip = "pip3" if shutil.which("pip3") else "pip"
    if package:
        result = subprocess.run(
            [pip, "install", "--upgrade", package],
            capture_output=True, text=True, check=False, timeout=120,
        )
        if result.returncode == 0:
            return f"{package} обновлён, сэр."
        return f"Ошибка обновления {package}: {result.stderr.strip()[:100]}, сэр."
    result = subprocess.run(
        [pip, "list", "--outdated"],
        capture_output=True, text=True, check=False, timeout=30,
    )
    lines = [l for l in result.stdout.strip().split("\n")[2:] if l]
    if not lines:
        return "Все Python-пакеты актуальны, сэр."
    outdated = [l.strip().split()[0] for l in lines[:20] if l.strip()]
    return f"Устаревшие пакеты: {', '.join(outdated)}, сэр."


def build_skills() -> list[Skill]:
    return [
        Skill(
            name="check_updates",
            description="Проверить наличие обновлений системы.",
            parameters=object_schema({}),
            handler=check_updates,
        ),
        Skill(
            name="run_update",
            description="Запустить обновление системы (apt upgrade).",
            parameters=object_schema({}),
            handler=run_update,
        ),
        Skill(
            name="pip_update",
            description="Обновить Python-пакет или показать устаревшие.",
            parameters=object_schema(
                {"package": {"type": "string", "description": "Имя пакета (пусто = список устаревших)"}}
            ),
            handler=lambda package="": pip_update(package),
        ),
    ]
