"""Сохранение скриншотов в файл."""

from __future__ import annotations

import logging
import time
from pathlib import Path

from .registry import Skill, object_schema

log = logging.getLogger(__name__)


def screenshot_save(save_dir: str = "~/Pictures/Jarvis") -> str:
    """Делает скриншот и сохраняет в файл."""
    try:
        import mss
    except ImportError:
        return "mss не установлен. pip install mss, сэр."
    out = Path(save_dir).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    fname = f"screenshot_{int(time.time())}.png"
    fpath = out / fname
    try:
        with mss.mss() as sct:
            sct.shot(output=str(fpath))
        return f"Скриншот сохранён: {fpath}, сэр."
    except Exception as exc:
        return f"Ошибка: {exc}, сэр."


def build_skills(save_dir: str = "~/Pictures/Jarvis") -> list[Skill]:
    return [
        Skill(name="screenshot_save", description="Сделать скриншот и сохранить в файл.",
              parameters=object_schema({"directory": {"type": "string", "description": "Папка для сохранения"}}),
              handler=lambda directory=save_dir: screenshot_save(directory)),
    ]
