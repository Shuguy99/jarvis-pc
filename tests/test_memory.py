"""Тесты долговременной памяти на JSON-хранилище."""

from __future__ import annotations

from pathlib import Path

from jarvis.config import MemoryConfig
from jarvis.skills.memory import JsonMemory, Memory, build_skills


def _memory(tmp_path: Path) -> Memory:
    """Память с гарантированно локальным JSON-хранилищем."""
    return Memory(MemoryConfig(backend="json", path=str(tmp_path)))


def test_remember_then_recall(tmp_path: Path) -> None:
    """Запомненный факт находится по ключевому слову вопроса."""
    memory = _memory(tmp_path)
    assert memory.remember("номер паспорта 1234 567890") == "Запомнил, сэр."
    assert "1234 567890" in memory.recall("паспорта")


def test_recall_without_match(tmp_path: Path) -> None:
    """Если ничего не найдено, ассистент говорит об этом прямо."""
    memory = _memory(tmp_path)
    memory.remember("любимый чай — сенча")
    assert "нет записей" in memory.recall("автомобиль")


def test_empty_fact_is_rejected(tmp_path: Path) -> None:
    """Пустые факты не сохраняются."""
    memory = _memory(tmp_path)
    assert "Пустой факт" in memory.remember("   ")
    assert memory.list_facts() == "Память пока пуста, сэр."


def test_forget_removes_matching_facts(tmp_path: Path) -> None:
    """Забывание удаляет только подходящие записи."""
    memory = _memory(tmp_path)
    memory.remember("пароль от вайфая старк2008")
    memory.remember("день рождения жены 12 мая")
    assert "Забыл 1" in memory.forget("вайфая")
    assert "старк2008" not in memory.list_facts()
    assert "12 мая" in memory.list_facts()


def test_disabled_memory_is_inert(tmp_path: Path) -> None:
    """Отключённая память не пишет и не читает."""
    memory = Memory(MemoryConfig(enabled=False, backend="json", path=str(tmp_path)))
    assert "отключена" in memory.remember("что-то")
    assert "отключена" in memory.recall("что-то")


def test_json_store_survives_corrupted_file(tmp_path: Path) -> None:
    """Повреждённый файл памяти не ломает ассистента."""
    store = JsonMemory(tmp_path)
    (tmp_path / "memory.json").write_text("{не json", encoding="utf-8")
    store.add("новая запись", "")
    assert store.all(10) == ["новая запись"]


def test_memory_skills_are_registered(tmp_path: Path) -> None:
    """Навыки памяти доступны модели через function calling."""
    skills, _ = build_skills(MemoryConfig(backend="json", path=str(tmp_path)))
    assert {skill.name for skill in skills} == {
        "remember_fact",
        "recall_fact",
        "list_memory",
        "forget_fact",
    }
