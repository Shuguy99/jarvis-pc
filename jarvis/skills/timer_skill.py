"""Простой таймер и напоминания."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

from .registry import Skill, object_schema

log = logging.getLogger(__name__)


class TimerSkillService:
    """Служба таймеров."""

    def __init__(self, notify: Callable[[str], None]) -> None:
        self._notify = notify
        self._timers: dict[str, threading.Timer] = {}
        self._counter = 0

    def set_timer(self, seconds: int, label: str = "") -> str:
        self._counter += 1
        tid = f"timer-{self._counter}"
        minutes, secs = divmod(seconds, 60)
        friendly = f"{minutes} мин {secs} сек" if minutes else f"{secs} сек"
        text = f"Таймер \u00ab{label}\u00bb на {friendly} запущен, сэр." if label else f"Таймер на {friendly} запущен, сэр."

        def _fire() -> None:
            self._timers.pop(tid, None)
            msg = f"\u00ab{label}\u00bb \u2014 время вышло, сэр!" if label else "Время вышло, сэр!"
            self._notify(msg)
            log.info("Таймер %s сработал", label or tid)

        t = threading.Timer(seconds, _fire)
        t.daemon = True
        t.start()
        self._timers[tid] = t
        return text

    def list_timers(self) -> str:
        n = len(self._timers)
        return f"Активных таймеров: {n}, сэр." if n else "Нет активных таймеров, сэр."

    def cancel_timer(self) -> str:
        if not self._timers:
            return "Нет активных таймеров, сэр."
        tid = list(self._timers.keys())[-1]
        self._timers[tid].cancel()
        del self._timers[tid]
        return "Последний таймер отменён, сэр."

    def shutdown(self) -> None:
        for t in self._timers.values():
            t.cancel()
        self._timers.clear()


def build_skills(service: TimerSkillService) -> list[Skill]:
    """Навыки таймеров регистрируются в personal.py. Этот модуль предоставляет
    только TimerSkillService для обратной совместимости."""
    return []
