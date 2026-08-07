from __future__ import annotations

import logging
import re
import urllib.parse
import webbrowser
from typing import Any

from ..config import SkillsConfig
from .registry import Skill, object_schema

HTTP_TIMEOUT_S = 10
DDG_LITE_URL = "https://lite.duckduckgo.com/lite/"
MAX_RESULTS = 5

log = logging.getLogger(__name__)

# Хранилище последнего поискового запроса для open_in_browser.
_last_search_url: str = ""


# ── DuckDuckGo парсер ─────────────────────────────────────────────────


def _fetch_ddg_results(query: str) -> list[dict[str, str]]:
    """Получает результаты поиска из DuckDuckGo Lite (HTML).

    Возвращает список словарей {"title", "snippet", "url"}.
    При ошибке возвращает пустой список.
    """
    try:
        import requests  # type: ignore[import-not-found]
    except ImportError:
        return []
    try:
        resp = requests.get(
            DDG_LITE_URL,
            params={"q": query},
            timeout=HTTP_TIMEOUT_S,
            headers={
                "User-Agent": "JarvisAssistant/1.0",
                "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
            },
        )
        resp.raise_for_status()
    except Exception:
        log.warning("DuckDuckGo Lite не ответил на запрос: %s", query)
        return []
    return _parse_ddg_html(resp.text)


def _parse_ddg_html(html: str) -> list[dict[str, str]]:
    """Парсит HTML-страницу DuckDuckGo Lite, извлекая результаты.

    Ищет пары: ссылка с классом result-link и соседний сниппет.
    """
    results: list[dict[str, str]] = []
    # Ищем блоки результатов: каждый начинается с <a class="result-link" ...>
    # и содержит <td class="result-snippet">.
    # Регулярка: заголовок.
    title_re = re.compile(
        r'<a[^>]+class="result-link"[^>]*href="([^"]+)"[^>]*>'
        r'(.*?)</a>',
        re.DOTALL,
    )
    snippet_re = re.compile(
        r'<td[^>]+class="result-snippet"[^>]*>(.*?)</td>',
        re.DOTALL,
    )
    titles = title_re.findall(html)
    snippets = snippet_re.findall(html)
    for i, (raw_url, raw_title) in enumerate(titles[:MAX_RESULTS]):
        # DDG Lite оборачивает ссылки через редирект.
        # Формат: /l/?uddg=<encoded_url>&rut=...
        actual_url = _extract_ddg_url(raw_url)
        title = _strip_tags(raw_title).strip()
        snippet = _strip_tags(snippets[i]).strip() if i < len(snippets) else ""
        if title:
            results.append({"title": title, "snippet": snippet, "url": actual_url})
    return results


def _extract_ddg_url(raw: str) -> str:
    """Извлекает реальный URL из DDG-редиректа /l/?uddg=...&rut=..."""
    match = re.search(r'uddg=([^&]+)', raw)
    if not match:
        return raw
    try:
        return urllib.parse.unquote(match.group(1))
    except Exception:
        return raw


def _strip_tags(html: str) -> str:
    """Удаляет HTML-теги, декодирует базовые сущности."""
    text = re.sub(r"<[^>]+>", " ", html)
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&quot;", '"').replace("&#39;", "'")
    return " ".join(text.split())


def _format_results(query: str, results: list[dict[str, str]]) -> str:
    """Форматирует результаты для озвучивания и popup."""
    if not results:
        return f"Ничего не нашёл по запросу «{query}», сэр."
    lines = []
    for i, r in enumerate(results, 1):
        snippet = r["snippet"] or r["title"]
        # Обрезаем длинные сниппеты для голоса.
        if len(snippet) > 200:
            snippet = snippet[:197] + "..."
        lines.append(f"{i}. {r['title']}")
        lines.append(f"   {snippet}")
    text = "\n".join(lines)
    return text


# ── Навыки ────────────────────────────────────────────────────────────


def web_search(config: SkillsConfig, query: str) -> str:
    """Ищет в интернете и показывает результаты в popup.

    Не открывает браузер — только возвращает текст с результатами.
    Для открытия в браузере используйте навык open_in_browser.
    """
    global _last_search_url  # noqa: PLW0603
    if not query.strip():
        return "Что искать, сэр?"
    _last_search_url = config.search_engine.replace("{query}", urllib.parse.quote(query))
    results = _fetch_ddg_results(query)
    if not results:
        # Fallback: открываем браузер как раньше.
        webbrowser.open(_last_search_url)
        return f"Сервер поиска не ответил, открыл в браузере: «{query}», сэр."
    text = _format_results(query, results)
    return text


def open_in_browser() -> str:
    """Открывает последний поисковый запрос в браузере."""
    if not _last_search_url:
        return "Вы ещё ничего не искали, сэр."
    webbrowser.open(_last_search_url)
    return "Открываю в браузере, сэр."


def open_url(url: str) -> str:
    """Открывает произвольный адрес в браузере."""
    from urllib.parse import urlparse
    parsed = urlparse(url)
    # Если схема есть и не http/https — отвергаем (javascript:, file:, data: и т.д.).
    if parsed.scheme and parsed.scheme.lower() not in ("http", "https"):
        return f"Схема «{parsed.scheme}» не поддерживается, сэр. Разрешены только http и https."
    # Если схемы нет — считаем https.
    if not parsed.scheme:
        url = "https://" + url
    webbrowser.open(url)
    return f"Открываю {url}."


def fetch_summary(query: str) -> str:
    """Короткая справка из Википедии по запросу."""
    try:
        import requests  # type: ignore[import-not-found]
    except ImportError:
        return "Модуль requests не установлен, сэр."
    try:
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
    except requests.Timeout:
        return "Википедия не ответила вовремя, сэр."
    except requests.RequestException as exc:
        return f"Не удалось связаться с Википедией: {exc}"
    if not hits:
        return f"По запросу «{query}» ничего не нашёл, сэр."
    title = hits[0]["title"]
    try:
        summary = requests.get(
            "https://ru.wikipedia.org/api/rest_v1/page/summary/"
            + urllib.parse.quote(title.replace(" ", "_")),
            timeout=HTTP_TIMEOUT_S,
            headers={"User-Agent": "JarvisAssistant/1.0"},
        )
        summary.raise_for_status()
        extract = summary.json().get("extract", "")
    except requests.RequestException as exc:
        return f"Статья «{title}» найдена, но не загрузилась: {exc}"
    return extract or f"Нашёл статью «{title}», но выжимки нет, сэр."


def build_skills(config: SkillsConfig) -> list[Skill]:
    """Создаёт веб-навыки."""
    return [
        Skill(
            name="web_search",
            description=(
                "Поиск в интернете. Показывает результаты в popup-окне, "
                "не открывая браузер. Скажите 'открой в браузере', чтобы увидеть полную страницу."
            ),
            parameters=object_schema(
                {"query": {"type": "string", "description": "Поисковый запрос"}},
                required=["query"],
            ),
            handler=lambda query: web_search(config, query),
        ),
        Skill(
            name="open_in_browser",
            description=(
                "Открыть результаты последнего поиска в браузере. "
                "Используется после web_search, когда нужно увидеть полную страницу."
            ),
            parameters=object_schema({}),
            handler=open_in_browser,
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
            name="fetch_summary",
            description="Получить краткую справку из Википедии по теме.",
            parameters=object_schema(
                {"query": {"type": "string", "description": "Тема запроса"}},
                required=["query"],
            ),
            handler=fetch_summary,
        ),
    ]
