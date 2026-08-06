"""Долговременная память: Джарвис запоминает факты и находит их по смыслу."""

from __future__ import annotations

import datetime as dt
import json
import logging
import re
import uuid
from pathlib import Path
from typing import Protocol

from ..config import MemoryConfig
from .registry import Skill, object_schema

log = logging.getLogger(__name__)

COLLECTION = "jarvis_memory"
WORD_RE = re.compile(r"\w+", re.UNICODE)


class MemoryStore(Protocol):
    """Хранилище фактов с поиском по запросу."""

    def add(self, text: str, tag: str) -> str: ...

    def search(self, query: str, top_k: int) -> list[str]: ...

    def all(self, limit: int) -> list[str]: ...

    def forget(self, query: str) -> int: ...


def _stamp() -> str:
    """Метка времени записи."""
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M")


def _tokens(text: str) -> set[str]:
    """Слова запроса в нижнем регистре для простого поиска."""
    return {word.lower() for word in WORD_RE.findall(text.replace("ё", "е"))}


class JsonMemory:
    """Резервное хранилище: JSON-файл и поиск по пересечению слов."""

    def __init__(self, path: Path) -> None:
        self._path = path / "memory.json"
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> list[dict[str, str]]:
        if not self._path.is_file():
            return []
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            log.warning("Файл памяти повреждён, начинаю заново: %s", self._path)
            return []
        return data if isinstance(data, list) else []

    def _save(self, items: list[dict[str, str]]) -> None:
        self._path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")

    def add(self, text: str, tag: str) -> str:
        items = self._load()
        entry_id = uuid.uuid4().hex
        items.append({"id": entry_id, "text": text, "tag": tag, "created": _stamp()})
        self._save(items)
        return entry_id

    def search(self, query: str, top_k: int) -> list[str]:
        wanted = _tokens(query)
        scored: list[tuple[int, str]] = []
        for item in self._load():
            score = len(wanted & _tokens(f"{item['text']} {item.get('tag', '')}"))
            if score:
                scored.append((score, item["text"]))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [text for _, text in scored[:top_k]]

    def all(self, limit: int) -> list[str]:
        return [item["text"] for item in self._load()[-limit:]]

    def forget(self, query: str) -> int:
        items = self._load()
        wanted = _tokens(query)
        kept = [item for item in items if not wanted & _tokens(item["text"])]
        self._save(kept)
        return len(items) - len(kept)


class ChromaMemory:
    """Векторная память на ChromaDB с семантическим поиском."""

    def __init__(self, path: Path) -> None:
        import chromadb

        path.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(path))
        self._collection = self._client.get_or_create_collection(COLLECTION)

    def add(self, text: str, tag: str) -> str:
        entry_id = uuid.uuid4().hex
        self._collection.add(
            ids=[entry_id],
            documents=[text],
            metadatas=[{"tag": tag, "created": _stamp()}],
        )
        return entry_id

    def search(self, query: str, top_k: int) -> list[str]:
        if not self._collection.count():
            return []
        result = self._collection.query(query_texts=[query], n_results=top_k)
        documents = result.get("documents") or [[]]
        return [str(item) for item in documents[0]]

    def all(self, limit: int) -> list[str]:
        result = self._collection.get(limit=limit)
        return [str(item) for item in result.get("documents") or []]

    def forget(self, query: str) -> int:
        matches = self.search(query, top_k=50)
        if not matches:
            return 0
        deleted_total = 0
        for match in matches:
            try:
                found = self._collection.get(where_document={"$contains": match})
                ids = list(found.get("ids") or [])
                if ids:
                    self._collection.delete(ids=ids)
                    deleted_total += len(ids)
            except Exception:
                log.warning("Не удалось удалить запись из ChromaDB: %s", match, exc_info=True)
        return deleted_total


def build_store(config: MemoryConfig) -> MemoryStore:
    """Создаёт хранилище: ChromaDB, если доступна, иначе JSON."""
    path = Path(config.path)
    if config.backend in {"auto", "chroma"}:
        try:
            return ChromaMemory(path)
        except Exception as exc:  # chromadb тяжёлая, падать из-за неё нельзя
            if config.backend == "chroma":
                log.warning("ChromaDB недоступна (%s), перехожу на JSON-память", exc)
            else:
                log.info("ChromaDB не используется (%s), беру JSON-память", exc)
    return JsonMemory(path)


class Memory:
    """Фасад памяти: сохраняет факты и отвечает на вопросы о них."""

    def __init__(self, config: MemoryConfig) -> None:
        self.config = config
        self._store: MemoryStore | None = None

    @property
    def store(self) -> MemoryStore:
        """Ленивая инициализация хранилища."""
        if self._store is None:
            self._store = build_store(self.config)
        return self._store

    def remember(self, text: str, tag: str = "") -> str:
        """Сохраняет факт в долговременную память."""
        fact = text.strip()
        if not fact:
            return "Пустой факт запоминать не буду, сэр."
        if not self.config.enabled:
            return "Долговременная память отключена в конфигурации, сэр."
        self.store.add(fact, tag.strip())
        return "Запомнил, сэр."

    def recall(self, query: str, top_k: int = 0) -> str:
        """Ищет факты по смыслу запроса."""
        if not self.config.enabled:
            return "Долговременная память отключена в конфигурации, сэр."
        limit = top_k if top_k > 0 else self.config.top_k
        matches = self.store.search(query, limit)
        if not matches:
            return f"В памяти нет записей про «{query}», сэр."
        return "Из памяти: " + "; ".join(matches)

    def list_facts(self, limit: int = 10) -> str:
        """Перечисляет последние запомненные факты."""
        if not self.config.enabled:
            return "Долговременная память отключена в конфигурации, сэр."
        items = self.store.all(max(1, limit))
        if not items:
            return "Память пока пуста, сэр."
        return "Помню: " + "; ".join(items)

    def forget(self, query: str) -> str:
        """Удаляет из памяти записи, подходящие под запрос."""
        if not self.config.enabled:
            return "Долговременная память отключена в конфигурации, сэр."
        removed = self.store.forget(query)
        if not removed:
            return f"Нечего забывать про «{query}», сэр."
        return f"Забыл {removed} записей про «{query}», сэр."


def build_skills(config: MemoryConfig) -> tuple[list[Skill], Memory]:
    """Создаёт навыки памяти и сам объект памяти."""
    memory = Memory(config)
    skills = [
        Skill(
            name="remember_fact",
            description=(
                "Запомнить факт о пользователе надолго: данные, предпочтения, пароли-подсказки, "
                "номера, привычки. Используй, когда пользователь говорит «запомни»."
            ),
            parameters=object_schema(
                {
                    "text": {"type": "string", "description": "Что запомнить"},
                    "tag": {"type": "string", "description": "Категория факта"},
                },
                required=["text"],
            ),
            handler=lambda text, tag="": memory.remember(text, tag),
        ),
        Skill(
            name="recall_fact",
            description=("Найти в долговременной памяти ранее запомненный факт по смыслу вопроса."),
            parameters=object_schema(
                {
                    "query": {"type": "string", "description": "О чём вспомнить"},
                    "top_k": {"type": "integer", "description": "Сколько записей вернуть"},
                },
                required=["query"],
            ),
            handler=lambda query, top_k=0: memory.recall(query, top_k),
        ),
        Skill(
            name="list_memory",
            description="Показать последние записи из долговременной памяти.",
            parameters=object_schema(
                {"limit": {"type": "integer", "description": "Сколько записей"}}
            ),
            handler=lambda limit=10: memory.list_facts(limit),
        ),
        Skill(
            name="forget_fact",
            description="Удалить из долговременной памяти записи по запросу.",
            parameters=object_schema(
                {"query": {"type": "string", "description": "Что забыть"}},
                required=["query"],
            ),
            handler=lambda query: memory.forget(query),
        ),
    ]
    return skills, memory
