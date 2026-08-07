"""Работа с буфером обмена."""

from __future__ import annotations

import logging

from .registry import Skill, object_schema

log = logging.getLogger(__name__)


def _get() -> str:
    try:
        import pyperclip
        return pyperclip.paste() or ""
    except Exception as exc:
        log.warning("pyperclip: %s", exc)
        return ""


def _set(text: str) -> bool:
    try:
        import pyperclip
        pyperclip.copy(text)
        return True
    except Exception as exc:
        log.warning("pyperclip: %s", exc)
        return False


def get_clipboard() -> str:
    text = _get()
    if not text:
        return "Буфер обмена пуст, сэр."
    preview = text[:500] if len(text) > 500 else text
    return f"В буфере: {preview}, сэр."


def set_clipboard(text: str) -> str:
    return "Скопировано в буфер, сэр." if _set(text) else "Не удалось записать, сэр."


def clear_clipboard() -> str:
    return "Буфер очищен, сэр." if _set("") else "Не удалось очистить, сэр."


def build_skills() -> list[Skill]:
    return [
        Skill(name="get_clipboard", description="Показать содержимое буфера обмена.",
              parameters=object_schema({}), handler=get_clipboard),
        Skill(name="set_clipboard", description="Скопировать текст в буфер обмена.",
              parameters=object_schema({"text": {"type": "string", "description": "Текст"}}, required=["text"]),
              handler=lambda text: set_clipboard(text)),
        Skill(name="clear_clipboard", description="Очистить буфер обмена.",
              parameters=object_schema({}), handler=clear_clipboard),
    ]
