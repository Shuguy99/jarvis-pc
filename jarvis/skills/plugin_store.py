"""Магазин плагинов: поиск, информация и установка плагинов из GitHub.

Использует GitHub Search API для поиска репозиториев по topic,
чтение README и файла манифеста ``jarvis.json`` для получения метаданных.

Манифест плагина (опционально, в корне репозитория)::

    {
        "name": "Умный шутник",
        "description": "Генерирует шутки по темам",
        "version": "1.0.0",
        "author": "username",
        "category": "развлечения",
        "tags": ["юмор", "шутки", "fun"]
    }

Голосовые команды:
  "Джарвис, найди плагин погода"
  "Джарвис, покажи информацию о плагине user/repo"
  "Джарвис, установи из магазина user/repo"
  "Джарвис, популярные плагины"
  "Джарвис, плагины в категории система"

Токен GitHub (из конфига или GITHUB_TOKEN) повышает лимиты API.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

from ..config import PluginStoreConfig
from .plugins import install_plugin
from .registry import Skill, object_schema

log = logging.getLogger(__name__)

_GITHUB_API = "https://api.github.com"
_RAW_BASE = "https://raw.githubusercontent.com"


def _gh_get(endpoint: str, params: dict | None = None, token: str = "") -> dict | list | None:
    """GET запрос к GitHub API. Возвращает JSON или None."""
    qs = urllib.parse.urlencode(params or {})
    url = f"{_GITHUB_API}{endpoint}?{qs}" if qs else f"{_GITHUB_API}{endpoint}"
    headers = {
        "User-Agent": "JarvisAssistant/1.0",
        "Accept": "application/vnd.github.v3+json",
    }
    if token:
        headers["Authorization"] = f"token {token}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        body = e.read().decode("utf-8", errors="replace")
        log.warning("GitHub API %s: HTTP %s — %s", endpoint, e.code, body[:200])
        return None
    except Exception as exc:
        log.warning("GitHub API ошибка: %s", exc)
        return None


def _get_token(config: PluginStoreConfig) -> str:
    """Возвращает токен: из конфига или переменной окружения."""
    return config.token or os.environ.get("GITHUB_TOKEN", "")


def _fetch_manifest(owner: str, repo: str, token: str = "") -> dict[str, Any] | None:
    """Загружает jarvis.json манифест из репозитория."""
    url = f"{_RAW_BASE}/{owner}/{repo}/main/jarvis.json"
    headers = {"User-Agent": "JarvisAssistant/1.0"}
    if token:
        headers["Authorization"] = f"token {token}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    # Пробуем ветку master
    url = f"{_RAW_BASE}/{owner}/{repo}/master/jarvis.json"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return None


def _fetch_readme(owner: str, repo: str, token: str = "") -> str:
    """Загружает README репозитория (первые 500 символов)."""
    data = _gh_get(f"/repos/{owner}/{repo}/readme", token=token)
    if not data or not isinstance(data, dict):
        return ""
    content_b64 = data.get("content", "")
    if not content_b64:
        return ""
    try:
        import base64
        text = base64.b64decode(content_b64).decode("utf-8", errors="replace")
        # Берём первые строки, без заголовка
        lines = [l for l in text.strip().split("\n") if l.strip() and not l.startswith("#")]
        return " ".join(lines)[:500]
    except Exception:
        return ""


def _format_repo_info(item: dict, token: str) -> dict[str, Any]:
    """Извлекает и форматирует информацию о репозитории из данных API."""
    full_name = item.get("full_name", "")
    parts = full_name.split("/")
    owner, repo = (parts[0], parts[1]) if len(parts) == 2 else ("", full_name)

    description = (item.get("description") or "").strip()
    stars = item.get("stargazers_count", 0)
    forks = item.get("forks_count", 0)
    lang = item.get("language") or "—"
    updated = (item.get("updated_at") or "")[:10]
    topics = item.get("topics", [])

    # Пытаемся загрузить манифест
    manifest = _fetch_manifest(owner, repo, token)
    if manifest:
        name = manifest.get("name", repo)
        desc = manifest.get("description", description)
        category = manifest.get("category", "")
        tags = manifest.get("tags", [])
        version = manifest.get("version", "")
        author = manifest.get("author", owner)
    else:
        name = repo
        desc = description
        category = ""
        tags = []
        version = ""
        author = owner

    return {
        "full_name": full_name,
        "name": name,
        "description": desc,
        "author": author,
        "category": category,
        "tags": tags,
        "version": version,
        "stars": stars,
        "forks": forks,
        "language": lang,
        "updated": updated,
        "topics": topics,
    }


def _format_plugin_card(info: dict[str, Any]) -> str:
    """Формирует текстовую карточку плагина."""
    lines = [f"📦 {info['name']} ({info['full_name']})"]
    if info["version"]:
        lines[0] += f" v{info['version']}"
    lines.append(f"   {info['description']}")
    meta_parts = [f"⭐ {info['stars']}", f"🍴 {info['forks']}", f"📝 {info['language']}"]
    if info["category"]:
        meta_parts.append(f"📂 {info['category']}")
    if info["author"]:
        meta_parts.append(f"👤 {info['author']}")
    lines.append(f"   {' | '.join(meta_parts)}")
    if info["tags"]:
        lines.append(f"   Теги: {', '.join(info['tags'])}")
    lines.append(f"   Обновлено: {info['updated']}")
    return "\n".join(lines)


def _parse_repo_input(repo_input: str) -> tuple[str, str]:
    """Разбирает ввод репозитория в (owner, repo)."""
    repo_input = repo_input.strip()
    if "github.com/" in repo_input:
        parts = repo_input.split("github.com/")[1].split("/")
        repo_input = "/".join(parts[:2])
    repo_input = repo_input.rstrip("/")
    if repo_input.endswith(".git"):
        repo_input = repo_input[:-4]
    parts = repo_input.split("/")
    if len(parts) == 2:
        return parts[0], parts[1]
    return "", repo_input


def search_plugins(config: PluginStoreConfig, query: str = "") -> str:
    """Ищет плагины на GitHub по topic + ключевому слову.

    Использует GitHub Search API: репозитории с указанным topic.
    Если задан query — добавляет поиск по названию/описанию.
    """
    token = _get_token(config)
    topic = config.topic

    params: dict[str, str] = {
        "q": f"topic:{topic}",
        "sort": "updated",
        "per_page": "15",
    }
    if query:
        params["q"] += f" {query}"

    data = _gh_get("/search/repositories", params=params, token=token)
    if not data or not isinstance(data, dict):
        return "Не удалось выполнить поиск плагинов, сэр. Проверьте подключение к интернету."

    items = data.get("items", [])
    total = data.get("total_count", 0)
    if not items:
        if query:
            return f"По запросу «{query}» ничего не найдено, сэр."
        return "Плагинов с topic jarvis-skill пока нет, сэр."

    lines = [f"Найдено плагинов: {total} (показываю до 15):\n"]
    for item in items:
        info = _format_repo_info(item, token)
        lines.append(_format_plugin_card(info))
        lines.append("")
    return "\n".join(lines).strip()


def plugin_info(config: PluginStoreConfig, repo: str = "") -> str:
    """Показывает подробную информацию о плагине.

    Загружает данные репозитория + манифест + README.
    """
    if not repo:
        return "Укажите репозиторий (owner/repo), сэр."

    token = _get_token(config)
    owner, name = _parse_repo_input(repo)
    if not owner:
        return f"Некорректный формат: {repo}. Ожидается owner/repo."

    full = f"{owner}/{name}"
    data = _gh_get(f"/repos/{full}", token=token)
    if not data or not isinstance(data, dict):
        return f"Репозиторий {full} не найден, сэр."

    info = _format_repo_info(data, token)
    lines = [_format_plugin_card(info), ""]

    # README
    readme = _fetch_readme(owner, name, token)
    if readme:
        lines.append("📖 Описание:")
        lines.append(f"   {readme}")

    # Подсказка установки
    lines.append("")
    lines.append(f"Для установки скажите: «установи из магазина {full}»")
    return "\n".join(lines)


def popular_plugins(config: PluginStoreConfig) -> str:
    """Показывает популярные плагины (по звёздам)."""
    token = _get_token(config)
    topic = config.topic

    params = {
        "q": f"topic:{topic}",
        "sort": "stars",
        "per_page": "10",
    }

    data = _gh_get("/search/repositories", params=params, token=token)
    if not data or not isinstance(data, dict):
        return "Не удалось загрузить список популярных плагинов, сэр."

    items = data.get("items", [])
    if not items:
        return "Плагинов с topic jarvis-skill пока нет, сэр."

    lines = ["⭐ Популярные плагины:\n"]
    for i, item in enumerate(items, 1):
        info = _format_repo_info(item, token)
        desc = info["description"][:80]
        lines.append(
            f"  {i}. {info['name']} ({info['full_name']}) — {desc}"
        )
        lines.append(f"     ⭐ {info['stars']} | 📝 {info['language']} | {info['updated']}")
    return "\n".join(lines)


def plugins_by_category(config: PluginStoreConfig, category: str = "") -> str:
    """Ищет плагины по категории из манифеста.

    GitHub API не умеет фильтровать по метаданным файла,
    поэтому ищем по topic + ключевые слова категории, затем
    фильтруем результаты по загруженным манифестам.
    """
    if not category:
        return "Укажите категорию, сэр. Например: система, погода, медиа, развлечения."

    token = _get_token(config)
    topic = config.topic

    # Сначала ищем все плагины с нужным topic
    params = {
        "q": f"topic:{topic} {category}",
        "sort": "stars",
        "per_page": "30",
    }
    data = _gh_get("/search/repositories", params=params, token=token)
    if not data or not isinstance(data, dict):
        return f"Не удалось найти плагины в категории «{category}», сэр."

    items = data.get("items", [])
    if not items:
        return f"В категории «{category}» ничего не найдено, сэр."

    # Фильтруем по категории из манифеста (если возможно)
    matched: list[dict] = []
    for item in items:
        info = _format_repo_info(item, token)
        cat_lower = (info["category"] or "").lower()
        query_lower = category.lower()
        # Совпадение по категории из манифеста или по тегам/названию
        if (cat_lower and query_lower in cat_lower) or \
           query_lower in (info["name"]).lower() or \
           any(query_lower in t.lower() for t in info["tags"]):
            matched.append(info)
        elif not matched or len(matched) < 5:
            # Если манифестов мало — показываем по релевантности поиска
            if query_lower in (info["description"]).lower():
                matched.append(info)

    if not matched:
        # Fallback — показываем первые результаты поиска
        matched = [_format_repo_info(item, token) for item in items[:10]]

    lines = [f"📂 Категория «{category}» — найдено {len(matched)}:\n"]
    for info in matched[:15]:
        desc = info["description"][:80]
        lines.append(f"  • {info['name']} ({info['full_name']}) — {desc}")
        lines.append(f"    ⭐ {info['stars']} | 📝 {info['language']}")
    return "\n".join(lines)


def store_install(config: PluginStoreConfig, repo: str = "") -> str:
    """Устанавливает плагин из магазина.

    Принимает owner/repo, клонирует через install_plugin()
    из plugins.py и регистрирует навыки.
    """
    if not repo:
        return "Укажите репозиторий (owner/repo), сэр."

    owner, name = _parse_repo_input(repo)
    if not owner:
        return f"Некорректный формат: {repo}. Ожидается owner/repo."

    url = f"https://github.com/{owner}/{name}"
    try:
        from ..config import Config as FullConfig
        skills = install_plugin(url, FullConfig())
        if not skills:
            return f"Плагин {owner}/{name} установлен, но не содержит навыков, сэр."
        names = ", ".join(s.name for s in skills)
        return (
            f"Плагин {owner}/{name} установлен из магазина! "
            f"Навыки: {names}. Перезапустите Джарвиса для применения."
        )
    except ValueError as e:
        return str(e)
    except RuntimeError as e:
        return str(e)
    except Exception as e:
        return f"Ошибка установки: {e}, сэр."


def build_skills(config: PluginStoreConfig) -> list[Skill]:
    """Создаёт навыки магазина плагинов."""
    return [
        Skill(
            name="store_search",
            description=(
                "Искать плагины в магазине GitHub. "
                "Без запроса — все плагины с topic jarvis-skill. "
                "С запросом — фильтр по названию/описанию."
            ),
            parameters=object_schema(
                {"query": {"type": "string", "description": "Ключевое слово для поиска (необязательно)"}},
            ),
            handler=lambda query="": search_plugins(config, query),
        ),
        Skill(
            name="store_info",
            description=(
                "Показать подробную информацию о плагине из магазина: "
                "описание, звёзды, версия, автор, README."
            ),
            parameters=object_schema(
                {"repo": {"type": "string", "description": "owner/repo репозитория"}},
                required=["repo"],
            ),
            handler=lambda repo: plugin_info(config, repo),
        ),
        Skill(
            name="store_install",
            description=(
                "Установить плагин из магазина GitHub. "
                "Укажите owner/repo. Навыки будут доступны после перезапуска."
            ),
            parameters=object_schema(
                {"repo": {"type": "string", "description": "owner/repo репозитория плагина"}},
                required=["repo"],
            ),
            handler=lambda repo: store_install(config, repo),
        ),
        Skill(
            name="store_popular",
            description="Показать популярные плагины из магазина (по звёздам).",
            parameters=object_schema({}),
            handler=lambda: popular_plugins(config),
        ),
        Skill(
            name="store_category",
            description=(
                "Показать плагины в указанной категории: система, погода, медиа, развлечения и т.д."
            ),
            parameters=object_schema(
                {"category": {"type": "string", "description": "Название категории"}},
                required=["category"],
            ),
            handler=lambda category: plugins_by_category(config, category),
        ),
    ]
