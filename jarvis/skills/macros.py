from __future__ import annotations

import json
import logging
import platform
import time
from pathlib import Path

from .registry import Skill, object_schema

log = logging.getLogger(__name__)

IS_WINDOWS = platform.system() == "Windows"
_MACROS_DIR = Path.home() / ".jarvis" / "macros"


def _get_macros_dir() -> Path:
    _MACROS_DIR.mkdir(parents=True, exist_ok=True)
    return _MACROS_DIR


def _press_key(key: str) -> None:
    """Нажимает одну клавишу."""
    try:
        import pyautogui  # type: ignore[import-not-found]
        pyautogui.press(key)
    except ImportError:
        if IS_WINDOWS:
            import ctypes
            VK_MAP = {
                "enter": 0x0D, "tab": 0x09, "escape": 0x1B,
                "space": 0x20, "backspace": 0x08, "delete": 0x2E,
            }
            vk = VK_MAP.get(key.lower())
            if vk:
                ctypes.windll.user32.keybd_event(vk, 0, 0, 0)  # type: ignore[attr-defined]
                ctypes.windll.user32.keybd_event(vk, 0, 2, 0)  # type: ignore[attr-defined]
        else:
            import shutil, subprocess
            if shutil.which("xdotool"):
                subprocess.run(["xdotool", "key", key], check=False, timeout=3)


def _type_text(text: str, delay: float = 0.05) -> None:
    """Печатает текст посимвольно."""
    try:
        import pyautogui  # type: ignore[import-not-found]
        pyautogui.typewrite(text, interval=delay)
    except ImportError:
        import shutil, subprocess
        if shutil.which("xdotool"):
            subprocess.run(["xdotool", "type", "--delay", str(int(delay * 1000)), text],
                           check=False, timeout=10)


def _execute_macro(actions: list[dict], speed: float = 1.0) -> str:
    """Воспроизводит список действий."""
    for action in actions:
        kind = action.get("type", "")
        if kind == "key":
            _press_key(action["key"])
        elif kind == "text":
            _type_text(action["text"])
        elif kind == "delay":
            time.sleep(action.get("ms", 100) / 1000.0 / max(speed, 0.1))
        elif kind == "combo":
            try:
                import pyautogui  # type: ignore[import-not-found]
                pyautogui.hotkey(*action["keys"])
            except ImportError:
                pass
    return f"Макрос выполнен ({len(actions)} действий)."


def play_macro(name: str, speed: float = 1.0) -> str:
    """Воспроизводит сохранённый макрос."""
    safe_name = name.replace(" ", "_").lower()
    path = _get_macros_dir() / f"{safe_name}.json"
    if not path.exists():
        return f"Макрос '{name}' не найден, сэр."
    try:
        actions = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return f"Ошибка чтения макроса: {exc}, сэр."
    return _execute_macro(actions, speed)


def list_macros() -> str:
    """Показывает список сохранённых макросов."""
    macros_dir = _get_macros_dir()
    files = list(macros_dir.glob("*.json"))
    if not files:
        return "Нет сохранённых макросов, сэр."
    lines = [f"Макросы ({len(files)}):"]
    for f in sorted(files):
        try:
            actions = json.loads(f.read_text(encoding="utf-8"))
            count = len(actions)
        except Exception:
            log.debug("macros: ошибка (line 99)")
            count = "?"
        lines.append(f"  {f.stem} ({count} действий)")
    return "\n".join(lines)


def delete_macro(name: str) -> str:
    """Удаляет макрос."""
    safe_name = name.replace(" ", "_").lower()
    path = _get_macros_dir() / f"{safe_name}.json"
    if not path.exists():
        return f"Макрос '{name}' не найден, сэр."
    path.unlink()
    return f"Макрос '{name}' удалён."


def type_text(text: str) -> str:
    """Напечатать текст как с клавиатуры."""
    _type_text(text)
    return f"Напечатал {len(text)} символов, сэр."


def press_key(key: str) -> str:
    """Нажать одну клавишу."""
    _press_key(key)
    return f"Нажал {key}, сэр."


def build_skills() -> list[Skill]:
    """Создаёт навыки макросов."""
    return [
        Skill(
            name="play_macro",
            description="Воспроизвести сохранённый макрос по имени.",
            parameters=object_schema(
                {
                    "name": {"type": "string", "description": "Имя макроса"},
                    "speed": {"type": "number", "description": "Скорость воспроизведения"},
                },
                required=["name"],
            ),
            handler=lambda name, speed=1.0: play_macro(name, speed),
        ),
        Skill(
            name="list_macros",
            description="Показать список сохранённых макросов.",
            parameters=object_schema({}),
            handler=list_macros,
        ),
        Skill(
            name="delete_macro",
            description="Удалить макрос.",
            parameters=object_schema(
                {
                    "name": {"type": "string", "description": "Имя макроса"},
                },
                required=["name"],
            ),
            handler=delete_macro,
        ),
        Skill(
            name="type_text",
            description="Напечатать текст как с клавиатуры (посимвольно).",
            parameters=object_schema(
                {
                    "text": {"type": "string", "description": "Текст для ввода"},
                },
                required=["text"],
            ),
            handler=type_text,
        ),
        Skill(
            name="press_key",
            description="Нажать одну клавишу (enter, tab, escape, space).",
            parameters=object_schema(
                {
                    "key": {"type": "string", "description": "Имя клавиши"},
                },
                required=["key"],
            ),
            handler=press_key,
        ),
    ]
