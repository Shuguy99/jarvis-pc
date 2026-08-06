"""Тесты реестра навыков."""

from __future__ import annotations

import pytest

from jarvis.skills.registry import Skill, SkillRegistry, object_schema


def _skill(name: str = "ping") -> Skill:
    """Простой навык для тестов."""
    return Skill(
        name=name,
        description="Проверка",
        parameters=object_schema({"value": {"type": "string"}}),
        handler=lambda value="pong": value,
    )


def test_duplicate_registration_rejected() -> None:
    """Повторная регистрация имени запрещена."""
    registry = SkillRegistry()
    registry.register(_skill())
    with pytest.raises(ValueError):
        registry.register(_skill())


def test_tool_specs_have_openai_shape() -> None:
    """Описания инструментов соответствуют формату function calling."""
    registry = SkillRegistry()
    registry.register(_skill())
    spec = registry.tool_specs()[0]
    assert spec["type"] == "function"
    assert spec["function"]["name"] == "ping"
    assert spec["function"]["parameters"]["type"] == "object"


def test_unknown_skill_returns_message() -> None:
    """Вызов неизвестного навыка не падает, а возвращает текст."""
    assert "не найден" in SkillRegistry().call("nope", {})


def test_bad_arguments_return_message() -> None:
    """Некорректные аргументы превращаются в понятный ответ."""
    registry = SkillRegistry()
    registry.register(_skill())
    assert "Некорректные аргументы" in registry.call("ping", {"wrong": 1})


def test_handler_exception_is_contained() -> None:
    """Исключение внутри навыка не пробрасывается наружу."""
    registry = SkillRegistry()

    def boom() -> str:
        raise RuntimeError("реактор перегрелся")

    registry.register(
        Skill(name="boom", description="", parameters=object_schema({}), handler=boom)
    )
    assert "реактор перегрелся" in registry.call("boom")
