"""Личные навыки: время, заметки, таймеры и напоминания, буфер обмена."""

from __future__ import annotations

import datetime as dt
import threading
from collections.abc import Callable
from pathlib import Path

from ..config import SkillsConfig
from .registry import Skill, object_schema

MONTHS_RU = (
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
)
WEEKDAYS_RU = (
    "понедельник",
    "вторник",
    "среда",
    "четверг",
    "пятница",
    "суббота",
    "воскресенье",
)


def current_time() -> str:
    """Сообщает текущее время."""
    now = dt.datetime.now()
    return f"Сейчас {now.hour:02d}:{now.minute:02d}, сэр."


def current_date() -> str:
    """Сообщает текущую дату и день недели."""
    now = dt.datetime.now()
    return (
        f"Сегодня {WEEKDAYS_RU[now.weekday()]}, "
        f"{now.day} {MONTHS_RU[now.month - 1]} {now.year} года."
    )


class TimerService:
    """Простые таймеры и напоминания на базе threading.Timer."""

    def __init__(self, notify: Callable[[str], None]) -> None:
        self._notify = notify
        self._timers: dict[str, tuple[threading.Timer, dt.datetime, str]] = {}
        self._counter = 0
        self._lock = threading.Lock()

    def add(self, seconds: float, label: str = "") -> str:
        """Ставит таймер и возвращает подтверждение."""
        seconds = max(1.0, float(seconds))
        with self._lock:
            self._counter += 1
            timer_id = f"t{self._counter}"
        text = label.strip() or "Таймер"
        due = dt.datetime.now() + dt.timedelta(seconds=seconds)

        def fire() -> None:
            with self._lock:
                self._timers.pop(timer_id, None)
            self._notify(f"{text} — время вышло, сэр.")

        timer = threading.Timer(seconds, fire)
        timer.daemon = True
        timer.start()
        with self._lock:
            self._timers[timer_id] = (timer, due, text)
        minutes = seconds / 60
        when = f"{minutes:.0f} минут" if minutes >= 1 else f"{seconds:.0f} секунд"
        return f"Таймер {timer_id} на {when} поставлен: {text}."

    def list(self) -> str:
        """Перечисляет активные таймеры."""
        with self._lock:
            items = sorted(self._timers.items(), key=lambda kv: kv[1][1])
        if not items:
            return "Активных таймеров нет, сэр."
        now = dt.datetime.now()
        parts = [
            f"{timer_id}: {text}, осталось {max(0, int((due - now).total_seconds() // 60))} мин"
            for timer_id, (_, due, text) in items
        ]
        return "; ".join(parts) + "."

    def cancel(self, timer_id: str = "") -> str:
        """Отменяет один таймер или все сразу."""
        with self._lock:
            if not timer_id:
                for timer, _, _ in self._timers.values():
                    timer.cancel()
                count = len(self._timers)
                self._timers.clear()
                return f"Отменил {count} таймеров, сэр."
            entry = self._timers.pop(timer_id, None)
        if entry is None:
            return f"Таймер {timer_id} не найден, сэр."
        entry[0].cancel()
        return f"Таймер {timer_id} отменён."

    def shutdown(self) -> None:
        """Останавливает все таймеры при завершении работы."""
        with self._lock:
            for timer, _, _ in self._timers.values():
                timer.cancel()
            self._timers.clear()


def add_note(config: SkillsConfig, text: str) -> str:
    """Дописывает заметку в файл заметок."""
    if not text.strip():
        return "Пустую заметку не сохраняю, сэр."
    path = Path(config.notes_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"- [{stamp}] {text.strip()}\n")
    return "Записал, сэр."


def read_notes(config: SkillsConfig, limit: int = 5) -> str:
    """Читает последние заметки."""
    path = Path(config.notes_file)
    if not path.is_file():
        return "Заметок пока нет, сэр."
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    lines = [line for line in lines if line]
    if not lines:
        return "Заметок пока нет, сэр."
    tail = lines[-max(1, int(limit)) :]
    return "Последние заметки: " + "; ".join(item.lstrip("- ") for item in tail)


def read_clipboard() -> str:
    """Читает текст из буфера обмена."""
    try:
        import pyperclip  # type: ignore[import-not-found]
    except ImportError:
        return "Модуль pyperclip не установлен, сэр."
    text = pyperclip.paste()
    return f"В буфере обмена: {text}" if text else "Буфер обмена пуст, сэр."


def write_clipboard(text: str) -> str:
    """Кладёт текст в буфер обмена."""
    try:
        import pyperclip  # type: ignore[import-not-found]
    except ImportError:
        return "Модуль pyperclip не установлен, сэр."
    pyperclip.copy(text)
    return "Скопировал в буфер обмена, сэр."


def build_skills(config: SkillsConfig, timers: TimerService) -> list[Skill]:
    """Создаёт личные навыки ассистента."""
    return [
        Skill(
            name="current_time",
            description="Узнать текущее время.",
            parameters=object_schema({}),
            handler=current_time,
        ),
        Skill(
            name="current_date",
            description="Узнать текущую дату и день недели.",
            parameters=object_schema({}),
            handler=current_date,
        ),
        Skill(
            name="set_timer",
            description="Поставить таймер или напоминание через N секунд.",
            parameters=object_schema(
                {
                    "seconds": {
                        "type": "number",
                        "description": "Через сколько секунд сработает",
                    },
                    "label": {
                        "type": "string",
                        "description": "О чём напомнить",
                    },
                },
                required=["seconds"],
            ),
            handler=lambda seconds, label="": timers.add(seconds, label),
        ),
        Skill(
            name="list_timers",
            description="Показать активные таймеры.",
            parameters=object_schema({}),
            handler=timers.list,
        ),
        Skill(
            name="cancel_timer",
            description="Отменить таймер по идентификатору или все таймеры.",
            parameters=object_schema(
                {
                    "timer_id": {
                        "type": "string",
                        "description": "Идентификатор таймера, пусто — отменить все",
                    }
                }
            ),
            handler=lambda timer_id="": timers.cancel(timer_id),
        ),
        Skill(
            name="add_note",
            description="Сохранить заметку в личный файл заметок.",
            parameters=object_schema(
                {"text": {"type": "string", "description": "Текст заметки"}},
                required=["text"],
            ),
            handler=lambda text: add_note(config, text),
        ),
        Skill(
            name="read_notes",
            description="Прочитать последние сохранённые заметки.",
            parameters=object_schema(
                {"limit": {"type": "integer", "description": "Сколько заметок"}}
            ),
            handler=lambda limit=5: read_notes(config, limit),
        ),
        Skill(
            name="read_clipboard",
            description="Прочитать текст из буфера обмена.",
            parameters=object_schema({}),
            handler=read_clipboard,
        ),
        Skill(
            name="write_clipboard",
            description="Поместить текст в буфер обмена.",
            parameters=object_schema(
                {"text": {"type": "string", "description": "Текст для копирования"}},
                required=["text"],
            ),
            handler=write_clipboard,
        ),
    ]
