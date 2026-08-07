from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from ..config import GitHubConfig
from .registry import Skill, object_schema

log = logging.getLogger(__name__)

_GITHUB_API = "https://api.github.com"


def _gh_request(config: GitHubConfig, endpoint: str, params: dict | None = None) -> dict | list | None:
    """GET запрос к GitHub API. Возвращает JSON или None."""
    qs = urllib.parse.urlencode(params or {})
    url = f"{_GITHUB_API}{endpoint}?{qs}" if qs else f"{_GITHUB_API}{endpoint}"
    headers = {"User-Agent": "JarvisAssistant/1.0", "Accept": "application/vnd.github.v3+json"}
    if config.token:
        headers["Authorization"] = f"token {config.token}"
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


def _parse_repo(repo_input: str) -> str:
    """Нормализует ввод репо: 'owner/repo' или URL."""
    repo_input = repo_input.strip()
    if "github.com/" in repo_input:
        parts = repo_input.split("github.com/")[1].split("/")
        repo_input = "/".join(parts[:2])
    repo_input = repo_input.rstrip("/")
    if repo_input.endswith(".git"):
        repo_input = repo_input[:-4]
    return repo_input


def repo_status(config: GitHubConfig, repo: str = "") -> str:
    """Статус репозитория: звёзды, форки, открытые issues, последний коммит."""
    if not repo and not config.default_repo:
        return "Укажите репозиторий (owner/repo) или настройте default_repo, сэр."
    repo = _parse_repo(repo or config.default_repo)
    data = _gh_request(config, f"/repos/{repo}")
    if not data or not isinstance(data, dict):
        return f"Репозиторий {repo} не найден, сэр."
    full_name = data.get("full_name", repo)
    stars = data.get("stargazers_count", 0)
    forks = data.get("forks_count", 0)
    open_issues = data.get("open_issues_count", 0)
    lang = data.get("language") or "не указан"
    desc = data.get("description") or ""
    private = "частный" if data.get("private") else "публичный"
    lines = [
        f"{full_name} ({private}, {lang})",
        f"Звёзды: {stars}, Форки: {forks}, Открытых issues: {open_issues}",
    ]
    if desc:
        lines.append(desc)
    # Последний коммит
    commit = _gh_request(config, f"/repos/{repo}/commits", {"per_page": "1"})
    if commit and isinstance(commit, list) and commit:
        c = commit[0]
        sha = c.get("sha", "")[:7]
        msg = c.get("commit", {}).get("message", "").split("\n")[0]
        date = c.get("commit", {}).get("author", {}).get("date", "")[:10]
        author = c.get("commit", {}).get("author", {}).get("name", "")
        lines.append(f"Последний коммит: {sha} — {msg} ({author}, {date})")
    return ". ".join(lines)


def list_commits(config: GitHubConfig, repo: str = "", count: int = 5) -> str:
    """Показывает последние коммиты в репозитории."""
    if not repo and not config.default_repo:
        return "Укажите репозиторий, сэр."
    repo = _parse_repo(repo or config.default_repo)
    data = _gh_request(config, f"/repos/{repo}/commits", {"per_page": str(min(count, 20))})
    if not data or not isinstance(data, list):
        return f"Не удалось получить коммиты для {repo}, сэр."
    if not data:
        return f"В {repo} нет коммитов, сэр."
    lines = [f"Последние коммиты в {repo}:"]
    for c in data:
        sha = c.get("sha", "")[:7]
        msg = c.get("commit", {}).get("message", "").split("\n")[0][:60]
        author = c.get("commit", {}).get("author", {}).get("name", "")
        lines.append(f"  {sha} {msg} — {author}")
    return "\n".join(lines)


def list_issues(config: GitHubConfig, repo: str = "", state: str = "open", count: int = 5) -> str:
    """Показывает issues репозитория."""
    if not repo and not config.default_repo:
        return "Укажите репозиторий, сэр."
    repo = _parse_repo(repo or config.default_repo)
    data = _gh_request(config, f"/repos/{repo}/issues", {
        "state": state, "per_page": str(min(count, 20)),
    })
    if not data or not isinstance(data, list):
        return f"Не удалось получить issues для {repo}, сэр."
    if not data:
        state_word = "открытых" if state == "open" else "закрытых"
        return f"В {repo} нет {state_word} issues, сэр."
    lines = [f"Issues в {repo} ({state}):"]
    for i in data:
        num = i.get("number", "?")
        title = i.get("title", "")[:60]
        labels = ", ".join(l.get("name", "") for l in i.get("labels", []))
        label_str = f" [{labels}]" if labels else ""
        lines.append(f"  #{num} {title}{label_str}")
    return "\n".join(lines)


def create_issue(config: GitHubConfig, repo: str, title: str, body: str = "") -> str:
    """Создаёт issue (нужен токен)."""
    if not config.token:
        return "Для создания issues нужен GitHub токен, сэр."
    if not repo and not config.default_repo:
        return "Укажите репозиторий, сэр."
    repo = _parse_repo(repo or config.default_repo)
    payload = json.dumps({"title": title, "body": body}).encode("utf-8")
    url = f"{_GITHUB_API}/repos/{repo}/issues"
    req = urllib.request.Request(
        url, data=payload, method="POST",
        headers={
            "User-Agent": "JarvisAssistant/1.0",
            "Authorization": f"token {config.token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        num = result.get("number", "?")
        return f"Issue #{num} создан в {repo}: {title}, сэр."
    except Exception as exc:
        return f"Ошибка создания issue: {exc}, сэр."


def build_skills(config: GitHubConfig) -> list[Skill]:
    """Создаёт GitHub навыки."""
    return [
        Skill(
            name="repo_status",
            description="Показать статус GitHub репозитория (звёзды, форки, последний коммит).",
            parameters=object_schema(
                {"repo": {"type": "string", "description": "owner/repo или URL"}},
            ),
            handler=lambda repo="": repo_status(config, repo),
        ),
        Skill(
            name="list_commits",
            description="Показать последние коммиты в репозитории.",
            parameters=object_schema(
                {
                    "repo": {"type": "string", "description": "owner/repo"},
                    "count": {"type": "integer", "description": "Сколько коммитов (по умолчанию 5)"},
                },
            ),
            handler=lambda repo="", count=5: list_commits(config, repo, count),
        ),
        Skill(
            name="list_issues",
            description="Показать issues репозитория (открытые или закрытые).",
            parameters=object_schema(
                {
                    "repo": {"type": "string", "description": "owner/repo"},
                    "state": {"type": "string", "description": "open или closed"},
                    "count": {"type": "integer", "description": "Сколько (по умолчанию 5)"},
                },
            ),
            handler=lambda repo="", state="open", count=5: list_issues(config, repo, state, count),
        ),
        Skill(
            name="create_issue",
            description="Создать GitHub issue (нужен токен в конфиге).",
            parameters=object_schema(
                {
                    "repo": {"type": "string", "description": "owner/repo"},
                    "title": {"type": "string", "description": "Заголовок issue"},
                    "body": {"type": "string", "description": "Описание issue (необязательно)"},
                },
                required=["repo", "title"],
            ),
            handler=lambda repo, title, body="": create_issue(config, repo, title, body),
        ),
    ]
