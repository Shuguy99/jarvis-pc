"""Ежедневник: агрегация событий, заметок и таймеров на сегодня."""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from pathlib import Path

from ..config import AgendaConfig
from .registry import Skill, object_schema


def _load_ics_events(ics_dir: str) -> list[dict[str, str]]:
    """Парсит ICS файлы из директории (простейший парсер)."""
    events: list[dict[str, str]] = []
    dir_path = Path(ics_dir).expanduser()
    if not dir_path.is_dir():
        return events
    today = dt.date.today()
    for ics_file in dir_path.glob("*.ics"):
        try:
            text = ics_file.read_text("utf-8")
        except Exception:
            continue
        # Разбиваем на события
        for block in text.split("BEGIN:VEVENT"):
            if "END:VEVENT" not in block:
                continue
            summary = ""
            dtstart = ""
            for line in block.split("\n"):
                line = line.strip()
                if line.upper().startswith("SUMMARY:"):
                    summary = line[8:]
                elif line.upper().startswith("DTSTART"):
                    dtstart = line.split(":")[-1]
            if not summary or not dtstart:
                continue
            # Парсим дату (YYYYMMDD или YYYYMMDDTHHMMSSZ)
            try:
                d = dt.datetime.strptime(dtstart[:8], "%Y%m%d").date()
            except ValueError:
                continue
            if d == today:
                time_str = dtstart[9:11] + ":" + dtstart[11:13] if len(dtstart) > 11 else ""
                events.append({"time": time_str, "summary": summary})
    events.sort(key=lambda e: e["time"])
    return events


def _load_notes(notes_file: str, today_str: str) -> list[str]:
    """Загружает заметки за сегодня из простого md-файла."""
    path = Path(notes_file).expanduser()
    if not path.is_file():
        return []
    result = []
    for line in path.read_text("utf-8").splitlines():
        line = line.strip()
        if not line or not line.startswith("-"):
            continue
        if today_str in line:
            # Извлекаем текст после даты
            idx = line.find(today_str)
            text = line[idx + len(today_str):].strip().lstrip("]").strip()
            if text:
                result.append(text)
    return result


def today_agenda(config: AgendaConfig, timers_list_fn: Callable[[], str] | None = None) -> str:
    """Агрегирует всё на сегодня: календарь, заметки, таймеры."""
    today = dt.date.today()
    today_str = today.strftime("%Y-%m-%d")
    weekday_ru = (
        "понедельник", "вторник", "среда", "четверг",
        "пятница", "суббота", "воскресенье",
    )
    lines = [
        f"{today_str}, {weekday_ru[today.weekday()]}",
    ]

    # Календарь
    events = _load_ics_events(config.ics_dir)
    if events:
        lines.append(f"\nКалендарь ({len(events)} событий):")
        for e in events:
            time_prefix = f"{e['time']} " if e['time'] else ""
            lines.append(f"  {time_prefix}{e['summary']}")
    else:
        lines.append("\nКалендарь: пусто.")

    # Заметки
    notes = _load_notes(config.notes_file, today_str)
    if notes:
        lines.append(f"\nЗаметки ({len(notes)}):")
        for n in notes:
            lines.append(f"  {n[:80]}")

    # Таймеры
    if timers_list_fn:
        timers_text = timers_list_fn()
        if "нет" not in timers_text.lower():
            lines.append(f"\nТаймеры:\n  {timers_text}")

    return "\n".join(lines)


def build_skills(config: AgendaConfig, timers_list_fn: Callable[[], str] | None = None) -> list[Skill]:
    """Создаёт навыки ежедневника."""
    return [
        Skill(
            name="today_agenda",
            description="Показать расписание на сегодня (календарь + заметки + таймеры).",
            parameters=object_schema({}),
            handler=lambda: today_agenda(config, timers_list_fn),
        ),
    ]
