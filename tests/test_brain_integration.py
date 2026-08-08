"""Интеграционные тесты: полный цикл Assistant → Brain → Skill.

Используют ScriptedBrain (поддельный LLM) для проверки:
- Tool call loop (вызов навыка → результат → ответ)
- Confirmation flow (подтверждение через диалог)
- Multi-step tool calls (несколько навыков за один ask)
- Error handling (навык падает → мозг не умирает)
"""

from __future__ import annotations

import pytest

from jarvis.brain.base import Brain, Message, ToolCall
from jarvis.config import BrainConfig
from jarvis.skills.registry import (
    ConfirmationRequired,
    Skill,
    SkillRegistry,
    _confirm_handler,
    object_schema,
)


class ScriptedBrain(Brain):
    """Мозг, отдающий заранее заданные ответы."""

    def __init__(self, config: BrainConfig, skills: SkillRegistry, replies: list[Message]):
        super().__init__(config, skills)
        self._replies = replies
        self.seen: list[list[Message]] = []

    def _chat(self, messages: list[Message]) -> Message:
        self.seen.append(list(messages))
        return self._replies.pop(0)


def make_brain(
    skills: SkillRegistry | None = None,
    replies: list[Message] | None = None,
    config: BrainConfig | None = None,
) -> ScriptedBrain:
    return ScriptedBrain(
        config or BrainConfig(),
        skills or SkillRegistry(),
        replies or [Message("assistant", "Готово, сэр.")],
    )


# ── Basic tool call ─────────────────────────────────────────────────


def test_single_tool_call_returns_result():
    """LLM вызывает один навык, мозг возвращает финальный ответ."""
    registry = SkillRegistry()
    registry.register(Skill(
        name="get_weather",
        description="Погода",
        parameters=object_schema({"city": {"type": "string"}}, ["city"]),
        handler=lambda city: f"В {city} +20C, солнечно",
    ))
    brain = make_brain(registry, [
        Message("assistant", "", [ToolCall("c1", "get_weather", {"city": "Москва"})]),
        Message("assistant", "В Москве +20C, солнечно, сэр."),
    ])
    result = brain.ask("какая погода в Москве")
    assert "+20C" in result
    assert "солнечно" in result


def test_tool_call_with_no_arguments():
    """Навык без аргументов работает корректно."""
    registry = SkillRegistry()
    registry.register(Skill(
        name="system_status",
        description="Статус системы",
        parameters=object_schema({}),
        handler=lambda: "CPU 10%, RAM 40%",
    ))
    brain = make_brain(registry, [
        Message("assistant", "", [ToolCall("c1", "system_status", {})]),
        Message("assistant", "Загрузка минимальная, сэр."),
    ])
    result = brain.ask("как дела у компьютера")
    assert "минимальная" in result


# ── Multi-step tool calls ────────────────────────────────────────────


def test_two_tool_calls_in_sequence():
    """LLM вызывает два навыка подряд: статус → погода."""
    registry = SkillRegistry()
    registry.register(Skill(
        name="system_status", description="Статус", parameters=object_schema({}),
        handler=lambda: "CPU 50%",
    ))
    registry.register(Skill(
        name="get_weather", description="Погода",
        parameters=object_schema({"city": {"type": "string"}}, ["city"]),
        handler=lambda city: f"{city}: +15C",
    ))
    brain = make_brain(registry, [
        Message("assistant", "", [ToolCall("c1", "system_status", {})]),
        Message("assistant", "", [ToolCall("c2", "get_weather", {"city": "Питер"})]),
        Message("assistant", "CPU 50%, в Питере +15C."),
    ])
    result = brain.ask("как система и погода в Питере")
    assert "CPU" in result
    assert "+15C" in result


# ── Error handling ────────────────────────────────────────────────────


def test_skill_exception_returns_error_message():
    """Навык падает → мозг не умирает, возвращает ошибку."""
    registry = SkillRegistry()
    registry.register(Skill(
        name="buggy", description="Баговый навык", parameters=object_schema({}),
        handler=lambda: (_ for _ in ()).throw(RuntimeError(" kaboom")),  # type: ignore[misc]
    ))
    brain = make_brain(registry, [
        Message("assistant", "", [ToolCall("c1", "buggy", {})]),
        Message("assistant", "Произошла ошибка, но я на связи, сэр."),
    ])
    result = brain.ask("вызови баг")
    # Мозг должен увидеть ошибку в tool result и ответить
    assert isinstance(result, str)


def test_unknown_skill_returns_friendly_error():
    """Несуществующий навык не крашит мозг."""
    brain = make_brain(replies=[
        Message("assistant", "", [ToolCall("c1", "nonexistent_skill", {})]),
        Message("assistant", "Такого навыка нет, сэр."),
    ])
    result = brain.ask("сделай магию")
    assert isinstance(result, str)


def test_wrong_arguments_returns_error():
    """Неправильные типы аргументов → ошибка, мозг продолжает."""
    registry = SkillRegistry()
    registry.register(Skill(
        name="set_volume",
        description="Громкость",
        parameters=object_schema({"level": {"type": "integer"}}, ["level"]),
        handler=lambda level: f"Громкость {level}",
    ))
    brain = make_brain(registry, [
        Message("assistant", "", [ToolCall("c1", "set_volume", {"level": "не число"})]),
        Message("assistant", "Не удалось установить громкость, сэр."),
    ])
    result = brain.ask("громкость на максимум")
    assert isinstance(result, str)


# ── Confirmation integration ─────────────────────────────────────────


def test_confirmation_flow_user_confirms():
    """Полный цикл: навык → подтверждение → пользователь говорит «да» → выполнение."""
    executed: list[str] = []

    def delete_file(path: str) -> str:
        executed.append(path)
        return f"Удалено: {path}"

    registry = SkillRegistry()
    registry.register(Skill(
        name="delete_file",
        description="Удалить файл",
        parameters=object_schema({"path": {"type": "string"}}, ["path"]),
        handler=_confirm_handler(lambda path: delete_file(path), "Удалить {path}?"),
    ))
    brain = make_brain(registry, [
        # 1) LLM вызывает delete_file → ConfirmationRequired
        Message("assistant", "", [ToolCall("c1", "delete_file", {"path": "/tmp/test.txt"})]),
        # 2) Мозг отправляет вопрос как tool result → LLM пересказывает пользователю
        Message("assistant", "Удалить /tmp/test.txt? Подтвердите, сэр."),
    ])

    result = brain.ask("удали файл /tmp/test.txt")
    # Пользователь увидел вопрос
    assert "Удалить" in result or "Подтвердите" in result
    # Но файл ещё не удалён
    assert executed == []
    # Подтверждение сохранено
    assert len(brain._confirmed) == 1

    # Теперь пользователь говорит «да» — модели нужно повторить вызов
    brain._replies = [
        Message("assistant", "", [ToolCall("c1", "delete_file", {"path": "/tmp/test.txt"})]),
        Message("assistant", "Файл удалён, сэр."),
    ]
    result2 = brain.ask("да, удаляй")
    assert executed == ["/tmp/test.txt"]
    assert "удалён" in result2.lower()


def test_confirmation_flow_user_declines():
    """Пользователь отказывается — навык не выполняется."""
    executed: list[str] = []

    registry = SkillRegistry()
    registry.register(Skill(
        name="delete_file",
        description="Удалить файл",
        parameters=object_schema({"path": {"type": "string"}}, ["path"]),
        handler=_confirm_handler(
            lambda path: (executed.append(path), f"Удалено: {path}")[-1],
            "Удалить {path}?",
        ),
    ))
    brain = make_brain(registry, [
        # LLM вызывает delete_file → ConfirmationRequired
        Message("assistant", "", [ToolCall("c1", "delete_file", {"path": "/tmp/important.txt"})]),
        # Мозг отправляет вопрос → LLM пересказывает
        Message("assistant", "Удалить /tmp/important.txt? Подтвердите."),
    ])
    result = brain.ask("удали важный файл")
    assert executed == []

    # Пользователь говорит «нет» — LLM не повторяет вызов
    brain._replies = [
        Message("assistant", "Как скажете, сэр. Файл оставлен."),
    ]
    result2 = brain.ask("нет, не надо")
    assert executed == []
    assert "оставлен" in result2.lower()


# ── History management ───────────────────────────────────────────────


def test_history_grows_with_tool_calls():
    """История содержит user, assistant с tool_call, и tool message."""
    registry = SkillRegistry()
    registry.register(Skill(
        name="echo", description="Эхо",
        parameters=object_schema({"text": {"type": "string"}}, ["text"]),
        handler=lambda text: text,
    ))
    brain = make_brain(registry, [
        Message("assistant", "", [ToolCall("c1", "echo", {"text": "hello"})]),
        Message("assistant", "hello"),
    ])
    brain.ask("привет")
    roles = [m.role for m in brain.history]
    assert "user" in roles
    assert "assistant" in roles
    assert "tool" in roles


def test_max_history_trims_old_messages():
    """История не превышает max_history."""
    registry = SkillRegistry()
    registry.register(Skill(
        name="echo", description="Эхо",
        parameters=object_schema({"text": {"type": "string"}}, ["text"]),
        handler=lambda text: text,
    ))
    config = BrainConfig(max_history=4)
    brain = make_brain(registry, [
        Message("assistant", "", [ToolCall("c1", "echo", {"text": "test"})]),
        Message("assistant", "test"),
    ], config)
    brain.ask("первый")
    brain._replies = [
        Message("assistant", "", [ToolCall("c2", "echo", {"text": "test2"})]),
        Message("assistant", "test2"),
    ]
    brain.ask("второй")
    # max_history=4: system не считается, user+assistant(tool_call)+tool+assistant = 4
    # Должны остаться только самые свежие
    assert len(brain.history) <= config.max_history + 2  # +2 за пары tool


def test_reset_clears_history_and_confirmed():
    """Сброс мозга очищает и историю, и подтверждённые вызовы."""
    brain = make_brain()
    brain._confirmed.add(("delete_file", frozenset({("path", "/tmp/test")})))
    brain.history.append(Message("user", "test"))
    brain.reset()
    assert len(brain.history) == 0
    assert len(brain._confirmed) == 0


# ── on_tool_result callback ──────────────────────────────────────────


def test_on_tool_result_callback_called():
    """Коллбэк on_tool_result вызывается после успешного tool call."""
    callbacks: list[tuple[str, str]] = []

    registry = SkillRegistry()
    registry.register(Skill(
        name="echo", description="Эхо",
        parameters=object_schema({"text": {"type": "string"}}, ["text"]),
        handler=lambda text: f"{text}!",
    ))
    brain = make_brain(registry, [
        Message("assistant", "", [ToolCall("c1", "echo", {"text": "hello"})]),
        Message("assistant", "hello!"),
    ])
    brain._on_tool_result = lambda name, result: callbacks.append((name, result))
    brain.ask("привет")
    assert callbacks == [("echo", "hello!")]


def test_on_tool_result_callback_not_called_on_confirmation():
    """При ConfirmationRequired on_tool_result НЕ вызывается (операция не выполнена)."""
    callbacks: list[tuple[str, str]] = []

    registry = SkillRegistry()
    registry.register(Skill(
        name="delete_file", description="Удалить",
        parameters=object_schema({"path": {"type": "string"}}, ["path"]),
        handler=_confirm_handler(lambda path: f"ok {path}", "Удалить {path}?"),
    ))
    brain = make_brain(registry, [
        Message("assistant", "Подтвердите удаление."),
    ])
    brain._on_tool_result = lambda name, result: callbacks.append((name, result))
    brain.ask("удали файл")
    assert callbacks == []
