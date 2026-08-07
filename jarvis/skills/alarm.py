"""Будильник: срабатывание в заданное время с голосовым оповещением."""

from __future__ import annotations

import datetime as dt
import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ..config import AlarmConfig
from .registry import Skill, object_schema

log = logging.getLogger(__name__)


@dataclass
class _Alarm:
    """Один будильник."""
    alarm_id: str
    time: dt.time
    label: str
    days: list[int]  # 0=пн, 6=вс. Пустой = один раз.
    timer: threading.Timer | None = None
    next_fire: dt.datetime | None = None


class AlarmService:
    """Сервис будильников."""

    def __init__(self, config: AlarmConfig, notify: Callable[[str], None]) -> None:
        self._config = config
        self._notify = notify
        self._alarms: dict[str, _Alarm] = {}
        self._counter = 0
        self._lock = threading.Lock()
        self._snooze_sec = config.snooze_min * 60

    def _parse_days(self, days_str: str) -> list[int]:
        """Парсит строки дней: 'пн,ср,пт' или 'будни' или 'каждый день'."""
        if not days_str.strip():
            return []  # одноразовый
        days_str = days_str.lower().strip()
        if days_str in ("каждый день", "ежедневно", "все"):
            return list(range(7))
        if days_str in ("будни", "по будням", "рабочие"):
            return [0, 1, 2, 3, 4]
        if days_str in ("выходные", "по выходным"):
            return [5, 6]
        # Явный перечисление
        mapping = {
            "пн": 0, "вт": 1, "ср": 2, "чт": 3, "пт": 4, "сб": 5, "вс": 6,
            "понедельник": 0, "вторник": 1, "среда": 2, "четверг": 3,
            "пятница": 4, "суббота": 5, "воскресенье": 6,
        }
        result = []
        for part in days_str.replace(",", " ").split():
            if part in mapping:
                result.append(mapping[part])
        return sorted(set(result))

    def _calc_next_fire(self, alarm_time: dt.time, days: list[int]) -> dt.datetime:
        """Вычисляет ближайшее время срабатывания."""
        now = dt.datetime.now()
        today_weekday = now.weekday()
        candidate = dt.datetime.combine(now.date(), alarm_time)

        if not days:
            # Одноразовый — если время уже прошло, завтра
            if candidate <= now:
                candidate += dt.timedelta(days=1)
            return candidate

        # Повторяющийся — ищем ближайший подходящий день
        for offset in range(8):
            check = candidate + dt.timedelta(days=offset)
            if check.weekday() in days and check > now:
                return check

        return candidate + dt.timedelta(days=1)

    def _schedule(self, alarm: _Alarm) -> None:
        """Перепланирует будильник."""
        next_fire = self._calc_next_fire(alarm.time, alarm.days)
        alarm.next_fire = next_fire
        delay = (next_fire - dt.datetime.now()).total_seconds()
        if delay < 1:
            return

        def fire() -> None:
            with self._lock:
                current = self._alarms.get(alarm.alarm_id)
                if current is None:
                    return
                if not current.days:
                    # Одноразовый — удаляем
                    self._alarms.pop(alarm.alarm_id, None)
                else:
                    # Повторяющийся — перепланируем
                    self._schedule(current)
            self._notify(f"Будильник! {alarm.label}. {dt.datetime.now().strftime('%H:%M')}")

        if alarm.timer:
            alarm.timer.cancel()
        alarm.timer = threading.Timer(delay, fire)
        alarm.timer.daemon = True
        alarm.timer.start()

    def add(
        self,
        time_str: str,
        label: str = "",
        days: str = "",
    ) -> str:
        """Добавляет будильник. time_str: '7:30' или '07:30'."""
        try:
            parts = time_str.strip().split(":")
            hour = int(parts[0])
            minute = int(parts[1]) if len(parts) > 1 else 0
            alarm_time = dt.time(hour, minute)
        except (ValueError, IndexError):
            return f"Неверный формат времени '{time_str}'. Используйте 'ЧЧ:ММ', сэр."

        parsed_days = self._parse_days(days)
        with self._lock:
            self._counter += 1
            alarm_id = f"alarm{self._counter}"
            alarm = _Alarm(
                alarm_id=alarm_id,
                time=alarm_time,
                label=label.strip() or "Будильник",
                days=parsed_days,
            )
            self._schedule(alarm)
            self._alarms[alarm_id] = alarm

        days_str = ""
        if parsed_days:
            day_names = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
            days_str = f" по {', '.join(day_names[d] for d in parsed_days)}"
        else:
            days_str = " (одноразовый)"

        next_str = alarm.next_fire.strftime("%H:%M %d.%m") if alarm.next_fire else "?"
        return f"Будильник {alarm_id} на {alarm_time.strftime('%H:%M')}{days_str}. Следующее срабатывание: {next_str}, сэр."

    def list_alarms(self) -> str:
        """Показывает активные будильники."""
        with self._lock:
            items = list(self._alarms.values())
        if not items:
            return "Будильников нет, сэр."
        lines = []
        for a in items:
            days_info = "одноразовый" if not a.days else ", ".join(
                str(d) for d in a.days
            )
            next_str = a.next_fire.strftime("%H:%M %d.%m") if a.next_fire else "?"
            lines.append(
                f"  {a.alarm_id}: {a.time.strftime('%H:%M')} — {a.label} "
                f"(дни: {days_info}, следующее: {next_str})"
            )
        return "Активные будильники:\n" + "\n".join(lines)

    def cancel(self, alarm_id: str = "") -> str:
        """Отменяет будильник."""
        with self._lock:
            if not alarm_id:
                for a in self._alarms.values():
                    if a.timer:
                        a.timer.cancel()
                count = len(self._alarms)
                self._alarms.clear()
                return f"Отменил {count} будильников, сэр."
            alarm = self._alarms.pop(alarm_id, None)
        if alarm is None:
            return f"Будильник {alarm_id} не найден, сэр."
        if alarm.timer:
            alarm.timer.cancel()
        return f"Будильник {alarm_id} отменён, сэр."

    def shutdown(self) -> None:
        """Останавливает все будильники."""
        with self._lock:
            for a in self._alarms.values():
                if a.timer:
                    a.timer.cancel()
            self._alarms.clear()


def build_skills(
    config: AlarmConfig, notify: Callable[[str], None]
) -> tuple[list[Skill], AlarmService]:
    """Создаёт навыки будильника."""
    service = AlarmService(config, notify)
    skills = [
        Skill(
            name="set_alarm",
            description="Поставить будильник на указанное время.",
            parameters=object_schema(
                {
                    "time": {"type": "string", "description": "Время в формате ЧЧ:ММ (например '7:30')"},
                    "label": {"type": "string", "description": "Описание (по умолчанию 'Будильник')"},
                    "days": {
                        "type": "string",
                        "description": (
                            "Дни: 'каждый день', 'будни', 'выходные', "
                            "или 'пн,ср,пт'. Пусто = одноразовый."
                        ),
                    },
                },
                required=["time"],
            ),
            handler=lambda time, label="", days="": service.add(time, label, days),
        ),
        Skill(
            name="list_alarms",
            description="Показать активные будильники.",
            parameters=object_schema({}),
            handler=service.list_alarms,
        ),
        Skill(
            name="cancel_alarm",
            description="Отменить будильник по ID или все сразу.",
            parameters=object_schema(
                {
                    "alarm_id": {
                        "type": "string",
                        "description": "ID будильника, пусто = отменить все",
                    }
                }
            ),
            handler=lambda alarm_id="": service.cancel(alarm_id),
        ),
    ]
    return skills, service
