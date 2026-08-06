"""Системные переменные: чтение и запись переменных окружения."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from .registry import Skill, object_schema

log = logging.getLogger(__name__)


# Защищённые переменные (нельзя менять через голос)
_PROTECTED = {
    "PATH", "SYSTEMROOT", "WINDIR", "HOME", "USERPROFILE",
    "PYTHONPATH", "PYTHONHOME", "LD_PRELOAD", "DYLD_INSERT_LIBRARIES",
}


def get_env(name: str = "") -> str:
    """Показать значение переменной окружения."""
    if not name.strip():
        # Показать все переменные (кратко)
        vars_list = sorted(os.environ.items())
        if not vars_list:
            return "Нет переменных окружения, сэр."
        lines = [f"Переменные окружения ({len(vars_list)}):"]
        for k, v in vars_list[:20]:
            lines.append(f"  {k}={v[:80]}")
        if len(vars_list) > 20:
            lines.append(f"  ... и ещё {len(vars_list) - 20}.")
        return "\n".join(lines)
    value = os.environ.get(name)
    if value is None:
        return f"Переменная {name} не найдена, сэр."
    return f"{name} = {value}"


def set_env(name: str, value: str) -> str:
    """Установить переменную окружения (только для текущего процесса)."""
    name = name.strip().upper()
    if name in _PROTECTED:
        return f"Переменная {name} защищена, сэр. Нельзя менять через голос."
    if not name:
        return "Укажите имя переменной, сэр."
    os.environ[name] = value
    return f"{name} = {value} (для текущего процесса)."


def get_path() -> str:
    """Показать содержимое PATH."""
    path = os.environ.get("PATH", "")
    dirs = path.split(os.pathsep)
    if not path.strip():
        return "PATH пуст, сэр."
    lines = [f"PATH ({len(dirs)} директорий):"]
    for d in dirs[:15]:
        exists = "OK" if Path(d).is_dir() else "НЕ НАЙДЕНА"
        lines.append(f"  [{exists}] {d}")
    if len(dirs) > 15:
        lines.append(f"  ... и ещё {len(dirs) - 15}.")
    return "\n".join(lines)


def build_skills() -> list:
    """Создаёт навыки для работы с переменными окружения."""
    from .registry import Skill
    return [
        Skill(
            name="get_env",
            description=(
                "Показать значение переменной окружения. "
                "Без аргументов — список всех переменных."
            ),
            parameters=object_schema(
                {
                    "name": {
                        "type": "string",
                        "description": "Имя переменной (пустое = показать все)",
                    },
                },
            ),
            handler=lambda name="": get_env(name),
        ),
        Skill(
            name="set_env",
            description=(
                "Установить переменную окружения для текущего процесса. "
                "Защищённые переменные (PATH, HOME и др.) изменить нельзя."
            ),
            parameters=object_schema(
                {
                    "name": {"type": "string", "description": "Имя переменной"},
                    "value": {"type": "string", "description": "Значение"},
                },
                required=["name", "value"],
            ),
            handler=set_env,
        ),
        Skill(
            name="get_path",
            description="Показать содержимое PATH с проверкой существования директорий.",
            parameters=object_schema({}),
            handler=get_path,
        ),
    ]
