"""Плагинная система: автозагрузка пользовательских навыков из папки.

Пользователь создаёт .py файлы в ``~/.jarvis/skills/``. Каждый файл
должен определять функцию ``build_skills(config: Config) -> list[Skill]``
(или ``build_skills() -> list[Skill]`` без параметров).

Пример ``~/.jarvis/skills/hello.py``::

    from jarvis.skills.registry import Skill, object_schema

    def build_skills():
        return [
            Skill(
                name="hello",
                description="Поприветствовать пользователя.",
                parameters=object_schema({}),
                handler=lambda: "Привет, сэр! Я — кастомный навык.",
            )
        ]

Также поддерживается установка плагинов из GitHub через
``install_plugin(url)`` — репозиторий клонируется в ``~/.jarvis/plugins/``,
все .py файлы загружаются автоматически.
"""

from __future__ import annotations

import importlib.util
import logging
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from ..config import Config
from .registry import Skill

log = logging.getLogger(__name__)

PLUGINS_DIR_NAME = "skills"
GITHUB_PLUGINS_DIR = Path.home() / ".jarvis" / "plugins"

# Паттерн для извлечения имени репозитория из GitHub URL
# Поддерживает: https://github.com/user/repo.git  и  https://github.com/user/repo
_GITHUB_REPO_RE = re.compile(
    r"github\.com[:/]([^/]+)/([^/\s]+?)(?:\.git)?\s*$"
)


def _load_plugin_file(path: Path, config: Config) -> list[Skill]:
    """Загружает один .py файл и извлекает из него функцию build_skills."""
    module_name = f"jarvis_plugin_{path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, str(path))  # type: ignore[arg-type]
    if spec is None or spec.loader is None:
        log.warning("Не удалось создать спецификацию модуля: %s", path)
        return []
    module = importlib.util.module_from_spec(spec)
    # Временно добавляем папку плагина в sys.path, чтобы плагин
    # мог импортировать другие файлы из той же папки.
    parent = str(path.parent)
    in_path = parent in sys.path
    if not in_path:
        sys.path.insert(0, parent)
    try:
        spec.loader.exec_module(module)  # type: ignore[attr-defined]
    except Exception:
        log.exception("Ошибка загрузки плагина %s", path)
        return []
    finally:
        if not in_path:
            sys.path.remove(parent)

    build_fn = getattr(module, "build_skills", None)
    if build_fn is None:
        log.warning("Плагин %s не содержит функцию build_skills", path)
        return []
    try:
        import inspect
        sig = inspect.signature(build_fn)
        if len(sig.parameters) == 0:
            skills = build_fn()
        else:
            skills = build_fn(config)
        if not isinstance(skills, list):
            log.warning("Плагин %s: build_skills должен вернуть list[Skill]", path)
            return []
        return [s for s in skills if isinstance(s, Skill)]
    except Exception:
        log.exception("Ошибка выполнения build_skills в %s", path)
        return []


def load_plugins(config: Config) -> list[Skill]:
    """Загружает все пользовательские плагины из ~/.jarvis/skills/."""
    plugins_dir = Path.home() / ".jarvis" / PLUGINS_DIR_NAME
    if not plugins_dir.is_dir():
        return []
    all_skills: list[Skill] = []
    for path in sorted(plugins_dir.glob("*.py")):
        if path.name.startswith("_"):
            continue
        skills = _load_plugin_file(path, config)
        if skills:
            log.info(
                "Плагин %s: загружено %d навыков (%s)",
                path.name,
                len(skills),
                ", ".join(s.name for s in skills),
            )
            all_skills.extend(skills)
    return all_skills


# ── Установка плагинов из GitHub ─────────────────────────────────────────


def _parse_repo_name(url: str) -> str | None:
    """Извлекает имя репозитория из GitHub URL.

    >>> _parse_repo_name("https://github.com/user/jarvis-hello.git")
    'jarvis-hello'
    >>> _parse_repo_name("https://github.com/user/jarvis-hello")
    'jarvis-hello'
    >>> _parse_repo_name("git@github.com:user/jarvis-hello.git")
    'jarvis-hello'
    """
    m = _GITHUB_REPO_RE.search(url.strip())
    if m:
        return m.group(2)
    return None


def _clone_repo(url: str, target_dir: Path) -> bool:
    """Клонирует (или обновляет) Git-репозиторий в target_dir."""
    if not target_dir.exists():
        try:
            subprocess.run(
                ["git", "clone", "--depth", "1", url, str(target_dir)],
                check=True,
                capture_output=True,
                text=True,
                timeout=120,
            )
            log.info("Репозиторий склонирован в %s", target_dir)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError, OSError) as exc:
            log.error("Ошибка клонирования %s: %s", url, exc)
            return False
    else:
        # Репозиторий уже существует — обновляем
        try:
            subprocess.run(
                ["git", "-C", str(target_dir), "pull", "--ff-only"],
                check=True,
                capture_output=True,
                text=True,
                timeout=60,
            )
            log.info("Репозиторий обновлён в %s", target_dir)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError, OSError) as exc:
            log.warning("Ошибка обновления %s: %s", target_dir, exc)
            return True  # используем текущую версию


def _load_plugin_dir(plugin_dir: Path, config: Config) -> list[Skill]:
    """Загружает все .py плагины из директории (рекурсивно)."""
    all_skills: list[Skill] = []
    if not plugin_dir.is_dir():
        return all_skills
    for path in sorted(plugin_dir.rglob("*.py")):
        # Пропускаем скрытые файлы и __init__
        if path.name.startswith("_") or path.name.startswith("."):
            continue
        # Пропускаем файлы в подкаталогах типа tests/, .git/, __pycache__/
        if any(part.startswith((".", "_", "test")) for part in path.relative_to(plugin_dir).parts):
            continue
        skills = _load_plugin_file(path, config)
        if skills:
            log.info(
                "GitHub-плагин %s: загружено %d навыков (%s)",
                path.relative_to(plugin_dir),
                len(skills),
                ", ".join(s.name for s in skills),
            )
            all_skills.extend(skills)
    return all_skills


def install_plugin(url: str, config: Config) -> list[Skill]:
    """Клонирует плагин из GitHub и загружает его навыки.

    Args:
        url: GitHub URL репозитория (HTTPS или SSH).
            Например: ``https://github.com/user/jarvis-my-skill``
        config: Конфигурация Джарвиса, передаётся в ``build_skills`` плагина.

    Returns:
        Список загруженных :class:`Skill` объектов.

    Raises:
        ValueError: Если URL не является GitHub-ссылкой.
        RuntimeError: Если клонирование или загрузка не удалась.

    Пример использования::

        from jarvis.skills.plugins import install_plugin
        from jarvis.config import Config

        config = Config()
        skills = install_plugin("https://github.com/user/jarvis-cool-skill", config)
        for skill in skills:
            registry.register(skill)
    """
    repo_name = _parse_repo_name(url)
    if repo_name is None:
        raise ValueError(
            f"Не удалось извлечь имя репозитория из URL: {url}. "
            "Ожидается ссылка вида https://github.com/user/repo"
        )

    # Убеждаемся, что директория плагинов существует
    GITHUB_PLUGINS_DIR.mkdir(parents=True, exist_ok=True)

    target_dir = GITHUB_PLUGINS_DIR / repo_name
    log.info("Установка плагина из %s → %s", url, target_dir)

    if not _clone_repo(url, target_dir):
        raise RuntimeError(
            f"Не удалось клонировать репозиторий {url} в {target_dir}, сэр."
        )

    skills = _load_plugin_dir(target_dir, config)
    if not skills:
        raise RuntimeError(
            f"Плагин {repo_name} установлен, но не содержит навыков "
            "(нет функций build_skills в .py файлах), сэр."
        )

    log.info(
        "Плагин %s: установлено и загружено %d навыков (%s)",
        repo_name,
        len(skills),
        ", ".join(s.name for s in skills),
    )
    return skills
