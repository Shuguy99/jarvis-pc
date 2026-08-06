"""Сборка полного набора навыков Джарвиса."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ..config import Config
from . import apps, browser, calendar, desktop_notify as desktop_notify_mod, memory, personal, spotify, system, vision, weather, web
from .browser import BrowserSession
from .memory import Memory
from .personal import TimerService
from .registry import Skill, SkillRegistry

__all__ = [
    "Services",
    "Skill",
    "SkillRegistry",
    "TimerService",
    "build_registry",
]


@dataclass
class Services:
    """Долгоживущие службы, которыми владеют навыки."""

    timers: TimerService
    memory: Memory
    browser: BrowserSession

    def shutdown(self) -> None:
        """Освобождает ресурсы всех служб."""
        self.timers.shutdown()
        self.browser.shutdown()


def build_registry(config: Config, notify: Callable[[str], None]) -> tuple[SkillRegistry, Services]:
    """Создаёт реестр всех навыков и связанные с ними службы.

    Встроенные навыки регистрируются первыми, затем — пользовательские
    плагины из ``~/.jarvis/skills/*.py``.
    """
    skills_config = config.skills
    timers = TimerService(notify)
    memory_skills, memory_store = memory.build_skills(skills_config.memory)
    browser_skills, browser_session = browser.build_skills(skills_config.browser)
    registry = SkillRegistry()
    registry.extend(system.build_skills(skills_config))
    registry.extend(apps.build_skills(skills_config))
    registry.extend(web.build_skills(skills_config))
    registry.extend(personal.build_skills(skills_config, timers))
    registry.extend(vision.build_skills(config))
    registry.extend(memory_skills)
    registry.extend(browser_skills)
    registry.extend(spotify.build_skills(skills_config))
    if skills_config.weather.enabled:
        registry.extend(weather.build_skills(skills_config.weather))
    if skills_config.calendar.enabled:
        registry.extend(calendar.build_skills(skills_config.calendar))
    registry.extend(desktop_notify_mod.build_skills())
    # Пользовательские плагины — последними, могут переопределить встроенные.
    from .plugins import load_plugins

    plugin_skills = load_plugins(config)
    if plugin_skills:
        registry.extend(plugin_skills)
    return registry, Services(timers, memory_store, browser_session)
