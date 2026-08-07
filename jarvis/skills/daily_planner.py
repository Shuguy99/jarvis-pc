"""Ежедневник: задачи на сегодня, агрегация из заметок и календаря."""

from __future__ import annotations

import datetime as dt
import json
import logging
from pathlib import Path

from ..config import DailyPlannerConfig
from .registry import Skill, object_schema

log = logging.getLogger(__name__)


def _load(path: Path) -> dict[str, list[dict]]:
    """Загружает задачи: {date: [{text, done, priority}]}."""
    if path.is_file():
        try:
            return json.loads(path.read_text("utf-8"))
        except Exception:
            return {}
    return {}


def _save(path: Path, data: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
    except Exception as exc:
        log.warning("Не удалось сохранить ежедневник: %s", exc)


def _today_key() -> str:
    return dt.date.today().isoformat()


def add_task(config: DailyPlannerConfig, text: str, priority: str = "normal", date: str = "") -> str:
    """Добавляет задачу на день."""
    if not text.strip():
        return "Пустая задача, сэр."
    key = date or _today_key()
    path = Path(config.planner_file).expanduser()
    data = _load(path)
    if key not in data:
        data[key] = []
    data[key].append({
        "text": text.strip(),
        "done": False,
        "priority": priority.lower(),
        "created": dt.datetime.now().isoformat(),
    })
    _save(path, data)
    date_str = f" на {key}" if key != _today_key() else " на сегодня"
    return f"Задача добавлена{date_str}: {text.strip()}, сэр."


def list_tasks(config: DailyPlannerConfig, date: str = "", show_done: bool = False) -> str:
    """Показывает задачи на день."""
    key = date or _today_key()
    path = Path(config.planner_file).expanduser()
    data = _load(path)
    tasks = data.get(key, [])
    if not tasks:
        date_str = f" на {key}" if key != _today_key() else " на сегодня"
        return f"Задач{date_str} нет, сэр."
    lines = [f"Задачи на {key}:"]
    priority_order = {"high": 0, "normal": 1, "low": 2}
    sorted_tasks = sorted(enumerate(tasks), key=lambda x: priority_order.get(x[1].get("priority", "normal"), 1))
    for idx, task in sorted_tasks:
        status = "[x]" if task.get("done") else "[ ]"
        if not show_done and task.get("done"):
            continue
        prio = task.get("priority", "normal")
        prio_mark = "!" if prio == "high" else ("~" if prio == "low" else " ")
        lines.append(f"  {status} {prio_mark} {task['text']}")
    if len(lines) == 1:
        return f"Все задачи выполнены на {key}, сэр!"
    done_count = sum(1 for t in tasks if t.get("done"))
    lines.append(f"Выполнено: {done_count}/{len(tasks)}")
    return "\n".join(lines)


def done_task(config: DailyPlannerConfig, task_index: int = 0) -> str:
    """Отмечает задачу как выполненную (1-based, 1 = первая невыполненная)."""
    key = _today_key()
    path = Path(config.planner_file).expanduser()
    data = _load(path)
    tasks = data.get(key, [])
    if not tasks:
        return "Задач на сегодня нет, сэр."
    undone = [(i, t) for i, t in enumerate(tasks) if not t.get("done")]
    if not undone:
        return "Все задачи уже выполнены, сэр!"
    if task_index < 1 or task_index > len(undone):
        return f"Некорректный номер. Невыполненных задач: {len(undone)}, сэр."
    real_idx, task = undone[task_index - 1]
    tasks[real_idx]["done"] = True
    data[key] = tasks
    _save(path, data)
    remaining = len(undone) - 1
    return f"Выполнено: {task['text']}. Осталось: {remaining}, сэр."


def clear_done(config: DailyPlannerConfig) -> str:
    """Удаляет выполненные задачи за сегодня."""
    key = _today_key()
    path = Path(config.planner_file).expanduser()
    data = _load(path)
    tasks = data.get(key, [])
    before = len(tasks)
    remaining = [t for t in tasks if not t.get("done")]
    removed = before - len(remaining)
    if removed == 0:
        return "Нет выполненных задач для очистки, сэр."
    data[key] = remaining
    _save(path, data)
    return f"Удалено {removed} выполненных задач, сэр."


def build_skills(config: DailyPlannerConfig) -> list[Skill]:
    """Создаёт навыки ежедневника."""
    return [
        Skill(
            name="add_task",
            description="Добавить задачу на сегодня (или другую дату).",
            parameters=object_schema(
                {
                    "text": {"type": "string", "description": "Текст задачи"},
                    "priority": {"type": "string", "description": "high | normal | low"},
                    "date": {"type": "string", "description": "Дата YYYY-MM-DD (пусто = сегодня)"},
                },
                required=["text"],
            ),
            handler=lambda text, priority="normal", date="": add_task(config, text, priority, date),
        ),
        Skill(
            name="list_tasks",
            description="Показать задачи на день.",
            parameters=object_schema(
                {
                    "date": {"type": "string", "description": "Дата YYYY-MM-DD (пусто = сегодня)"},
                    "show_done": {"type": "boolean", "description": "Показать выполненные (по умолчанию false)"},
                },
            ),
            handler=lambda date="", show_done=False: list_tasks(config, date, show_done),
        ),
        Skill(
            name="done_task",
            description="Отметить задачу как выполненную.",
            parameters=object_schema(
                {"task_index": {"type": "integer", "description": "Номер задачи (1 = первая невыполненная)"}},
            ),
            handler=lambda task_index=1: done_task(config, task_index),
        ),
        Skill(
            name="clear_done",
            description="Удалить выполненные задачи за сегодня.",
            parameters=object_schema({}),
            handler=lambda: clear_done(config),
        ),
    ]
