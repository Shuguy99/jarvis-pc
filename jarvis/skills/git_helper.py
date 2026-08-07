"""Git-операции: коммит, пуш, статус, лог."""

from __future__ import annotations

import logging
import subprocess

from .registry import Skill, object_schema

log = logging.getLogger(__name__)


def _git(args: list[str], cwd: str = ".") -> str:
    try:
        r = subprocess.run(["git"] + args, capture_output=True, text=True, check=False, timeout=30, cwd=cwd)
        if r.returncode != 0:
            return f"git ошибка: {r.stderr.strip() or r.stdout.strip()}, сэр."
        return (r.stdout.strip() or r.stderr.strip()) or "Готово, сэр."
    except FileNotFoundError:
        return "git не установлен, сэр."
    except Exception as exc:
        return f"Ошибка: {exc}, сэр."


def git_status(cwd: str = ".") -> str:
    out = _git(["status", "--short"], cwd)
    if not out or out == "Готово, сэр.":
        return "Рабочая директория чиста, сэр."
    return "Изменения:" + chr(10) + out + chr(10) + "Сэр."


def git_commit(message: str, cwd: str = ".") -> str:
    add = _git(["add", "-A"], cwd)
    if "ошибка" in add.lower():
        return add
    return _git(["commit", "-m", message], cwd)


def git_push(cwd: str = ".") -> str:
    return _git(["push"], cwd)


def git_log(n: int = 5, cwd: str = ".") -> str:
    out = _git(["log", "--oneline", f"-{n}"], cwd)
    if not out or out == "Готово, сэр.":
        return "Нет коммитов, сэр."
    return "Последние коммиты:" + chr(10) + out + chr(10) + "Сэр."


def git_branch() -> str:
    return _git(["branch", "--show-current"])


def build_skills() -> list[Skill]:
    return [
        Skill(name="git_status", description="Статус git-репозитория.",
              parameters=object_schema({"cwd": {"type": "string", "description": "Путь"}}),
              handler=lambda cwd=".": git_status(cwd)),
        Skill(name="git_commit", description="git add -A + commit.",
              parameters=object_schema({"message": {"type": "string", "description": "Сообщение"}, "cwd": {"type": "string", "description": "Путь"}}, required=["message"]),
              handler=lambda message, cwd=".": git_commit(message, cwd)),
        Skill(name="git_push", description="git push.",
              parameters=object_schema({"cwd": {"type": "string", "description": "Путь"}}),
              handler=lambda cwd=".": git_push(cwd)),
        Skill(name="git_log", description="Последние коммиты.",
              parameters=object_schema({"n": {"type": "integer", "description": "Количество"}}),
              handler=lambda n=5: git_log(n)),
        Skill(name="git_branch", description="Текущая ветка.",
              parameters=object_schema({}), handler=git_branch),
    ]
