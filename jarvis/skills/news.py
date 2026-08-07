"""RSS / Новости: заголовки из заданных лент."""

from __future__ import annotations

import logging
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime

from ..config import NewsConfig
from .registry import Skill, object_schema

log = logging.getLogger(__name__)

_DEFAULT_FEEDS: list[dict[str, str]] = [
    {"url": "https://habr.com/ru/rss/best/daily/", "name": "Habr"},
    {"url": "https://hnrss.org/frontpage", "name": "Hacker News"},
    {"url": "https://lenta.ru/rss", "name": "Лента.ру"},
]


def _fetch_feed(feed_url: str, timeout: int = 10) -> list[dict[str, str]]:
    """Скачивает и парсит RSS/Atom ленту. Возвращает список {title, link, date}."""
    headers = {"User-Agent": "JarvisAssistant/1.0"}
    req = urllib.request.Request(feed_url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
    except Exception as exc:
        log.warning("Не удалось загрузить %s: %s", feed_url, exc)
        return []

    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        log.warning("Ошибка парсинга XML от %s: %s", feed_url, exc)
        return []

    items: list[dict[str, str]] = []
    # RSS 2.0
    for entry in root.iter("item"):
        title_el = entry.find("title")
        link_el = entry.find("link")
        date_el = entry.find("pubDate")
        if title_el is not None and title_el.text:
            items.append({
                "title": title_el.text.strip(),
                "link": (link_el.text or "").strip(),
                "date": (date_el.text or "").strip(),
            })
    if items:
        return items

    # Atom
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    for entry in root.findall(".//atom:entry", ns):
        title_el = entry.find("atom:title", ns)
        link_el = entry.find("atom:link", ns)
        date_el = entry.find("atom:published", ns) or entry.find("atom:updated", ns)
        if title_el is not None and title_el.text:
            href = link_el.get("href", "") if link_el is not None else ""
            items.append({
                "title": title_el.text.strip(),
                "link": href.strip(),
                "date": (date_el.text or "").strip() if date_el is not None else "",
            })
    return items


def _strip_html(text: str) -> str:
    """Убирает HTML-теги из текста."""
    return re.sub(r"<[^>]+>", "", text).strip()


def _format_date(date_str: str) -> str:
    """Пытается привести дату к читаемому виду."""
    if not date_str:
        return ""
    # RSS форматы: "Wed, 07 Aug 2024 12:00:00 +0000" или ISO
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            return dt.strftime("%d.%m %H:%M")
        except ValueError:
            continue
    return date_str[:16]


def get_news(config: NewsConfig, feed_name: str = "", count: int = 5) -> str:
    """Получает заголовки из RSS лент."""
    feeds = config.feeds if config.feeds else _DEFAULT_FEEDS
    if feed_name:
        feeds = [f for f in feeds if feed_name.lower() in f["name"].lower()]
        if not feeds:
            available = ", ".join(f["name"] for f in (config.feeds or _DEFAULT_FEEDS))
            return f"Лента '{feed_name}' не найдена. Доступные: {available}, сэр."

    all_items: list[dict[str, str]] = []
    lines = []
    for feed in feeds[:5]:  # максимум 5 лент за раз
        items = _fetch_feed(feed["url"])
        if items:
            all_items.extend(items)
            name = feed.get("name", feed["url"])
            lines.append(f"--- {name} ({len(items)} статей) ---")
            for item in items[:count]:
                title = _strip_html(item["title"])[:80]
                date_str = _format_date(item["date"])
                date_prefix = f"[{date_str}] " if date_str else ""
                lines.append(f"  {date_prefix}{title}")
        else:
            lines.append(f"--- {feed.get('name', '?')} — не удалось загрузить ---")

    if not all_items:
        return "Не удалось загрузить новости, сэр. Проверьте интернет, сэр."
    return "\n".join(lines)


def add_feed(config: NewsConfig, name: str, url: str) -> str:
    """Добавляет RSS ленту в конфиг (в памяти, не сохраняет)."""
    for f in config.feeds:
        if f["url"] == url:
            return f"Лента {name} уже есть, сэр."
    config.feeds.append({"name": name, "url": url})
    return f"Лента '{name}' добавлена, сэр."


def list_feeds(config: NewsConfig) -> str:
    """Показывает настроенные ленты."""
    feeds = config.feeds if config.feeds else _DEFAULT_FEEDS
    lines = ["Настроенные RSS ленты:"]
    for f in feeds:
        lines.append(f"  {f['name']}: {f['url']}")
    return "\n".join(lines)


def build_skills(config: NewsConfig) -> list[Skill]:
    """Создаёт навыки новостей."""
    return [
        Skill(
            name="get_news",
            description="Показать заголовки из RSS лент (Habr, Hacker News и др.).",
            parameters=object_schema(
                {
                    "feed_name": {
                        "type": "string",
                        "description": "Название ленты (пусто = все)",
                    },
                    "count": {
                        "type": "integer",
                        "description": "Сколько заголовков (по умолчанию 5)",
                    },
                },
            ),
            handler=lambda feed_name="", count=5: get_news(config, feed_name, count),
        ),
        Skill(
            name="add_feed",
            description="Добавить RSS ленту по имени и URL.",
            parameters=object_schema(
                {
                    "name": {"type": "string", "description": "Название ленты"},
                    "url": {"type": "string", "description": "URL RSS/Atom"},
                },
                required=["name", "url"],
            ),
            handler=lambda name, url: add_feed(config, name, url),
        ),
        Skill(
            name="list_feeds",
            description="Показать список настроенных RSS лент.",
            parameters=object_schema({}),
            handler=lambda: list_feeds(config),
        ),
    ]
