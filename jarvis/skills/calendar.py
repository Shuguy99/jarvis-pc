"""Навыки календаря: события на сегодня, добавление событий через ICS файлы."""

from __future__ import annotations

import logging
import re
from datetime import datetime, date, timedelta
from pathlib import Path

from ..config import CalendarConfig
from .registry import Skill, object_schema

log = logging.getLogger(__name__)


# Простой ICS парсер (без зависимости от icalendar)
_DT_RE = re.compile(r"^DTSTART[^:]*:(.+)$", re.MULTILINE | re.IGNORECASE)
_SUMMARY_RE = re.compile(r"^SUMMARY:(.+)$", re.MULTILINE | re.IGNORECASE)
_LOCATION_RE = re.compile(r"^LOCATION:(.+)$", re.MULTILINE | re.IGNORECASE)
_DESCRIPTION_RE = re.compile(r"^DESCRIPTION:(.+)$", re.MULTILINE | re.IGNORECASE)
_VEVENT_RE = re.compile(r"BEGIN:VEVENT\r?\n(.*?)\r?\nEND:VEVENT", re.DOTALL | re.IGNORECASE)


def _parse_ics_datetime(dt_str: str) -> datetime | None:
    """Парсит дату/время из ICS формата."""
    dt_str = dt_str.strip().rstrip("Z")
    # Пробуем парсить с временем: YYYYMMDDTHHMMSS
    try:
        return datetime.strptime(dt_str, "%Y%m%dT%H%M%S")
    except ValueError:
        pass
    # Только дата: YYYYMMDD
    try:
        d = datetime.strptime(dt_str, "%Y%m%d").date()
        return datetime.combine(d, datetime.min.time())
    except ValueError:
        pass
    return None


def _parse_ics_events(ics_text: str) -> list[dict]:
    """Парсит события из ICS текста. Возвращает список словарей."""
    ics_text = ics_text.replace('\r\n', '\n').replace('\r', '\n')
    events = []
    for match in _VEVENT_RE.finditer(ics_text):
        block = match.group(1)
        dt_match = _DT_RE.search(block)
        if not dt_match:
            continue
        dt = _parse_ics_datetime(dt_match.group(1))
        if dt is None:
            continue
        summary_match = _SUMMARY_RE.search(block)
        location_match = _LOCATION_RE.search(block)
        desc_match = _DESCRIPTION_RE.search(block)
        events.append({
            "dt": dt,
            "summary": summary_match.group(1).strip() if summary_match else "Без названия",
            "location": location_match.group(1).strip() if location_match else "",
            "description": desc_match.group(1).strip() if desc_match else "",
        })
    return events


def _load_ics_files(ics_dir: str) -> list[dict]:
    """Загружает все .ics файлы из директории."""
    events = []
    dir_path = Path(ics_dir).expanduser()
    if not dir_path.is_dir():
        return events
    for ics_file in sorted(dir_path.glob("*.ics")):
        try:
            text = ics_file.read_text(encoding="utf-8")
            events.extend(_parse_ics_events(text))
        except Exception as exc:
            log.warning("Не удалось прочитать %s: %s", ics_file, exc)
    return events


def _format_time(dt: datetime) -> str:
    """Форматирует время в читаемом виде."""
    return dt.strftime("%H:%M")


def _relative_day(d: date) -> str:
    """Возвращает относительное название дня (сегодня, завтра, послезавтра)."""
    today = date.today()
    if d == today:
        return "сегодня"
    if d == today + timedelta(days=1):
        return "завтра"
    if d == today + timedelta(days=2):
        return "послезавтра"
    return d.strftime("%d.%m")


def today_events(config: CalendarConfig) -> str:
    """Показывает события на сегодня из ICS файлов."""
    events = _load_ics_files(config.ics_dir)
    today = date.today()
    today_events_list = [
        e for e in events
        if e["dt"].date() == today
    ]
    today_events_list.sort(key=lambda e: e["dt"])
    if not today_events_list:
        return "На сегодня нет событий, сэр."
    lines = [f"События на сегодня ({today.strftime('%d.%m.%Y')}):"]
    for ev in today_events_list:
        time_str = _format_time(ev["dt"])
        line = f"{time_str} — {ev['summary']}"
        if ev["location"]:
            line += f", {ev['location']}"
        lines.append(line)
    if len(today_events_list) > 5:
        lines = lines[:6]
        rest = len(today_events_list) - 5
        word = "событие" if rest == 1 else "события" if 2 <= rest <= 4 else "событий"
        lines.append(f"... и ещё {rest} {word}.")
    return "\n".join(lines)


def add_event(config: CalendarConfig, summary: str, day: str = "", time_str: str = "",
             location: str = "", description: str = "") -> str:
    """Добавляет событие в ICS файл календаря."""
    dir_path = Path(config.ics_dir).expanduser()
    dir_path.mkdir(parents=True, exist_ok=True)

    # Определяем дату
    today = date.today()
    if day:
        day_lower = day.lower()
        if day_lower == "завтра":
            target_date = today + timedelta(days=1)
        elif day_lower == "послезавтра":
            target_date = today + timedelta(days=2)
        else:
            try:
                target_date = datetime.strptime(day, "%d.%m").date()
                target_date = target_date.replace(year=today.year)
            except ValueError:
                return f"Не понял дату '{day}'. Формат: дд.мм, 'завтра' или 'послезавтра'."
    else:
        target_date = today

    # Парсим время
    if time_str:
        try:
            hour, minute = map(int, time_str.replace(":", "").split())
            dt = datetime(target_date.year, target_date.month, target_date.day, hour, minute)
        except (ValueError, IndexError):
            return f"Не понял время '{time_str}'. Формат: ЧЧ:ММ."
    else:
        dt = datetime(target_date.year, target_date.month, target_date.day, 9, 0)

    # Формируем ICS
    dt_str = dt.strftime("%Y%m%dT%H%M%S")
    end_dt = dt + timedelta(hours=1)
    end_str = end_dt.strftime("%Y%m%dT%H%M%S")
    ics_content = (
        "BEGIN:VCALENDAR\n"
        "VERSION:2.0\n"
        "PRODID:-//Jarvis//Calendar//RU\n"
        "BEGIN:VEVENT\n"
        f"DTSTART:{dt_str}\n"
        f"DTEND:{end_str}\n"
        f"SUMMARY:{summary}\n"
    )
    if location:
        ics_content += f"LOCATION:{location}\n"
    if description:
        ics_content += f"DESCRIPTION:{description}\n"
    ics_content += "END:VEVENT\nEND:VCALENDAR\n"

    # Сохраняем в файл
    safe_name = re.sub(r"[^\w\-]", "_", summary)[:30]
    filename = f"{dt.strftime('%Y%m%d')}_{safe_name}.ics"
    file_path = dir_path / filename
    file_path.write_text(ics_content, encoding="utf-8")
    rel = _relative_day(target_date)
    return f"Добавлено: {summary}, {rel} в {dt.strftime('%H:%M')}."


def upcoming_events(config: CalendarConfig, days: int = 3) -> str:
    """Показывает ближайшие события на несколько дней."""
    events = _load_ics_files(config.ics_dir)
    today = date.today()
    limit = today + timedelta(days=days)
    upcoming = [
        e for e in events
        if today <= e["dt"].date() <= limit
    ]
    upcoming.sort(key=lambda e: e["dt"])
    if not upcoming:
        return f"Ближайшие {days} дней событий нет, сэр."
    lines = [f"Ближайшие события ({days} дней):"]
    for ev in upcoming[:10]:
        rel = _relative_day(ev["dt"].date())
        time_str = _format_time(ev["dt"])
        line = f"{rel} {time_str} — {ev['summary']}"
        if ev["location"]:
            line += f", {ev['location']}"
        lines.append(line)
    return "\n".join(lines)


def build_skills(config: CalendarConfig) -> list[Skill]:
    """Создаёт навыки календаря."""
    return [
        Skill(
            name="today_events",
            description="Показать события на сегодня из календаря.",
            parameters=object_schema({}),
            handler=lambda: today_events(config),
        ),
        Skill(
            name="add_event",
            description=(
                "Добавить событие в календарь. "
                "День можно указать как дд.мм, 'завтра', 'послезавтра' или пустое (сегодня)."
            ),
            parameters=object_schema(
                {
                    "summary": {
                        "type": "string",
                        "description": "Название события",
                    },
                    "day": {
                        "type": "string",
                        "description": "Дата: 'завтра', 'послезавтра' или дд.мм",
                    },
                    "time_str": {
                        "type": "string",
                        "description": "Время в формате ЧЧ:ММ",
                    },
                    "location": {
                        "type": "string",
                        "description": "Место проведения (необязательно)",
                    },
                    "description": {
                        "type": "string",
                        "description": "Описание события (необязательно)",
                    },
                },
                required=["summary"],
            ),
            handler=lambda summary, day="", time_str="", location="", description="": add_event(
                config, summary, day, time_str, location, description
            ),
        ),
        Skill(
            name="upcoming_events",
            description="Показать ближайшие события на несколько дней.",
            parameters=object_schema(
                {
                    "days": {
                        "type": "integer",
                        "description": "На сколько дней вперёд показать (по умолчанию 3)",
                    },
                },
            ),
            handler=lambda days=3: upcoming_events(config, days),
        ),
    ]
