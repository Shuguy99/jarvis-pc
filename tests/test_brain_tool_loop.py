"""Тесты цикла вызова инструментов и конфигурации."""

from __future__ import annotations

from pathlib import Path

from jarvis.brain.base import Brain, Message, ToolCall, parse_arguments
from jarvis.config import BrainConfig, load_config
from jarvis.skills.registry import Skill, SkillRegistry, object_schema


class ScriptedBrain(Brain):
    """Мозг, отдающий заранее заданные ответы."""

    def __init__(self, config: BrainConfig, skills: SkillRegistry, replies: list[Message]):
        super().__init__(config, skills)
        self._replies = replies
        self.seen: list[list[Message]] = []

    def _chat(self, messages: list[Message]) -> Message:
        self.seen.append(list(messages))
        return self._replies.pop(0)


def _registry(calls: list[tuple[str, dict[str, object]]]) -> SkillRegistry:
    """Реестр, записывающий вызовы навыка."""
    registry = SkillRegistry()

    def handler(level: int) -> str:
        calls.append(("set_volume", {"level": level}))
        return f"Громкость {level}"

    registry.register(
        Skill(
            name="set_volume",
            description="",
            parameters=object_schema({"level": {"type": "integer"}}, ["level"]),
            handler=handler,
        )
    )
    return registry


def test_tool_call_result_returned_to_model() -> None:
    """Результат навыка попадает в историю и модель отвечает финальным текстом."""
    calls: list[tuple[str, dict[str, object]]] = []
    replies = [
        Message("assistant", "", [ToolCall("c1", "set_volume", {"level": 30})]),
        Message("assistant", "Готово, сэр."),
    ]
    brain = ScriptedBrain(BrainConfig(), _registry(calls), replies)
    assert brain.ask("сделай тише") == "Готово, сэр."
    assert calls == [("set_volume", {"level": 30})]
    tool_messages = [m for m in brain.history if m.role == "tool"]
    assert tool_messages[0].content == "Громкость 30"
    assert tool_messages[0].tool_call_id == "c1"


def test_system_prompt_is_prepended(tmp_path, monkeypatch) -> None:
    """Системный промпт всегда первый в запросе к модели."""
    import jarvis.skills.personality as mod
    monkeypatch.setattr(mod, "_PROFILES_FILE", tmp_path / "p.json")
    mod._manager = None
    brain = ScriptedBrain(BrainConfig(), SkillRegistry(), [Message("assistant", "да")])
    brain.ask("привет")
    assert brain.seen[0][0].role == "system"
    assert "Джарвис" in brain.seen[0][0].content


def test_tool_iterations_are_capped() -> None:
    """Бесконечный цикл вызовов инструментов прерывается."""
    calls: list[tuple[str, dict[str, object]]] = []
    config = BrainConfig(max_tool_iterations=3)
    replies = [
        Message("assistant", "", [ToolCall(f"c{i}", "set_volume", {"level": 10})]) for i in range(3)
    ]
    brain = ScriptedBrain(config, _registry(calls), replies)
    assert "Прерываю цикл" in brain.ask("крути громкость")
    assert len(calls) == 3


def test_parse_arguments_handles_json_and_garbage() -> None:
    """Аргументы приходят и строкой JSON, и мусором."""
    assert parse_arguments('{"level": 5}') == {"level": 5}
    assert parse_arguments("не json") == {}
    assert parse_arguments(None) == {}
    assert parse_arguments({"a": 1}) == {"a": 1}


def test_config_defaults_and_yaml_override(tmp_path: Path) -> None:
    """Конфиг из файла переопределяет только указанные поля."""
    assert load_config(None).brain.backend in {"ollama", "openai", "offline"}
    path = tmp_path / "config.yaml"
    path.write_text(
        "brain:\n  backend: openai\n  temperature: 0.1\nui:\n  enabled: false\n",
        encoding="utf-8",
    )
    config = load_config(path)
    assert config.brain.backend == "openai"
    assert config.brain.temperature == 0.1
    assert config.ui.enabled is False
    assert config.stt.language == "ru"
