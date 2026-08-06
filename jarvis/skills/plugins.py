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
"""

from __future__ import annotations

import importlib.util
import logging
import sys
from pathlib import Path
from typing import Any

from ..config import Config
from .registry import Skill

log = logging.getLogger(__name__)

PLUGINS_DIR_NAME = "skills"


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
        # Плагин может принимать config или не принимать аргументов.
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
