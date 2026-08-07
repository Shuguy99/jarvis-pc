"""Интеграция с Notion: задачи и поиск."""

from __future__ import annotations

import json
import logging
import os
import urllib.request

from .registry import Skill, object_schema

log = logging.getLogger(__name__)


def _notion_api(method: str, path: str, body: dict | None = None) -> dict:
    token = os.environ.get("NOTION_API_KEY", "")
    if not token:
        raise RuntimeError("NOTION_API_KEY не задан")
    url = f"https://api.notion.com/v1{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method,
                                headers={"Authorization": f"Bearer {token}",
                                         "Content-Type": "application/json",
                                         "Notion-Version": "2022-06-28"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def notion_add_task(title: str, database_id: str = "") -> str:
    db = database_id or os.environ.get("NOTION_DATABASE_ID", "")
    if not db:
        return "NOTION_DATABASE_ID не задан, сэр."
    try:
        _notion_api("POST", "/pages", {
            "parent": {"database_id": db},
            "properties": {"title": {"title": [{"text": {"content": title}}]}},
        })
        return f"Задача добавлена: {title}, сэр."
    except RuntimeError as exc:
        return str(exc) + ", сэр."
    except Exception as exc:
        return f"Ошибка Notion: {exc}, сэр."


def notion_search(query: str = "") -> str:
    try:
        body = {"query": query} if query else {}
        data = _notion_api("POST", "/search", body)
        results = data.get("results", [])
        if not results:
            return "Ничего не найдено, сэр."
        parts = []
        for r in results[:5]:
            obj_type = r.get("object", "")
            tp = r.get("properties", {}).get("title", {}).get("title", [])
            name = tp[0]["plain_text"] if tp else "без названия"
            parts.append(f"  [{obj_type}] {name}")
        return "Найдено:" + chr(10) + chr(10).join(parts) + chr(10) + f"Всего: {len(results)}, сэр."
    except RuntimeError as exc:
        return str(exc) + ", сэр."
    except Exception as exc:
        return f"Ошибка Notion: {exc}, сэр."


def build_skills() -> list[Skill]:
    return [
        Skill(name="notion_add_task", description="Добавить задачу в Notion.",
              parameters=object_schema({
                  "title": {"type": "string", "description": "Название"},
                  "database_id": {"type": "string", "description": "ID базы"},
              }, required=["title"]),
              handler=lambda title, database_id="": notion_add_task(title, database_id)),
        Skill(name="notion_search", description="Поиск в Notion.",
              parameters=object_schema({"query": {"type": "string", "description": "Запрос"}}),
              handler=lambda query="": notion_search(query)),
    ]
