"""RAG: загрузка текста и ответы на вопросы по ключевым словам.

Простая реализация без векторной БД: хранит документы в памяти,
находит наиболее релевантный по совпадению слов (TF-IDF-подобный скоринг).
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from .registry import Skill, object_schema

log = logging.getLogger(__name__)

# Хранилище: имя → текст
_store: dict[str, str] = {}


def _tokenize(text: str) -> set[str]:
    """Нормализует текст в набор слов."""
    words = re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9]+", text.lower())
    return set(words)


def _score(question: str, document: str) -> float:
    """Простой TF-IDF-подобный скор: пересечение слов вопроса и документа."""
    q_words = _tokenize(question)
    if not q_words:
        return 0.0
    d_words = _tokenize(document)
    if not d_words:
        return 0.0
    # IDF: штраф за слишком частые слова (длина документа > 200 слов)
    total_d = len(d_words)
    score = 0.0
    for w in q_words:
        if w in d_words:
            # TF-подобный: сколько раз слово встречается в документе
            tf = document.lower().count(w) / max(total_d, 1)
            score += tf + 0.5  # базовый бонус за совпадение
    # Нормализация по длине документа, чтобы длинные не побеждали всегда
    normalized = score * (100 / max(total_d, 1))
    return normalized


def rag_load(name: str, text: str) -> str:
    """Сохранить текстовый фрагмент в хранилище."""
    if not name.strip():
        return "Имя документа не может быть пустым, сэр."
    _store[name] = text
    return f"Документ «{name}» загружен ({len(text)} символов), сэр."


def rag_load_file(path: str) -> str:
    """Прочитать файл и сохранить его в хранилище."""
    p = Path(path).expanduser()
    if not p.is_file():
        return f"Файл {path} не найден, сэр."
    try:
        text = p.read_text("utf-8")
    except Exception as exc:
        return f"Не удалось прочитать файл: {exc}, сэр."
    name = p.stem
    _store[name] = text
    return f"Файл «{name}» загружен ({len(text)} символов), сэр."


def rag_ask(question: str) -> str:
    """Найти наиболее релевантный документ по вопросу."""
    if not _store:
        return "Хранилище пусто. Загрузите документы через rag_load или rag_load_file, сэр."
    if not question.strip():
        return "Задайте вопрос, сэр."
    best_name = ""
    best_score = -1.0
    best_text = ""
    for name, text in _store.items():
        s = _score(question, text)
        if s > best_score:
            best_score = s
            best_name = name
            best_text = text
    if best_score <= 0:
        return "Ничего подходящего не найдено, сэр."
    # Обрезаем ответ до разумной длины
    snippet = best_text[:500]
    if len(best_text) > 500:
        snippet += "..."
    return (
        f"📎 Наиболее релевантный документ: «{best_name}» (скор: {best_score:.2f})\n\n"
        f"{snippet}"
    )


def rag_list() -> str:
    """Показать загруженные документы."""
    if not _store:
        return "Хранилище пусто, сэр."
    lines = [f"Загружено документов: {len(_store)}"]
    for name, text in _store.items():
        lines.append(f"  {name} — {len(text)} символов")
    return "\n".join(lines)


def build_skills() -> list[Skill]:
    """Создаёт навыки RAG."""
    return [
        Skill(
            name="rag_load",
            description=(
                "Загрузить текстовый фрагмент в память RAG-хранилища."
            ),
            parameters=object_schema(
                {
                    "name": {"type": "string", "description": "Имя документа"},
                    "text": {"type": "string", "description": "Текст документа"},
                },
                required=["name", "text"],
            ),
            handler=rag_load,
        ),
        Skill(
            name="rag_load_file",
            description="Прочитать файл и загрузить его содержимое в RAG.",
            parameters=object_schema(
                {
                    "path": {"type": "string", "description": "Путь к текстовому файлу"},
                },
                required=["path"],
            ),
            handler=rag_load_file,
        ),
        Skill(
            name="rag_ask",
            description=(
                "Задать вопрос — будет найден наиболее релевантный документ "
                "по совпадению ключевых слов и возвращён фрагмент текста."
            ),
            parameters=object_schema(
                {
                    "question": {"type": "string", "description": "Вопрос"},
                },
                required=["question"],
            ),
            handler=rag_ask,
        ),
        Skill(
            name="rag_list",
            description="Показать список загруженных в RAG документов.",
            parameters=object_schema({}),
            handler=rag_list,
        ),
    ]
