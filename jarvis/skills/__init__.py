"""Сборка полного набора навыков Джарвиса."""

from __future__ import annotations

from collections.abc import Callable

from ..config import SkillsConfig
from . import apps, personal, system, web
from .personal import TimerService
from .registry import Skill, SkillRegistry

__all__ = ["Skill", "SkillRegistry", "TimerService", "build_registry"]


def build_registry(
    config: SkillsConfig, notify: Callable[[str], None]
) -> tuple[SkillRegistry, TimerService]:
    """Создаёт реестр всех навыков и сервис таймеров."""
    timers = TimerService(notify)
    registry = SkillRegistry()
    registry.extend(system.build_skills(config))
    registry.extend(apps.build_skills(config))
    registry.extend(web.build_skills(config))
    registry.extend(personal.build_skills(config, timers))
    return registry, timers
