"""Плагинная система: локальные + GitHub-плагины с манифестом.

Источники плагинов:
1. **Локальные**: ``~/.jarvis/skills/*.py`` — каждый файл
   определяет ``build_skills(config?) -> list[Skill]``.
2. **GitHub**: устанавливаются через ``install_plugin(url)`` в
   ``~/.jarvis/plugins/<repo-name>/``, автозагружаются при старте.

Манифест ``~/.jarvis/plugins/manifest.json`` отслеживает установленные
GitHub-плагины (url, имя, дата установки, список навыков).

Голосовые команды (навыки):
  "Джарвис, установи плагин https://github.com/user/skill"
  "Джарвис, покажи плагины"
  "Джарвис, удали плагин jarvis-hello"
  "Джарвис, обнови плагины"

Пример локального плагина ``~/.jarvis/skills/hello.py``::

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

Пример GitHub-плагина (в репозитории файл ``skill.py``)::

    from jarvis.skills.registry import Skill, object_schema

    def build_skills():
        return [
            Skill(
                name="my_skill",
                description="Описание навыка.",
                parameters=object_schema({}),
                handler=lambda: "Результат работы навыка.",
            )
        ]
"""

from __future__ import annotations

import importlib.util
import json
import logging
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import Config
from .registry import Skill, object_schema

log = logging.getLogger(__name__)

PLUGINS_DIR_NAME = "skills"
GITHUB_PLUGINS_DIR = Path.home() / ".jarvis" / "plugins"
MANIFEST_PATH = GITHUB_PLUGINS_DIR / "manifest.json"

# Паттерн для извлечения имени репозитория из GitHub URL
_GITHUB_REPO_RE = re.compile(
    r"github\.com[:/]([^/]+)/([^/\s]+?)(?:\.git)?\s*$"
)


# ── Манифест ─────────────────────────────────────────────────────────


def _load_manifest() -> dict[str, dict[str, Any]]:
    """Загружает манифест установленных плагинов."""
    if not MANIFEST_PATH.is_file():
        return {}
    try:
        data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        log.warning("Манифест плагинов повреждён")
        return {}


def _save_manifest(manifest: dict[str, dict[str, Any]]) -> None:
    """Сохраняет манифест."""
    try:
        GITHUB_PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
        MANIFEST_PATH.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8"
        )
    except OSError:
        log.exception("Не удалось сохранить манифест")


def _manifest_add(url: str, repo_name: str, skills: list[Skill]) -> None:
    """Добавляет запись в манифест после установки."""
    manifest = _load_manifest()
    manifest[repo_name] = {
        "url": url,
        "installed_at": datetime.now(timezone.utc).isoformat(),
        "skills": [s.name for s in skills],
    }
    _save_manifest(manifest)


def _manifest_remove(repo_name: str) -> None:
    """Удаляет запись из манифеста."""
    manifest = _load_manifest()
    manifest.pop(repo_name, None)
    _save_manifest(manifest)


def _manifest_update_skills(repo_name: str, skills: list[Skill]) -> None:
    """Обновляет список навыков в манифесте."""
    manifest = _load_manifest()
    if repo_name in manifest:
        manifest[repo_name]["skills"] = [s.name for s in skills]
        manifest[repo_name]["updated_at"] = datetime.now(timezone.utc).isoformat()
    _save_manifest(manifest)


# ── Загрузка .py файлов ──────────────────────────────────────────────


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
        config: Конфигурация Джарвиса.

    Returns:
        Список загруженных :class:`Skill` объектов.

    Raises:
        ValueError: Если URL не является GitHub-ссылкой.
        RuntimeError: Если клонирование или загрузка не удалась.
    """
    repo_name = _parse_repo_name(url)
    if repo_name is None:
        raise ValueError(
            f"Не удалось извлечь имя репозитория из URL: {url}. "
            "Ожидается ссылка вида https://github.com/user/repo"
        )

    GITHUB_PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
    target_dir = GITHUB_PLUGINS_DIR / repo_name
    log.info("Установка плагина из %s → %s", url, target_dir)

    if not _clone_repo(url, target_dir):
        raise RuntimeError(
            f"Не удалось клонировать репозиторий {url}, сэр."
        )

    skills = _load_plugin_dir(target_dir, config)
    if not skills:
        raise RuntimeError(
            f"Плагин {repo_name} установлен, но не содержит навыков, сэр."
        )

    # Записываем в манифест
    _manifest_add(url, repo_name, skills)

    log.info(
        "Плагин %s: %d навыков (%s)",
        repo_name, len(skills), ", ".join(s.name for s in skills),
    )
    return skills


def uninstall_plugin(repo_name: str) -> str:
    """Удаляет установленный GitHub-плагин.

    Args:
        repo_name: Имя директории плагина (совпадает с именем репозитория).

    Returns:
        Сообщение о результате.
    """
    repo_name = repo_name.strip()
    target_dir = GITHUB_PLUGINS_DIR / repo_name

    if not target_dir.is_dir():
        manifest = _load_manifest()
        # Попробуем найти по частичному совпадению
        for name in manifest:
            if repo_name.lower() in name.lower():
                target_dir = GITHUB_PLUGINS_DIR / name
                repo_name = name
                break
        if not target_dir.is_dir():
            available = ", ".join(_load_manifest().keys()) or "нет"
            return f"Плагин '{repo_name}' не найден. Установленные: {available}."

    try:
        shutil.rmtree(target_dir)
    except OSError as exc:
        return f"Не удалось удалить {repo_name}: {exc}."

    _manifest_remove(repo_name)
    return f"Плагин {repo_name} удалён."


def update_plugin(repo_name: str, config: Config) -> str:
    """Обновляет один GitHub-плагин (git pull).

    Args:
        repo_name: Имя плагина (пустая строка = обновить все).

    Returns:
        Сообщение о результате.
    """
    repo_name = repo_name.strip()
    manifest = _load_manifest()

    if not manifest:
        return "Нет установленных GitHub-плагинов."

    targets: dict[str, Path] = {}
    if repo_name:
        # Ищем конкретный плагин
        for name in manifest:
            if repo_name.lower() in name.lower():
                targets[name] = GITHUB_PLUGINS_DIR / name
        if not targets:
            available = ", ".join(manifest.keys())
            return f"Плагин '{repo_name}' не найден. Установленные: {available}."
    else:
        # Все плагины
        for name in manifest:
            targets[name] = GITHUB_PLUGINS_DIR / name

    results: list[str] = []
    for name, target_dir in targets.items():
        if not target_dir.is_dir():
            results.append(f"  {name}: директория отсутствует (пропущен)")
            continue
        url = manifest[name].get("url", "")
        ok = _clone_repo(url, target_dir) if url else False
        if ok:
            skills = _load_plugin_dir(target_dir, config)
            _manifest_update_skills(name, skills)
            results.append(f"  {name}: обновлён, {len(skills)} навыков")
        else:
            results.append(f"  {name}: ошибка обновления")

    return "Результат обновления:\n" + "\n".join(results)


def list_installed_plugins() -> str:
    """Возвращает список установленных GitHub-плагинов из манифеста."""
    manifest = _load_manifest()
    if not manifest:
        return "Нет установленных GitHub-плагинов, сэр."
    lines: list[str] = []
    for name, info in sorted(manifest.items()):
        url = info.get("url", "?")
        skills = info.get("skills", [])
        installed = info.get("installed_at", "?")[:10]
        skills_str = ", ".join(skills) if skills else "(нет навыков)"
        lines.append(f"  {name}: {skills_str}")
        lines.append(f"    URL: {url}, установлено: {installed}")
    return f"Установленные плагины ({len(manifest)}):\n" + "\n".join(lines)


def load_github_plugins(config: Config) -> list[Skill]:
    """Загружает все установленные GitHub-плагины при старте.

    Вызывается из build_registry. Для каждого плагина в манифесте
    загружает навыки из соответствующей директории.
    """
    manifest = _load_manifest()
    if not manifest:
        return []
    all_skills: list[Skill] = []
    for name in sorted(manifest):
        target_dir = GITHUB_PLUGINS_DIR / name
        if not target_dir.is_dir():
            log.warning("Плагин %s: директория отсутствует, пропускаю", name)
            continue
        skills = _load_plugin_dir(target_dir, config)
        if skills:
            log.info(
                "GitHub-плагин %s: загружено %d навыков (%s)",
                name, len(skills), ", ".join(s.name for s in skills),
            )
            all_skills.extend(skills)
    return all_skills


def load_plugins(config: Config) -> list[Skill]:
    """Загружает все плагины: локальные + GitHub."""
    # 1. Локальные из ~/.jarvis/skills/
    local_skills = _load_local_plugins(config)
    # 2. GitHub-плагины из манифеста
    github_skills = load_github_plugins(config)
    return local_skills + github_skills


def _load_local_plugins(config: Config) -> list[Skill]:
    """Загружает локальные плагины из ~/.jarvis/skills/."""
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
                "Локальный плагин %s: %d навыков (%s)",
                path.name, len(skills), ", ".join(s.name for s in skills),
            )
            all_skills.extend(skills)
    return all_skills


# ── Голосовые навыки управления плагинами ─────────────────────────────


def build_plugin_skills(config: Config) -> list[Skill]:
    """Навыки для управления плагинами через голос."""

    def _install(url: str = "") -> str:
        """Установить плагин из GitHub по URL."""
        if not url:
            return ("Укажите URL плагина. Например: "
                    "установи плагин https://github.com/user/jarvis-skill")
        try:
            skills = install_plugin(url, config)
            names = ", ".join(s.name for s in skills)
            return f"Плагин установлен! Навыки: {names}."
        except ValueError as e:
            return str(e)
        except RuntimeError as e:
            return str(e)
        except Exception as e:
            return f"Ошибка установки: {e}."

    def _uninstall(name: str = "") -> str:
        """Удалить установленный плагин."""
        if not name:
            return "Укажите имя плагина для удаления."
        return uninstall_plugin(name)

    def _list() -> str:
        """Показать установленные плагины."""
        return list_installed_plugins()

    def _update(name: str = "") -> str:
        """Обновить плагин (или все, если имя не указано)."""
        return update_plugin(name, config)

    return [
        Skill(
            name="plugin_install",
            description="Установить плагин из GitHub по URL репозитория.",
            parameters=object_schema(
                {"url": {"type": "string", "description": "GitHub URL (https://github.com/user/repo)"}},
                required=["url"],
            ),
            handler=_install,
        ),
        Skill(
            name="plugin_uninstall",
            description="Удалить установленный GitHub-плагин.",
            parameters=object_schema(
                {"name": {"type": "string", "description": "Имя плагина"}},
                required=["name"],
            ),
            handler=_uninstall,
        ),
        Skill(
            name="plugin_list",
            description="Показать все установленные GitHub-плагины.",
            parameters=object_schema({}),
            handler=_list,
        ),
        Skill(
            name="plugin_update",
            description="Обновить плагин(ы) из GitHub. Пустое имя = обновить все.",
            parameters=object_schema(
                {"name": {"type": "string", "description": "Имя плагина (необязательно)"}},
            ),
            handler=_update,
        ),
    ]
