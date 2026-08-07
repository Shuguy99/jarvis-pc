from __future__ import annotations

import datetime as dt
import json
import logging
from pathlib import Path
from typing import Any

from ..config import HabitsConfig
from .registry import Skill, object_schema

log = logging.getLogger(__name__)


WEEKDAYS_RU = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]


class HabitTracker:
    """Трекер привычек с стикерами за неделю."""

    def __init__(self, config: HabitsConfig) -> None:
        self._path = Path(config.habits_file).expanduser()
        self._habits: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if self._path.is_file():
            try:
                self._habits = json.loads(self._path.read_text("utf-8"))
            except Exception:
                self._habits = {}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._habits, ensure_ascii=False, indent=2), "utf-8"
        )

    def _today(self) -> str:
        return dt.date.today().isoformat()

    def add_habit(self, name: str) -> str:
        """Добавляет привычку для отслеживания."""
        name = name.strip().lower()
        if name in self._habits:
            return f"Привычка '{name}' уже есть, сэр."
        self._habits[name] = {"created": self._today(), "log": {}}
        self._save()
        return f"Привычка '{name}' добавлена, сэр."

    def check_in(self, name: str) -> str:
        """Отмечает привычку как выполненную сегодня."""
        name = name.strip().lower()
        if name not in self._habits:
            # Неопознанная привычка — создаём автоматически
            self._habits[name] = {"created": self._today(), "log": {}}
        today = self._today()
        self._habits[name].setdefault("log", {})[today] = True
        self._save()
        return f"{name} — отмечено, сэр."

    def uncheck(self, name: str) -> str:
        """Снимает отметку за сегодня."""
        name = name.strip().lower()
        if name not in self._habits:
            return f"Привычка '{name}' не найдена, сэр."
        today = self._today()
        self._habits[name].get("log", {}).pop(today, None)
        self._save()
        return f"Отметка '{name}' за сегодня снята, сэр."

    def stats(self, days: int = 7) -> str:
        """Показывает таблицу привычек за N дней."""
        if not self._habits:
            return "Нет отслеживаемых привычек, сэр."
        today = dt.date.today()
        # Заголовок дней
        header = ""
        day_labels = []
        for i in range(days - 1, -1, -1):
            d = today - dt.timedelta(days=i)
            day_labels.append(d.isoformat())
            weekday = WEEKDAYS_RU[d.weekday()]
            short = weekday
            header += f" {short:>3}"

        lines = [f"{'Привычка':<20}{header}"]
        lines.append("-" * (20 + 4 * days))

        for name, habit in sorted(self._habits.items()):
            row = f"{name:<20}"
            for d in day_labels:
                checked = habit.get("log", {}).get(d, False)
                row += "   +" if checked else "   ."
            lines.append(row)

        # Итого за неделю
        total_checks = sum(
            1 for h in self._habits.values()
            for d in day_labels
            if h.get("log", {}).get(d, False)
        )
        possible = len(self._habits) * days
        pct = (total_checks / possible * 100) if possible else 0
        lines.append(f"\nИтого: {total_checks}/{possible} ({pct:.0f}%)")
        return "\n".join(lines)

    def list_habits(self) -> str:
        """Показывает список привычек."""
        if not self._habits:
            return "Нет привычек, сэр."
        lines = [f"Привычки ({len(self._habits)}):"]
        for name, habit in sorted(self._habits.items()):
            streak = self._streak(name, habit)
            lines.append(f"  {name} (серия: {streak} дн.)")
        return "\n".join(lines)

    def _streak(self, name: str, habit: dict) -> int:
        """Считает текущую серию подряд идущих дней."""
        today = dt.date.today()
        streak = 0
        for i in range(365):
            d = (today - dt.timedelta(days=i)).isoformat()
            if habit.get("log", {}).get(d, False):
                streak += 1
            else:
                break
        return streak

    def delete_habit(self, name: str) -> str:
        """Удаляет привычку."""
        name = name.strip().lower()
        if name in self._habits:
            del self._habits[name]
            self._save()
            return f"Привычка '{name}' удалена, сэр."
        return f"Привычка '{name}' не найдена, сэр."


def build_skills(config: HabitsConfig) -> tuple[list[Skill], HabitTracker]:
    """Создаёт навыки трекера привычек."""
    tracker = HabitTracker(config)
    skills = [
        Skill(
            name="habit_add",
            description="Добавить привычку для отслеживания.",
            parameters=object_schema(
                {"name": {"type": "string", "description": "Название привычки"}},
                required=["name"],
            ),
            handler=lambda name: tracker.add_habit(name),
        ),
        Skill(
            name="habit_check",
            description="Отметить привычку как выполненную сегодня.",
            parameters=object_schema(
                {"name": {"type": "string", "description": "Название привычки"}},
                required=["name"],
            ),
            handler=lambda name: tracker.check_in(name),
        ),
        Skill(
            name="habit_stats",
            description="Показать таблицу привычек за неделю (стикеры).",
            parameters=object_schema(
                {"days": {"type": "integer", "description": "Сколько дней (по умолчанию 7)"}}
            ),
            handler=lambda days=7: tracker.stats(days),
        ),
        Skill(
            name="habit_list",
            description="Показать список привычек с текущей серией.",
            parameters=object_schema({}),
            handler=tracker.list_habits,
        ),
        Skill(
            name="habit_delete",
            description="Удалить привычку.",
            parameters=object_schema(
                {"name": {"type": "string", "description": "Название"}},
                required=["name"],
            ),
            handler=lambda name: tracker.delete_habit(name),
        ),
    ]
    return skills, tracker
