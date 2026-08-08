"""Обновление Jarvis из Git."""

from __future__ import annotations

import logging
import subprocess

from .registry import Skill, _confirm_handler, object_schema

log = logging.getLogger(__name__)


def self_update() -> str:
    try:
        r = subprocess.run(["git", "pull", "--rebase"], capture_output=True, text=True, check=False, timeout=30)
        if r.returncode != 0:
            return f"Ошибка: {r.stderr.strip()}, сэр."
        return f"Обновление: {r.stdout.strip() or 'уже актуален'}, сэр."
    except FileNotFoundError:
        return "git не установлен, сэр."
    except Exception as exc:
        return f"Ошибка: {exc}, сэр."


def current_version() -> str:
    try:
        r = subprocess.run(["git", "log", "-1", "--oneline"], capture_output=True, text=True, timeout=5)
        return f"Версия: {r.stdout.strip()}, сэр." if r.stdout.strip() else "Не удалось определить, сэр."
    except Exception:
        log.debug("self_update: ошибка (line 29), используем fallback")
        return "git недоступен, сэр."


def build_skills() -> list[Skill]:
    return [
        Skill(name="self_update", description="Обновить Jarvis из git (git pull).",
              parameters=object_schema({}), handler=_confirm_handler(self_update, 'Обновить Jarvis из git (git pull --rebase)?')),
        Skill(name="current_version", description="Текущая версия/коммит Jarvis.",
              parameters=object_schema({}), handler=current_version),
    ]
