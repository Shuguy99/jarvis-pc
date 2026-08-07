from __future__ import annotations

import datetime as dt
import json
import logging
from pathlib import Path
from typing import Any

from ..config import NotesConfig
from .registry import Skill, object_schema

log = logging.getLogger(__name__)


class TaggedNotes:
    """Заметки с тегами, хранящиеся в JSON."""

    def __init__(self, config: NotesConfig) -> None:
        self._path = Path(config.notes_db).expanduser()
        self._notes: list[dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        if self._path.is_file():
            try:
                self._notes = json.loads(self._path.read_text("utf-8"))
            except Exception:
                self._notes = []

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._notes, ensure_ascii=False, indent=2), "utf-8"
        )

    def _parse_tags(self, text: str) -> tuple[list[str], str]:
        """Извлекает #теги из текста, возвращает (теги, очищенный текст)."""
        tags: list[str] = []
        parts: list[str] = []
        for word in text.split():
            if word.startswith("#") and len(word) > 1:
                tags.append(word[1:].lower())
            else:
                parts.append(word)
        return tags, " ".join(parts)

    def add(self, text: str) -> str:
        """Добавляет заметку. Теги извлекаются из #тег в тексте."""
        text = text.strip()
        if not text:
            return "Пустая заметка не сохраняется, сэр."
        tags, clean = self._parse_tags(text)
        note = {
            "id": max((n["id"] for n in self._notes), default=0) + 1,
            "text": clean,
            "tags": tags,
            "created": dt.datetime.now().isoformat(timespec="minutes"),
        }
        self._notes.append(note)
        self._save()
        tag_str = f" [теги: {', '.join(tags)}]" if tags else ""
        return f"Заметка #{note['id']} сохранена{tag_str}, сэр."

    def search(self, query: str = "", tag: str = "", limit: int = 10) -> str:
        """Ищет заметки по тексту и/или тегу."""
        results = self._notes
        if tag:
            tag = tag.lower().lstrip("#")
            results = [n for n in results if tag in n.get("tags", [])]
        if query:
            q = query.lower()
            results = [n for n in results if q in n.get("text", "").lower()]
        if not results:
            return "Ничего не найдено, сэр."
        lines = []
        for note in reversed(results[-limit:]):
            tags_str = f" [{', '.join('#' + t for t in note.get('tags', []))}]" if note.get("tags") else ""
            lines.append(
                f"  #{note['id']} [{note.get('created', '?')}]{tags_str} {note.get('text', '')[:100]}"
            )
        return f"Найдено {len(results)}:\n" + "\n".join(lines)

    def list_all(self, tag: str = "", limit: int = 20) -> str:
        """Показывает последние заметки, опционально по тегу."""
        return self.search(query="", tag=tag, limit=limit)

    def delete(self, note_id: int) -> str:
        """Удаляет заметку по ID."""
        for i, note in enumerate(self._notes):
            if note["id"] == note_id:
                self._notes.pop(i)
                self._save()
                return f"Заметка #{note_id} удалена, сэр."
        return f"Заметка #{note_id} не найдена, сэр."

    def tags(self) -> str:
        """Показывает все теги с количеством."""
        counter: dict[str, int] = {}
        for note in self._notes:
            for t in note.get("tags", []):
                counter[t] = counter.get(t, 0) + 1
        if not counter:
            return "Тегов пока нет, сэр."
        lines = ["Теги:"]
        for tag, count in sorted(counter.items(), key=lambda x: -x[1]):
            lines.append(f"  #{tag} — {count}")
        return "\n".join(lines)


def build_skills(config: NotesConfig) -> tuple[list[Skill], TaggedNotes]:
    """Создаёт навыки заметок с тегами."""
    store = TaggedNotes(config)
    skills = [
        Skill(
            name="note_add",
            description=(
                "Сохранить заметку. Теги указываются в тексте через #, "
                "например: 'Встреча в 15 #работа #важное'"
            ),
            parameters=object_schema(
                {"text": {"type": "string", "description": "Текст заметки (теги через #)"}},
                required=["text"],
            ),
            handler=lambda text: store.add(text),
        ),
        Skill(
            name="note_search",
            description="Найти заметки по тексту и/или тегу.",
            parameters=object_schema(
                {
                    "query": {"type": "string", "description": "Поиск по тексту"},
                    "tag": {"type": "string", "description": "Фильтр по тегу"},
                },
            ),
            handler=lambda query="", tag="": store.search(query, tag),
        ),
        Skill(
            name="note_list",
            description="Показать последние заметки.",
            parameters=object_schema(
                {
                    "tag": {"type": "string", "description": "Фильтр по тегу"},
                    "limit": {"type": "integer", "description": "Сколько (по умолчанию 20)"},
                },
            ),
            handler=lambda tag="", limit=20: store.list_all(tag, limit),
        ),
        Skill(
            name="note_delete",
            description="Удалить заметку по ID.",
            parameters=object_schema(
                {"note_id": {"type": "integer", "description": "ID заметки"}},
                required=["note_id"],
            ),
            handler=lambda note_id: store.delete(note_id),
        ),
        Skill(
            name="note_tags",
            description="Показать все теги и их количество.",
            parameters=object_schema({}),
            handler=store.tags,
        ),
    ]
    return skills, store
