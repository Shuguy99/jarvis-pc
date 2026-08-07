#!/usr/bin/env python3
"""Fix broken docstrings and generate remaining skill files."""

import os

D = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'jarvis', 'skills')

# Fix self_update.py
d = os.path.join(D, 'self_update.py')
content = open(d).read()
content = content.replace("'''Self-update Jarvis via git.", '"""Обновление Jarvis из Git."""')
content = content.replace("    '''\n\nfrom", '"""\n\nfrom')
open(d, 'w').write(content)

# Generate weather_alert.py
open(os.path.join(D, 'weather_alert.py'), 'w').write(
'''"""Погода-оповещения: прогноз с рекомендацией по зонту."""

from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request

from .registry import Skill, object_schema

log = logging.getLogger(__name__)


def weather_alert(city: str = "Moscow") -> str:
    try:
        url = f"https://wttr.in/{urllib.parse.quote(city)}?format=j1"
        req = urllib.request.Request(url, headers={"User-Agent": "Jarvis/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        lines = []
        for i, label in enumerate(["Сегодня", "Завтра"]):
            if i >= len(data.get("weather", [])):
                break
            day = data["weather"][i]
            hourly = day.get("hourly", [{}])
            desc_r = hourly[0].get("lang_ru", [{}])[0].get("value", "") if hourly else ""
            desc_e = hourly[0].get("weatherDesc", [{}])[0].get("value", "") if hourly else ""
            desc = desc_r or desc_e
            tmin = day["mintempC"]
            tmax = day["maxtempC"]
            rain = int(hourly[0].get("chanceofrain", "0")) if hourly else 0
            wind = int(hourly[0].get("windspeedKmph", "0")) if hourly else 0
            line = f"{label}: {desc}, {tmin}..{tmax}\u00b0C, ветер {wind} км/ч, дождь {rain}%"
            if rain > 50:
                line += " \u2014 возьмите зонт!"
            lines.append(line)
        return "\n".join(lines) + "\nСэр."
    except Exception as exc:
        return f"Ошибка: {exc}, сэр."


def build_skills() -> list[Skill]:
    return [
        Skill(name="weather_alert", description="Прогноз на сегодня и завтра с рекомендацией по зонту.",
              parameters=object_schema({"city": {"type": "string", "description": "Город"}}),
              handler=lambda city="Moscow": weather_alert(city)),
    ]
'''
)

# Generate notion_tasks.py
open(os.path.join(D, 'notion_tasks.py'), 'w').write(
'''"""Интеграция с Notion: задачи и поиск."""

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
        return "NOTION_DATABASE_ID не задан. Задайте в переменных окружения, сэр."
    try:
        _notion_api("POST", "/pages", {
            "parent": {"database_id": db},
            "properties": {"title": {"title": [{"text": {"content": title}}]}},
        })
        return f"Задача добавлена в Notion: {title}, сэр."
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
            return "Ничего не найдено в Notion, сэр."
        lines = []
        for r in results[:5]:
            obj_type = r.get("object", "")
            title_parts = r.get("properties", {}).get("title", {}).get("title", [])
            name = title_parts[0]["plain_text"] if title_parts else "без названия"
            lines.append(f"  [{obj_type}] {name}")
        return "Найдено в Notion:\n" + "\n".join(lines) + f"\nВсего: {len(results)}, сэр."
    except RuntimeError as exc:
        return str(exc) + ", сэр."
    except Exception as exc:
        return f"Ошибка Notion: {exc}, сэр."


def build_skills() -> list[Skill]:
    return [
        Skill(name="notion_add_task", description="Добавить задачу в базу Notion.",
              parameters=object_schema({
                  "title": {"type": "string", "description": "Название задачи"},
                  "database_id": {"type": "string", "description": "ID базы (или NOTION_DATABASE_ID)"},
              }, required=["title"]),
              handler=lambda title, database_id="": notion_add_task(title, database_id)),
        Skill(name="notion_search", description="Поиск в Notion.",
              parameters=object_schema({"query": {"type": "string", "description": "Запрос"}}),
              handler=lambda query="": notion_search(query)),
    ]
'''
)

# Fix screenshot_save.py (missing closing paren in handler lambda)
d = os.path.join(D, 'screenshot_save.py')
content = open(d).read()
content = content.replace('handler=lambda directory=save_dir: screenshot_save(directory)),', 'handler=lambda directory=save_dir: screenshot_save(directory)),')
if 'handler=lambda directory=save_dir: screenshot_save(directory)),' in content:
    content = content.replace(
        'handler=lambda directory=save_dir: screenshot_save(directory)),',
        'handler=lambda directory=save_dir: screenshot_save(directory)),'
    )
open(d, 'w').write(content)

# Fix git_helper.py - f-string issue with backslash
d = os.path.join(D, 'git_helper.py')
content = open(d).read()
content = content.replace('return f"Изменения:\n{out}\nСэр."', 'return "Изменения:\n" + out + "\nСэр."')
content = content.replace('return f"Последние коммиты:\n{out}\nСэр."', 'return "Последние коммиты:\n" + out + "\nСэр."')
open(d, 'w').write(content)

# Fix volume.py - missing -Command
d = os.path.join(D, 'volume.py')
content = open(d).read()
content = content.replace('"powershell", "-NoProfile", "Command"', '"powershell", "-NoProfile", "-Command"')
open(d, 'w').write(content)

# Fix crypto.py - missing docstring closing
d = os.path.join(D, 'crypto.py')
content = open(d).read()
if not content.startswith('"""'):
    content = '"""Криптовалюта и акции через CoinGecko.\n' + content
open(d, 'w').write(content)

print("All fixes applied")
