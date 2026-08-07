#!/usr/bin/env python3
"""Fix the 4 broken files."""

import os

D = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'jarvis', 'skills')

# 1. crypto.py - docstring unclosed
open(os.path.join(D, 'crypto.py'), 'w').write(
'''"""Криптовалюта и акции через CoinGecko."""

from __future__ import annotations

import json
import logging
import urllib.request

from .registry import Skill, object_schema

log = logging.getLogger(__name__)
_API = "https://api.coingecko.com/api/v3"


def _fetch(path: str) -> dict:
    url = f"{_API}{path}"
    req = urllib.request.Request(url, headers={"User-Agent": "Jarvis/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def crypto_price(coin: str = "bitcoin") -> str:
    try:
        data = _fetch(f"/simple/price?ids={coin}&vs_currencies=usd,rub&include_24hr_change=true")
        if coin not in data:
            return f"Монета {coin} не найдена, сэр."
        info = data[coin]
        usd = info.get("usd", "?")
        rub = info.get("rub", "?")
        change = info.get("usd_24h_change")
        change_str = f" ({change:+.2f}% за 24ч)" if change is not None else ""
        return f"{coin.title()}: ${usd} / {rub}руб{change_str}, сэр."
    except Exception as exc:
        return f"Ошибка: {exc}, сэр."


def crypto_list(top: int = 10) -> str:
    try:
        data = _fetch(f"/coins/markets?vs_currency=usd&order=market_cap_desc&per_page={min(top, 50)}&page=1")
        lines = ["Топ криптовалют:"]
        for c in data:
            lines.append(f"  {c['name']} ({c['symbol']}): ${c['current_price']:.2f}")
        return "\n".join(lines) + "\nСэр."
    except Exception as exc:
        return f"Ошибка: {exc}, сэр."


def stock_price(symbol: str = "AAPL") -> str:
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol.upper()}?range=1d&interval=1d"
        req = urllib.request.Request(url, headers={"User-Agent": "Jarvis/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        meta = data["chart"]["result"][0]["meta"]
        price = meta.get("regularMarketPrice", "?")
        prev = meta.get("previousClose", "?")
        name = meta.get("symbol", symbol)
        return f"{name}: ${price} (вчера: ${prev}), сэр."
    except Exception:
        return f"Не удалось получить данные по {symbol}, сэр."


def build_skills() -> list[Skill]:
    return [
        Skill(name="crypto_price", description="Цена криптовалюты в USD и RUB.",
              parameters=object_schema({"coin": {"type": "string", "description": "ID монеты"}}),
              handler=lambda coin="bitcoin": crypto_price(coin)),
        Skill(name="crypto_list", description="Топ криптовалют по капитализации.",
              parameters=object_schema({"top": {"type": "integer", "description": "Количество"}}),
              handler=lambda top=10: crypto_list(top)),
        Skill(name="stock_price", description="Цена акции по тикеру.",
              parameters=object_schema({"symbol": {"type": "string", "description": "Тикер"}}, required=["symbol"]),
              handler=lambda symbol: stock_price(symbol)),
    ]
'''
)

# 2. git_helper.py
open(os.path.join(D, 'git_helper.py'), 'w').write(
'''"""Git-операции: коммит, пуш, статус, лог."""

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
    return "Изменения:\n" + out + "\nСэр."


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
    return "Последние коммиты:\n" + out + "\nСэр."


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
'''
)

# 3. weather_alert.py
open(os.path.join(D, 'weather_alert.py'), 'w').write(
'''"""Погода-оповещения: прогноз с рекомендацией."""

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
            line = f"{label}: {desc}, {tmin}..{tmax} C, ветер {wind} км/ч, дождь {rain}%"
            if rain > 50:
                line += " - возьмите зонт!"
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

# 4. notion_tasks.py
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
            tp = r.get("properties", {}).get("title", {}).get("title", [])
            name = tp[0]["plain_text"] if tp else "без названия"
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
                  "database_id": {"type": "string", "description": "ID базы"},
              }, required=["title"]),
              handler=lambda title, database_id="": notion_add_task(title, database_id)),
        Skill(name="notion_search", description="Поиск в Notion.",
              parameters=object_schema({"query": {"type": "string", "description": "Запрос"}}),
              handler=lambda query="": notion_search(query)),
    ]
'''
)

print("Done: 4 files rewritten")
