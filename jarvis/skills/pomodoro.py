"""Помодоро-таймер: рабочие сессии, перерывы, статистика."""

from __future__ import annotations

import datetime as dt
import json
import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..config import PomodoroConfig
from .registry import Skill, object_schema

log = logging.getLogger(__name__)


@dataclass
class _Session:
    """Активная помодоро-сессия."""
    kind: str  # "work" | "break" | "long_break"
    timer: threading.Timer
    due: dt.datetime
    duration_min: int


class PomodoroService:
    """Сервис помодоро-таймера с персистентной статистикой."""

    def __init__(self, config: PomodoroConfig, notify: Callable[[str], None]) -> None:
        self._config = config
        self._notify = notify
        self._session: _Session | None = None
        self._lock = threading.Lock()
        self._done_today: int = 0
        self._today_str: str = ""
        self._stats_path = Path(config.stats_file).expanduser()
        self._load_today()

    # ── Персистентность ──────────────────────────────────────────────

    def _load_today(self) -> None:
        today = dt.date.today().isoformat()
        self._today_str = today
        if self._stats_path.is_file():
            try:
                data = json.loads(self._stats_path.read_text("utf-8"))
                self._done_today = data.get(today, 0)
            except Exception:
                log.debug("pomodoro: ошибка инициализации self._done_today, используется fallback")
                self._done_today = 0

    def _save_today(self) -> None:
        try:
            self._stats_path.parent.mkdir(parents=True, exist_ok=True)
            data: dict[str, Any] = {}
            if self._stats_path.is_file():
                try:
                    data = json.loads(self._stats_path.read_text("utf-8"))
                except Exception:
                    log.debug("pomodoro: повреждённый файл статистики, пересоздаём")
            data[self._today_str] = self._done_today
            self._stats_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
        except Exception as exc:
            log.warning("Не удалось сохранить статистику помодоро: %s", exc)

    # ── Управление сессиями ──────────────────────────────────────────

    def start(self, kind: str = "work", duration_min: int = 0) -> str:
        """Запускает помодоро-сессию."""
        with self._lock:
            if self._session is not None:
                remaining = max(0, int((self._session.due - dt.datetime.now()).total_seconds() // 60))
                return (
                    f"Уже идёт {self._session.kind} сессия, "
                    f"осталось {remaining} мин. Сначала отмените, сэр."
                )

            if kind == "work":
                duration_min = duration_min or self._config.work_min
                label = "Помодоро"
            elif kind == "long_break":
                duration_min = duration_min or self._config.long_break_min
                label = "Длинный перерыв"
            else:
                duration_min = duration_min or self._config.break_min
                label = "Перерыв"

            seconds = duration_min * 60
            due = dt.datetime.now() + dt.timedelta(seconds=seconds)

            def fire() -> None:
                with self._lock:
                    self._session = None
                    if kind == "work":
                        self._done_today += 1
                        self._save_today()
                        self._notify(
                            f"{label} завершён! Завершено сегодня: {self._done_today}. "
                            f"Время перерыва, сэр."
                        )
                    else:
                        self._notify(f"{label} окончен, сэр. За работу!")

            timer = threading.Timer(seconds, fire)
            timer.daemon = True
            timer.start()
            self._session = _Session(kind=kind, timer=timer, due=due, duration_min=duration_min)

        return f"{label} на {duration_min} мин запущен, сэр."

    def status(self) -> str:
        """Статус текущей сессии."""
        with self._lock:
            if self._session is None:
                return "Нет активной помодоро-сессии, сэр."
            s = self._session
            remaining = max(0, (s.due - dt.datetime.now()).total_seconds())
            mins = int(remaining // 60)
            secs = int(remaining % 60)
        kind_ru = {"work": "Работа", "break": "Перерыв", "long_break": "Длинный перерыв"}
        return f"{kind_ru.get(s.kind, s.kind)}: {mins}:{secs:02d} осталось, сэр."

    def stats(self, days: int = 7) -> str:
        """Статистика помодоро за последние N дней."""
        lines = [f"Статистика помодоро (последние {days} дней):"]
        if self._stats_path.is_file():
            try:
                data = json.loads(self._stats_path.read_text("utf-8"))
            except Exception:
                log.debug("pomodoro: ошибка (line 131)")
                data = {}
        else:
            data = {}
        today = dt.date.today()
        total = 0
        for i in range(days - 1, -1, -1):
            d = (today - dt.timedelta(days=i)).isoformat()
            count = data.get(d, 0)
            total += count
            marker = " ← сегодня" if i == 0 else ""
            lines.append(f"  {d}: {count} помодоро{marker}")
        lines.append(f"Всего: {total}")
        return "\n".join(lines)

    def cancel(self) -> str:
        """Отменяет текущую сессию."""
        with self._lock:
            if self._session is None:
                return "Нет активной сессии, сэр."
            self._session.timer.cancel()
            self._session = None
        return "Помодоро отменён, сэр."


def build_skills(
    config: PomodoroConfig, notify: Callable[[str], None]
) -> tuple[list[Skill], PomodoroService]:
    """Создаёт навыки помодоро."""
    service = PomodoroService(config, notify)
    skills = [
        Skill(
            name="pomodoro_start",
            description=(
                "Запустить помодоро-сессию. kind: work (по умолчанию), "
                "break, long_break. Можно указать duration_min."
            ),
            parameters=object_schema(
                {
                    "kind": {
                        "type": "string",
                        "description": "work | break | long_break",
                    },
                    "duration_min": {
                        "type": "integer",
                        "description": "Длительность в минутах (по умолчанию из конфига)",
                    },
                },
            ),
            handler=lambda kind="work", duration_min=0: service.start(kind, duration_min),
        ),
        Skill(
            name="pomodoro_status",
            description="Статус текущей помодоро-сессии.",
            parameters=object_schema({}),
            handler=service.status,
        ),
        Skill(
            name="pomodoro_stats",
            description="Статистика помодоро за последние N дней.",
            parameters=object_schema(
                {"days": {"type": "integer", "description": "Сколько дней (по умолчанию 7)"}}
            ),
            handler=lambda days=7: service.stats(days),
        ),
        Skill(
            name="pomodoro_cancel",
            description="Отменить текущую помодоро-сессию.",
            parameters=object_schema({}),
            handler=service.cancel,
        ),
    ]
    return skills, service
