generate the remaining skill files. 
Code: 

import os

D = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'jarvis', 'skills')

# code_snippets.py
open(os.path.join(D, 'code_snippets.py'), 'w').write('''"""Сниппеты: сохранение и поиск фрагментов кода."""

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
            pass
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
            matches.append(f"  {name}: {info[\"code\"][:100]}...")
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
              parameters=object_schema({"name": {"type": "string", "description": "Имя сниппета"}}, required=["name"]),
              handler=lambda name: get_snippet(name)),
    ]

''')

# email.py
open(os.path.join(D, 'email.py'), 'w').write('''"""Отправка email через SMTP."""

from __future__ import annotations

import logging
import smtplib
import os
from email.mime.text import MIMEText

from .registry import Skill, object_schema

log = logging.getLogger(__name__)


def send_email(to: str, subject: str, body: str, smtp_host: str = "", smtp_port: int = 587,
               login: str = "", password: str = "") -> str:
    host = smtp_host or os.environ.get("JARVIS_SMTP_HOST", "")
    port = smtp_port
    user = login or os.environ.get("JARVIS_SMTP_USER", "")
    pwd = password or os.environ.get("JARVIS_SMTP_PASS", "")
    if not host or not user:
        return "SMTP не настроен. Задайте JARVIS_SMTP_HOST/USER/PASS в окружении, сэр."
    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = user
        msg["To"] = to
        with smtplib.SMTP(host, port) as server:
            server.starttls()
            server.login(user, pwd)
            server.send_message(msg)
        return f"Письмо отправлено на {to}, сэр."
    except Exception as exc:
        return f"Ошибка отправки: {exc}, сэр."


def build_skills() -> list[Skill]:
    return [
        Skill(name="send_email", description="Отправить email.",
              parameters=object_schema({
                  "to": {"type": "string", "description": "Адрес получателя"},
                  "subject": {"type": "string", "description": "Тема"},
                  "body": {"type": "string", "description": "Текст письма"},
              }, required=["to", "subject", "body"]),
              handler=lambda to, subject, body, smtp_host="", smtp_port=587, login="", password="": send_email(to, subject, body, smtp_host, smtp_port, login, password)),
    ]

''')

# self_update.py
open(os.path.join(D, 'self_update.py'), 'w').write('''"""Автообновление Jarvis из Git."""

from __future__ import annotations

import logging
import subprocess

from .registry import Skill, object_schema

log = logging.getLogger(__name__)


def self_update() -> str:
    try:
        r = subprocess.run(["git", "pull", "--rebase"], capture_output=True, text=True, check=False, timeout=30)
        if r.returncode != 0:
            return f"Ошибка обновления: {r.stderr.strip()}, сэр."
        msg = r.stdout.strip() or "Обновлений нет"
        return f"Обновление: {msg}, сэр."
    except FileNotFoundError:
        return "git не установлен, сэр."
    except Exception as exc:
        return f"Ошибка: {exc}, сэр."


def current_version() -> str:
    try:
        r = subprocess.run(["git", "log", "-1", "--oneline"], capture_output=True, text=True, timeout=5)
        if r.stdout.strip():
            return f"Версия: {r.stdout.strip()}, сэр."
        return "Не удалось определить версию, сэр."
    except Exception:
        return "git недоступен, сэр."


def build_skills() -> list[Skill]:
    return [
        Skill(name="self_update", description="Обновить Jarvis из git (git pull).",
              parameters=object_schema({}), handler=self_update),
        Skill(name="current_version", description="Показать текущую версию/коммит Jarvis.",
              parameters=object_schema({}), handler=current_version),
    ]

''')

# weather_alert.py
open(os.path.join(D, 'weather_alert.py'), 'w').write('''"""Погода-оповещения: прогноз на завтра, нужен ли зонт."""

from __future__ import annotations

import json
import logging
import urllib.request

from .registry import Skill, object_schema

log = logging.getLogger(__name__)


def weather_alert(city: str = "Moscow") -> str:
    try:
        url = f"https://wttr.in/{urllib.parse.quote(city)}?format=j1"
        req = urllib.request.Request(url, headers={"User-Agent": "Jarvis/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        today = data["weather"][0]
        tomorrow = data["weather"][1] if len(data["weather"]) > 1 else today
        alerts = []
        for day, label in [(today, "Сегодня"), (tomorrow, "Завтра")]:
            desc = day.get("hourly", [{}])[0].get("lang_ru", {}).get("value", day.get("hourly", [{}])[0].get("weatherDesc", [{}])[0].get("value", ""))
            temp_min = day["mintempC"]
            temp_max = day["maxtempC"]
            rain = int(day.get("hourly", [{}])[0].get("chanceofrain", "0"))
            if rain > 50:
                alerts.append(f"{label}: {desc}, {temp_min}..{temp_max}°C, шанс дождя {rain}% - возьмите зонт!")
            else:
                alerts.append(f"{label}: {desc}, {temp_min}..{temp_max}°C, дождь {rain}%")
        return "\n".join(alerts) + "\nСэр."
    except Exception as exc:
        return f"Ошибка: {exc}, сэр."


def build_skills() -> list[Skill]:
    return [
        Skill(name="weather_alert", description="Прогноз погоды на сегодня и завтра с оповещением о дожде.",
              parameters=object_schema({"city": {"type": "string", "description": "Город"}}),
              handler=lambda city="Moscow": weather_alert(city)),
    ]

''')

# notion_tasks.py
open(os.path.join(D, 'notion_tasks.py'), 'w').write('''"""Интеграция с Notion: добавление задач."""

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
        return "NOTION_DATABASE_ID не задан. Задайте в окружении, сэр."
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
              parameters=object_schema({"query": {"type": "string", "description": "Поисковый запрос"}}),
              handler=lambda query="": notion_search(query)),
    ]

''')

print("Done: 5 files generated")
