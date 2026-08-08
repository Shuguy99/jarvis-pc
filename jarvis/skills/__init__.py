"""Сборка полного набора навыков Джарвиса."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from ..config import Config
from ..profiles import ProfileManager
from . import (
    alarm, agenda, apps, battery, bluetooth, brightness, browser, calculator, calendar,
    clipboard, code_snippets, crypto, currency, desktop_notify as desktop_notify_mod,
    dictaphone, disk, email, env, expenses, face, files, git_helper, github,
    habits, homeassistant, image_gen, macros, memory, music_recognition, network,
    news, notion_tasks, notes, password_gen, passwords, personal, pomodoro,
    processes, profiles as profiles_skill, qr, radio, screenshot_save, self_update,
    sounds, spotify, system, sysupdate, telegram_bot, timer_skill, translator,
    unit_converter, vision, vpn, volume, weather, weather_alert, web, wifi,
    windows_manager, youtube, youtube_music,
)
from .alarm import AlarmService
from .browser import BrowserSession
from .memory import Memory
from .personal import TimerService
from .pomodoro import PomodoroService
from .registry import Skill, SkillRegistry
from .timer_skill import TimerSkillService

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
    timer_skill: TimerSkillService | None = None

    def shutdown(self) -> None:
        """Освобождает ресурсы всех служб."""
        self.timers.shutdown()
        self.browser.shutdown()
        if self.alarm is not None:
            self.alarm.shutdown()
        if self.timer_skill is not None:
            self.timer_skill.shutdown()


def build_registry(
    config: Config,
    notify: Callable[[str], None],
    profile_manager: ProfileManager | None = None,
) -> tuple[SkillRegistry, Services]:
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
    # --- Система и сеть ---
    if skills_config.network.enabled:
        registry.extend(network.build_skills())
    if skills_config.windows.enabled:
        registry.extend(windows_manager.build_skills())
    if skills_config.disk.enabled:
        registry.extend(disk.build_skills())
    if skills_config.sysupdate.enabled:
        registry.extend(sysupdate.build_skills())
    if skills_config.processes.enabled:
        registry.extend(processes.build_skills())
    # --- Медиа ---
    if skills_config.music_recognition.enabled:
        registry.extend(music_recognition.build_skills(skills_config.music_recognition))
    if skills_config.qr.enabled:
        registry.extend(qr.build_skills())
    if skills_config.image_gen.enabled:
        registry.extend(image_gen.build_skills(skills_config.image_gen))
    if skills_config.radio.enabled:
        registry.extend(radio.build_skills())
    # --- Новые навыки ---
    registry.extend(volume.build_skills())
    registry.extend(clipboard.build_skills())
    registry.extend(calculator.build_skills())
    registry.extend(battery.build_skills())
    registry.extend(bluetooth.build_skills())
    registry.extend(brightness.build_skills())
    registry.extend(password_gen.build_skills())
    registry.extend(git_helper.build_skills())
    registry.extend(code_snippets.build_skills())
    registry.extend(unit_converter.build_skills())
    registry.extend(email.build_skills())
    registry.extend(self_update.build_skills())
    registry.extend(crypto.build_skills())
    registry.extend(weather_alert.build_skills())
    registry.extend(notion_tasks.build_skills())
    # Таймер (нужен notify)
    timer_skill_svc = TimerSkillService(notify)
    registry.extend(timer_skill.build_skills(timer_skill_svc))
    # Скриншот и диктофон (нужен конфиг)
    registry.extend(screenshot_save.build_skills(skills_config.screenshot_dir))
    registry.extend(dictaphone.build_skills(config.mic))
    registry.extend(youtube_music.build_skills())
    # Голосовые профили
    if skills_config.profiles.enabled and profile_manager is not None:
        registry.extend(profiles_skill._build_skills(profile_manager))
    # Пользовательские плагины
    from .plugins import load_plugins

    plugin_skills = load_plugins(config)
    if plugin_skills:
        registry.extend(plugin_skills)
    return registry, Services(timers, memory_store, browser_session, pomodoro_svc, alarm_svc, timer_skill_svc)
