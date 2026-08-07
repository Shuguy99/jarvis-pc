"""Заметки с тегами: создание, поиск, статистика."""

from __future__ import annotations

import datetime as dt
import json
import logging
from pathlib import Path

from ..config import TagsNotesConfig
from .registry import Skill, object_schema

log = logging.getLogger(__name__)


def _load(path: Path) -> list[dict]:
    if path.is_file():
        try:
            return json.loads(path.read_text("utf-8"))
        except Exception:
            return []
    return []


def _save(path: Path, notes: list[dict]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(notes, ensure_ascii=False, indent=2), "utf-8")
    except Exception as exc:
        log.warning("Не удалось сохранить заметки: %s", exc)


def _parse_tags(text: str) -> list[str]:
    """Извлекает #теги из текста."""
    import re
    return list(set(re.findall(r"#(\w+)", text)))


def add_note(config: TagsNotesConfig, text: str, tags: str = "") -> str:
    """Добавляет заметку с тегами."""
    if not text.strip():
        return "Пустая заметка, сэр."
    path = Path(config.notes_file).expanduser()
    notes = _load(path)
    auto_tags = _parse_tags(text)
    manual_tags = [t.strip().lstrip("#") for t in tags.split(",") if t.strip()]
    all_tags = sorted(set(auto_tags + manual_tags))
    note = {
        "text": text.strip(),
        "tags": all_tags,
        "created": dt.datetime.now().isoformat(),
    }
    notes.append(note)
    _save(path, notes)
    tag_str = f" [{', '.join('#' + t for t in all_tags)}]" if all_tags else ""
    return f"Заметка сохранена{tag_str}, сэр."


def search_notes(config: TagsNotesConfig, query: str = "", tag: str = "", limit: int = 10) -> str:
    """Ищет заметки по тексту и/или тегу."""
    path = Path(config.notes_file).expanduser()
    notes = _load(path)
    if not notes:
        return "Заметок нет, сэр."
    tag = tag.strip().lstrip("#")
    results = []
    for note in reversed(notes):
        # Фильтр по тегу
        if tag and tag.lower() not in [t.lower() for t in note.get("tags", [])]:
            continue
        # Фильтр по тексту
        if query and query.lower() not in note["text"].lower():
            continue
        results.append(note)
        if len(results) >= limit:
            break
    if not results:
        criteria = []
        if query:
            criteria.append(f"текст '{query}'")
        if tag:
            criteria.append(f"тег #{tag}")
        return f"По запросу ({', '.join(criteria)}) ничего не найдено, сэр."
    lines = []
    for n in results:
        ts = n.get("created", "?")[:16].replace("T", " ")
        tags_str = " ".join(f"#{t}" for t in n.get("tags", []))
        text = n["text"][:120]
        lines.append(f"  [{ts}] {text}{f'  {tags_str}' if tags_str else ''}")
    return f"Найдено {len(results)}:\n" + "\n".join(lines)


def list_tags(config: TagsNotesConfig) -> str:
    """Показывает все теги и количество заметок."""
    path = Path(config.notes_file).expanduser()
    notes = _load(path)
    if not notes:
        return "Заметок нет, сэр."
    from collections import Counter
    counter: Counter = Counter()
    for note in notes:
        for t in note.get("tags", []):
            counter[t] += 1
    if not counter:
        return "Тегов пока нет. Добавляйте через #тег в тексте заметки, сэр."
    lines = ["Теги (количество заметок):"]
    for tag, count in counter.most_common():
        lines.append(f"  #{tag}: {count}")
    return "\n".join(lines)


def delete_note(config: TagsNotesConfig, index: int = -1) -> str:
    """Удаляет последнюю заметку или по индексу (1-based с конца)."""
    path = Path(config.notes_file).expanduser()
    notes = _load(path)
    if not notes:
        return "Заметок нет, сэр."
    if index < 0:
        # Удалить последнюю
        removed = notes.pop()
        text = removed["text"][:60]
        _save(path, notes)
        return f"Удалена заметка: {text}..., сэр."
    # 1-based с конца: 1 = последняя, 2 = предпоследняя
    real_idx = len(notes) - index
    if real_idx < 0 or real_idx >= len(notes):
        return f"Некорректный индекс {index}. Всего заметок: {len(notes)}, сэр."
    removed = notes.pop(real_idx)
    _save(path, notes)
    return f"Удалена заметка: {removed['text'][:60]}..., сэр."


def build_skills(config: TagsNotesConfig) -> list[Skill]:
    """Создаёт навыки заметок с тегами."""
    return [
        Skill(
            name="tagged_note",
            description="Сохранить заметку с тегами (можно #теги прямо в тексте).",
            parameters=object_schema(
                {
                    "text": {"type": "string", "description": "Текст заметки"},
                    "tags": {"type": "string", "description": "Теги через запятую (необязательно, если есть #теги в тексте)"},
                },
                required=["text"],
            ),
            handler=lambda text, tags="": add_note(config, text, tags),
        ),
        Skill(
            name="search_notes",
            description="Найти заметки по тексту и/или тегу.",
            parameters=object_schema(
                {
                    "query": {"type": "string", "description": "Поиск по тексту (пусто = любой)"},
                    "tag": {"type": "string", "description": "Фильтр по тегу (без #)"},
                    "limit": {"type": "integer", "description": "Максимум результатов (по умолчанию 10)"},
                },
            ),
            handler=lambda query="", tag="", limit=10: search_notes(config, query, tag, limit),
        ),
        Skill(
            name="list_tags",
            description="Показать все теги и количество заметок по каждому.",
            parameters=object_schema({}),
            handler=lambda: list_tags(config),
        ),
        Skill(
            name="delete_note",
            description="Удалить заметку (последнюю или по номеру с конца).",
            parameters=object_schema(
                {"index": {"type": "integer", "description": "1 = последняя, 2 = предпоследняя. Пусто = последняя."}}
            ),
            handler=lambda index=-1: delete_note(config, index),
        ),
    ]
