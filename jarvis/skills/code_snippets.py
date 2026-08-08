"""Сниппеты: сохранение и поиск фрагментов кода."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from .registry import Skill, object_schema

log = logging.getLogger(__name__)

_SNIPPETS_FILE = Path.home() / ".jarvis" / "snippets.json"


def _load() -> dict:
    if _SNIPPETS_FILE.exists():
        try:
            return json.loads(_SNIPPETS_FILE.read_text(encoding="utf-8"))
        except Exception:
            log.debug("code_snippets: не критичная ошибка при return json.loads(_SNIPPETS_FILE.read_text(encodin")
    return {}


def _save(data: dict) -> None:
    _SNIPPETS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _SNIPPETS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def save_snippet(name: str, code: str, tags: str = "") -> str:
    data = _load()
    data[name] = {"code": code, "tags": [t.strip() for t in tags.split(",") if t.strip()]}
    _save(data)
    return f"Сниппет \u00ab{name}\u00bb сохранён, сэр."


def search_snippets(query: str) -> str:
    data = _load()
    if not data:
        return "Нет сохранённых сниппетов, сэр."
    q = query.lower()
    matches = []
    for name, info in data.items():
        if q in name.lower() or q in info["code"].lower() or any(q in t.lower() for t in info.get("tags", [])):
            matches.append(f"  {name}: {info['code'][:100]}...")
    if not matches:
        return f"По запросу \u00ab{query}\u00bb ничего не найдено, сэр."
    return "Найденные сниппеты:\n" + "\n".join(matches) + "\nСэр."


def list_snippets() -> str:
    data = _load()
    if not data:
        return "Нет сохранённых сниппетов, сэр."
    lines = [f"  {name}" for name in data]
    return "Сниппеты:\n" + "\n".join(lines) + f"\nВсего: {len(data)}, сэр."


def get_snippet(name: str) -> str:
    data = _load()
    if name not in data:
        return f"Сниппет \u00ab{name}\u00bb не найден, сэр."
    return data[name]["code"]


def build_skills() -> list[Skill]:
    return [
        Skill(name="save_snippet", description="Сохранить фрагмент кода с именем и тегами.",
              parameters=object_schema({"name": {"type": "string", "description": "Имя"}, "code": {"type": "string", "description": "Код"}, "tags": {"type": "string", "description": "Теги через запятую"}}, required=["name", "code"]),
              handler=lambda name, code, tags="": save_snippet(name, code, tags)),
        Skill(name="search_snippets", description="Найти сниппет по запросу.",
              parameters=object_schema({"query": {"type": "string", "description": "Поиск"}}, required=["query"]),
              handler=lambda query: search_snippets(query)),
        Skill(name="list_snippets", description="Показать все сохранённые сниппеты.",
              parameters=object_schema({}), handler=list_snippets),
        Skill(name="get_snippet", description="Получить код сниппета по имени.",
              parameters=object_schema({"name": {"type": "string", "description": "Имя"}}, required=["name"]),
              handler=lambda name: get_snippet(name)),
    ]
