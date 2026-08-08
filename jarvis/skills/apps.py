"""Навыки запуска приложений и управления окнами."""

from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess

# Допустимые символы в имени команды (латиница, кириллица, цифры, пробелы, точки, дефисы, слеши).
_SAFE_CMD_RE = re.compile(r'^[\w\-./ :\\а-яА-ЯёЁ]+$')

from ..config import SkillsConfig
from .registry import Skill, _confirm_handler, object_schema

IS_WINDOWS = platform.system() == "Windows"

# Базовый набор приложений Windows, доступный без настройки конфига.
BUILTIN_APPS: dict[str, str] = {
    "блокнот": "notepad.exe",
    "notepad": "notepad.exe",
    "калькулятор": "calc.exe",
    "calculator": "calc.exe",
    "проводник": "explorer.exe",
    "explorer": "explorer.exe",
    "диспетчер задач": "taskmgr.exe",
    "task manager": "taskmgr.exe",
    "paint": "mspaint.exe",
    "терминал": "wt.exe",
    "cmd": "cmd.exe",
    "powershell": "powershell.exe",
    "браузер": "",
    "chrome": "chrome.exe",
    "spotify": "spotify.exe",
    "telegram": "telegram.exe",
    "steam": "steam.exe",
    "vs code": "code",
    "vscode": "code",
}


def _resolve(config: SkillsConfig, name: str) -> str | None:
    """Ищет команду запуска по имени приложения."""
    key = name.strip().lower()
    catalog = {**BUILTIN_APPS, **{k.lower(): v for k, v in config.apps.items()}}
    if key in catalog:
        return catalog[key]
    for alias, command in catalog.items():
        if key in alias or alias in key:
            return command
    return None


def open_app(config: SkillsConfig, name: str) -> str:
    """Запускает приложение по имени или псевдониму из конфига."""
    command = _resolve(config, name)
    if command is None:
        command = name.strip()
    if not command:
        import webbrowser

        webbrowser.open("https://www.google.com")
        return "Открываю браузер, сэр."
    # Защита от command injection: не пропускаем команды с метасимволами shell.
    if not _SAFE_CMD_RE.match(command):
        return f"Слишком хитрое имя «{name}», сэр. Не могу гарантировать безопасность."
    try:
        if IS_WINDOWS:
            os.startfile(command)  # type: ignore[attr-defined]
        elif shutil.which(command):
            subprocess.Popen([command], start_new_session=True)
        else:
            return f"Не нашёл приложение «{name}», сэр."
    except OSError as exc:
        return f"Не удалось запустить «{name}»: {exc}"
    return f"Запускаю {name}, сэр."


def close_app(name: str) -> str:
    """Закрывает процессы приложения по имени."""
    try:
        import psutil  # type: ignore[import-not-found]
    except ImportError:
        return "Модуль psutil не установлен, сэр."
    needle = name.strip().lower().removesuffix(".exe")
    if not needle:
        return "Уточните, что закрыть, сэр."
    killed = 0
    for process in psutil.process_iter(["name"]):
        process_name = (process.info.get("name") or "").lower().removesuffix(".exe")
        # Точное совпадение или совпадение полного имени процесса
        # (защита от ложных срабатываний: «chrome» не убьёт «chromedriver")
        if process_name == needle:
            try:
                process.terminate()
                killed += 1
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                continue
        elif needle in process_name and len(needle) >= 4:
            # Для коротких запросов (>=4 символа) допускаем подстроку,
            # но только если имена близки по длине (не более чем в 1.5 раза длиннее).
            if len(process_name) <= len(needle) * 1.5:
                try:
                    process.terminate()
                    killed += 1
                except (psutil.AccessDenied, psutil.NoSuchProcess):
                    continue
    if not killed:
        return f"Процессы «{name}» не найдены, сэр."
    return f"Закрыл {killed} процессов «{name}»."


def list_windows() -> str:
    """Перечисляет заголовки открытых окон."""
    if not IS_WINDOWS:
        return "Список окон доступен только в Windows, сэр."
    try:
        import pygetwindow  # type: ignore[import-not-found]
    except ImportError:
        return "Модуль pygetwindow не установлен, сэр."
    titles = [title for title in pygetwindow.getAllTitles() if title.strip()]
    if not titles:
        return "Открытых окон нет, сэр."
    return "Открытые окна: " + "; ".join(titles[:15]) + "."


def focus_window(title: str) -> str:
    """Разворачивает и активирует окно по части заголовка."""
    if not IS_WINDOWS:
        return "Управление окнами доступно только в Windows, сэр."
    try:
        import pygetwindow  # type: ignore[import-not-found]
    except ImportError:
        return "Модуль pygetwindow не установлен, сэр."
    matches = [
        window
        for window in pygetwindow.getAllWindows()
        if title.lower() in window.title.lower() and window.title.strip()
    ]
    if not matches:
        return f"Окно «{title}» не найдено, сэр."
    window = matches[0]
    if window.isMinimized:
        window.restore()
    window.activate()
    return f"Переключился на «{window.title}»."


def build_skills(config: SkillsConfig) -> list[Skill]:
    """Создаёт навыки работы с приложениями и окнами."""
    return [
        Skill(
            name="open_app",
            description="Запустить программу на компьютере по названию.",
            parameters=object_schema(
                {"name": {"type": "string", "description": "Название приложения"}},
                required=["name"],
            ),
            handler=lambda name: open_app(config, name),
        ),
        Skill(
            name="close_app",
            description="Закрыть программу по названию процесса.",
            parameters=object_schema(
                {"name": {"type": "string", "description": "Название приложения"}},
                required=["name"],
            ),
            handler=_confirm_handler(close_app, 'Закрыть все процессы "{name}"?'),
        ),
        Skill(
            name="list_windows",
            description="Показать заголовки открытых окон.",
            parameters=object_schema({}),
            handler=list_windows,
        ),
        Skill(
            name="focus_window",
            description="Переключиться на окно по части его заголовка.",
            parameters=object_schema(
                {"title": {"type": "string", "description": "Часть заголовка окна"}},
                required=["title"],
            ),
            handler=focus_window,
        ),
    ]
