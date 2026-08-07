"""Сборка полного набора навыков Джарвиса."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from ..config import Config
from . import (
    alarm, agenda, apps, browser, calendar, currency, desktop_notify as desktop_notify_mod,
    env, expenses, face, files, github, habits, homeassistant, macros,
    memory, news, notes, passwords, personal, pomodoro, sounds,
    spotify, system, telegram_bot, translator, vision, vpn, weather, web, wifi, youtube,
)
from .alarm import AlarmService
from .browser import BrowserSession
from .memory import Memory
from .personal import TimerService
from .pomodoro import PomodoroService
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
    pomodoro: PomodoroService | None = None
    alarm: AlarmService | None = None

    def shutdown(self) -> None:
        """Освобождает ресурсы всех служб."""
        self.timers.shutdown()
        self.browser.shutdown()
        if self.alarm is not None:
            self.alarm.shutdown()


def build_registry(config: Config, notify: Callable[[str], None]) -> tuple[SkillRegistry, Services]:
    """Создаёт реестр всех навыков и связанные с ними службы."""
    skills_config = config.skills
    timers = TimerService(notify)
    memory_skills, memory_store = memory.build_skills(skills_config.memory)
    browser_skills, browser_session = browser.build_skills(skills_config.browser)
    registry = SkillRegistry()
    # Базовые навыки
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
    registry.extend(translator.build_skills())
    registry.extend(env.build_skills())
    registry.extend(macros.build_skills())
    if skills_config.files.enabled:
        registry.extend(files.build_skills(skills_config.files))
    if skills_config.youtube.enabled:
        registry.extend(youtube.build_skills(skills_config.youtube))
    if skills_config.face.enabled:
        registry.extend(face.build_skills(skills_config.face))
    if skills_config.github.enabled:
        registry.extend(github.build_skills(skills_config.github))
    if skills_config.vpn.enabled:
        registry.extend(vpn.build_skills(skills_config.vpn))
    registry.extend(sounds.build_skills(skills_config.sounds))
    registry.extend(wifi.build_skills())
    # --- Круто и полезно ---
    pomodoro_svc = None
    if skills_config.pomodoro.enabled:
        pomodoro_skills, pomodoro_svc = pomodoro.build_skills(skills_config.pomodoro, notify)
        registry.extend(pomodoro_skills)
    if skills_config.news.enabled:
        registry.extend(news.build_skills(skills_config.news))
    if skills_config.currency.enabled:
        registry.extend(currency.build_skills(skills_config.currency))
    if skills_config.homeassistant.enabled:
        registry.extend(homeassistant.build_skills(skills_config.homeassistant))
    if skills_config.telegram.enabled:
        registry.extend(telegram_bot.build_skills(skills_config.telegram))
    alarm_svc = None
    if skills_config.alarm.enabled:
        alarm_skills, alarm_svc = alarm.build_skills(skills_config.alarm, notify)
        registry.extend(alarm_skills)
    # --- Продуктивность ---
    if skills_config.passwords.enabled:
        registry.extend(passwords.build_skills(skills_config.passwords)[0])
    if skills_config.notes.enabled:
        registry.extend(notes.build_skills(skills_config.notes)[0])
    if skills_config.agenda.enabled:
        registry.extend(agenda.build_skills(skills_config.agenda, timers.list))
    if skills_config.habits.enabled:
        registry.extend(habits.build_skills(skills_config.habits)[0])
    if skills_config.expenses.enabled:
        registry.extend(expenses.build_skills(skills_config.expenses)[0])
    # Пользовательские плагины
    from .plugins import load_plugins

    plugin_skills = load_plugins(config)
    if plugin_skills:
        registry.extend(plugin_skills)
    return registry, Services(timers, memory_store, browser_session, pomodoro_svc, alarm_svc)
