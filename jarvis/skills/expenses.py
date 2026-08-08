"""Трекер расходов: логирование и статистика."""

from __future__ import annotations

import datetime as dt
import json
import logging
from pathlib import Path
from typing import Any

from ..config import ExpensesConfig
from .registry import Skill, object_schema

log = logging.getLogger(__name__)


MONTHS_RU = [
    "январь", "февраль", "март", "апрель", "май", "июнь",
    "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь",
]


class ExpenseTracker:
    """Трекер расходов с категориями."""

    def __init__(self, config: ExpensesConfig) -> None:
        self._path = Path(config.expenses_file).expanduser()
        self._expenses: list[dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        if self._path.is_file():
            try:
                self._expenses = json.loads(self._path.read_text("utf-8"))
            except Exception:
                log.debug("expenses: ошибка инициализации self._expenses, используется fallback")
                self._expenses = []

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._expenses, ensure_ascii=False, indent=2), "utf-8"
        )

    def add(self, amount: float, category: str = "", description: str = "") -> str:
        """Добавляет расход."""
        if amount <= 0:
            return "Сумма должна быть положительной, сэр."
        category = category.strip() or "разное"
        expense = {
            "amount": amount,
            "category": category.lower(),
            "description": description.strip(),
            "date": dt.datetime.now().isoformat(timespec="minutes"),
        }
        self._expenses.append(expense)
        self._save()
        return f"Записано: {amount:.0f} руб. ({category}){(' — ' + description) if description else ''}, сэр."

    def summary(self, period: str = "day") -> str:
        """Итоги за период: day, week, month."""
        now = dt.datetime.now()
        if period == "week":
            cutoff = now - dt.timedelta(days=now.weekday())
            cutoff = cutoff.replace(hour=0, minute=0, second=0, microsecond=0)
            period_name = "неделю"
        elif period == "month":
            cutoff = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            period_name = MONTHS_RU[now.month - 1]
        else:
            cutoff = now.replace(hour=0, minute=0, second=0, microsecond=0)
            period_name = "сегодня"

        filtered = [
            e for e in self._expenses
            if dt.datetime.fromisoformat(e["date"]) >= cutoff
        ]

        if not filtered:
            return f"Нет расходов за {period_name}, сэр."

        total = sum(e["amount"] for e in filtered)
        # По категориям
        cats: dict[str, float] = {}
        for e in filtered:
            cat = e["category"]
            cats[cat] = cats.get(cat, 0) + e["amount"]

        lines = [f"Расходы за {period_name}: {total:.0f} руб. ({len(filtered)} записей)"]
        lines.append("")
        for cat, amount in sorted(cats.items(), key=lambda x: -x[1]):
            pct = amount / total * 100
            bar_len = min(int(pct / 5), 20)
            bar = "█" * bar_len + "░" * (20 - bar_len)
            lines.append(f"  {cat:<15} {amount:>8.0f} руб. {bar} {pct:.0f}%")

        return "\n".join(lines)

    def last(self, count: int = 10) -> str:
        """Показывает последние расходы."""
        if not self._expenses:
            return "Расходов пока нет, сэр."
        lines = ["Последние расходы:"]
        for e in reversed(self._expenses[-count:]):
            date_str = e.get("date", "?")[:16]
            desc = f" — {e['description']}" if e.get("description") else ""
            lines.append(f"  [{date_str}] {e['amount']:.0f} руб. ({e['category']}){desc}")
        return "\n".join(lines)

    def categories(self) -> str:
        """Показывает все категории и их totals."""
        cats: dict[str, float] = {}
        for e in self._expenses:
            cat = e["category"]
            cats[cat] = cats.get(cat, 0) + e["amount"]
        if not cats:
            return "Нет категорий, сэр."
        lines = ["Категории (все время):"]
        for cat, amount in sorted(cats.items(), key=lambda x: -x[1]):
            lines.append(f"  {cat}: {amount:.0f} руб.")
        return "\n".join(lines)

    def delete_last(self) -> str:
        """Удаляет последнюю запись."""
        if not self._expenses:
            return "Нет записей для удаления, сэр."
        removed = self._expenses.pop()
        self._save()
        return f"Удалено: {removed['amount']:.0f} руб. ({removed['category']}), сэр."


def build_skills(config: ExpensesConfig) -> tuple[list[Skill], ExpenseTracker]:
    """Создаёт навыки трекера расходов."""
    tracker = ExpenseTracker(config)
    skills = [
        Skill(
            name="expense_add",
            description="Записать расход.",
            parameters=object_schema(
                {
                    "amount": {"type": "number", "description": "Сумма"},
                    "category": {"type": "string", "description": "Категория (еда, транспорт, ...)"},
                    "description": {"type": "string", "description": "Описание"},
                },
                required=["amount"],
            ),
            handler=lambda amount, category="", description="": tracker.add(amount, category, description),
        ),
        Skill(
            name="expense_summary",
            description="Итоги расходов за период (day/week/month).",
            parameters=object_schema(
                {"period": {"type": "string", "description": "day | week | month"}}
            ),
            handler=lambda period="day": tracker.summary(period),
        ),
        Skill(
            name="expense_last",
            description="Показать последние расходы.",
            parameters=object_schema(
                {"count": {"type": "integer", "description": "Сколько (по умолчанию 10)"}}
            ),
            handler=lambda count=10: tracker.last(count),
        ),
        Skill(
            name="expense_categories",
            description="Показать категории расходов.",
            parameters=object_schema({}),
            handler=tracker.categories,
        ),
        Skill(
            name="expense_delete_last",
            description="Удалить последнюю запись расхода.",
            parameters=object_schema({}),
            handler=tracker.delete_last,
        ),
    ]
    return skills, tracker
