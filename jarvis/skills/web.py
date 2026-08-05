"""Навыки работы с вебом: поиск, открытие ссылок, погода, короткие справки."""

from __future__ import annotations

import urllib.parse
import webbrowser
from typing import Any

from ..config import SkillsConfig
from .registry import Skill, object_schema

WEATHER_URL = "https://wttr.in/{city}?format=j1"
HTTP_TIMEOUT_S = 10


def web_search(config: SkillsConfig, query: str) -> str:
    """Открывает поиск в браузере по умолчанию."""
    if not query.strip():
        return "Что искать, сэр?"
    url = config.search_engine.format(query=urllib.parse.quote(query))
    webbrowser.open(url)
    return f"Ищу «{query}», сэр."


def open_url(url: str) -> str:
    """Открывает произвольный адрес в браузере."""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    webbrowser.open(url)
    return f"Открываю {url}."


def weather(city: str = "Moscow") -> str:
    """Возвращает текущую погоду через открытый сервис wttr.in."""
    try:
        import requests  # type: ignore[import-not-found]
    except ImportError:
        return "Модуль requests не установлен, сэр."
    response = requests.get(
        WEATHER_URL.format(city=urllib.parse.quote(city)), timeout=HTTP_TIMEOUT_S
    )
    response.raise_for_status()
    current = response.json()["current_condition"][0]
    description = current["lang_ru"][0]["value"] if "lang_ru" in current else ""
    if not description:
        description = current["weatherDesc"][0]["value"]
    return (
        f"В городе {city}: {description.lower()}, {current['temp_C']} градусов, "
        f"ощущается как {current['FeelsLikeC']}, ветер {current['windspeedKmph']} км/ч."
    )


def fetch_summary(query: str) -> str:
    """Короткая справка из Википедии по запросу."""
    try:
        import requests  # type: ignore[import-not-found]
    except ImportError:
        return "Модуль requests не установлен, сэр."
    params: dict[str, str | int] = {
        "action": "query",
        "list": "search",
        "srsearch": query,
        "format": "json",
        "srlimit": 1,
    }
    search = requests.get(
        "https://ru.wikipedia.org/w/api.php",
        params=params,
        timeout=HTTP_TIMEOUT_S,
        headers={"User-Agent": "JarvisAssistant/1.0"},
    )
    search.raise_for_status()
    hits: list[dict[str, Any]] = search.json().get("query", {}).get("search", [])
    if not hits:
        return f"По запросу «{query}» ничего не нашёл, сэр."
    title = hits[0]["title"]
    summary = requests.get(
        "https://ru.wikipedia.org/api/rest_v1/page/summary/"
        + urllib.parse.quote(title.replace(" ", "_")),
        timeout=HTTP_TIMEOUT_S,
        headers={"User-Agent": "JarvisAssistant/1.0"},
    )
    summary.raise_for_status()
    extract = summary.json().get("extract", "")
    return extract or f"Нашёл статью «{title}», но выжимки нет, сэр."


def build_skills(config: SkillsConfig) -> list[Skill]:
    """Создаёт веб-навыки."""
    return [
        Skill(
            name="web_search",
            description="Открыть поиск в браузере по запросу пользователя.",
            parameters=object_schema(
                {"query": {"type": "string", "description": "Поисковый запрос"}},
                required=["query"],
            ),
            handler=lambda query: web_search(config, query),
        ),
        Skill(
            name="open_url",
            description="Открыть конкретный сайт в браузере.",
            parameters=object_schema(
                {"url": {"type": "string", "description": "Адрес сайта"}},
                required=["url"],
            ),
            handler=open_url,
        ),
        Skill(
            name="weather",
            description="Узнать текущую погоду в городе.",
            parameters=object_schema(
                {"city": {"type": "string", "description": "Название города"}}
            ),
            handler=weather,
        ),
        Skill(
            name="fetch_summary",
            description="Получить краткую справку из Википедии по теме.",
            parameters=object_schema(
                {"query": {"type": "string", "description": "Тема запроса"}},
                required=["query"],
            ),
            handler=fetch_summary,
        ),
    ]
