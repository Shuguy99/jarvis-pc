"""Тесты механизма подтверждения опасных операций."""

from __future__ import annotations

import pytest

from jarvis.skills.registry import (
    ConfirmationRequired,
    SkillRegistry,
    Skill,
    _confirm_handler,
    object_schema,
)


# ── ConfirmationRequired exception ────────────────────────────────────


def test_confirmation_required_carries_message():
    exc = ConfirmationRequired("Удалить файл test.txt?")
    assert exc.message == "Удалить файл test.txt?"
    assert str(exc) == "Удалить файл test.txt?"


def test_confirmation_required_is_exception():
    assert issubclass(ConfirmationRequired, Exception)


# ── _confirm_handler wrapper ─────────────────────────────────────────


def test_confirm_handler_raises_on_call():
    def dangerous(path: str) -> str:
        return f"deleted {path}"

    wrapped = _confirm_handler(dangerous, "Удалить {path}?")
    with pytest.raises(ConfirmationRequired) as ctx:
        wrapped(path="/tmp/test.txt")
    assert ctx.value.message == "Удалить /tmp/test.txt?"


def test_confirm_handler_preserves_original():
    def dangerous(path: str) -> str:
        return f"deleted {path}"

    wrapped = _confirm_handler(dangerous, "Удалить {path}?")
    assert wrapped._original is dangerous
    # Оригинальная функция работает нормально
    assert wrapped._original(path="/tmp/test.txt") == "deleted /tmp/test.txt"


def test_confirm_handler_formats_message():
    def kill(name: str) -> str:
        return f"killed {name}"

    wrapped = _confirm_handler(kill, 'Закрыть "{name}"?')
    with pytest.raises(ConfirmationRequired) as ctx:
        wrapped(name="chrome")
    assert ctx.value.message == 'Закрыть "chrome"?'


# ── SkillRegistry.call() propagates ConfirmationRequired ────────────


def test_registry_propagates_confirmation():
    def dangerous(path: str) -> str:
        raise ConfirmationRequired(f"Удалить {path}?")

    registry = SkillRegistry()
    registry.register(Skill(
        name="delete_file",
        description="test",
        parameters=object_schema({"path": {"type": "string"}}, required=["path"]),
        handler=dangerous,
    ))
    with pytest.raises(ConfirmationRequired):
        registry.call("delete_file", {"path": "/tmp/test"})


def test_registry_catches_other_exceptions():
    def buggy() -> str:
        raise RuntimeError("boom")

    registry = SkillRegistry()
    registry.register(Skill(
        name="buggy_skill",
        description="test",
        parameters=object_schema({}),
        handler=buggy,
    ))
    result = registry.call("buggy_skill")
    assert "завершился ошибкой" in result


def test_registry_unknown_skill_returns_error():
    registry = SkillRegistry()
    result = registry.call("nonexistent")
    assert "не найден" in result


# ── Brain.ask() confirmation flow ────────────────────────────────────


class FakeMessage:
    """Упрощённое сообщение для тестов Brain."""
    def __init__(self, role: str, content: str = "", tool_calls: list | None = None,
                 tool_call_id: str = "", name: str = ""):
        self.role = role
        self.content = content
        self.tool_calls = tool_calls or []
        self.tool_call_id = tool_call_id
        self.name = name


class FakeToolCall:
    def __init__(self, id: str, name: str, arguments: dict):
        self.id = id
        self.name = name
        self.arguments = arguments


class FakeBrain:
    """Минимальная реализация Brain для тестирования confirmation flow."""

    def __init__(self):
        from jarvis.skills.registry import SkillRegistry, Skill, object_schema
        from jarvis.config import BrainConfig
        from jarvis.skills.registry import ConfirmationRequired

        self.config = BrainConfig()
        self.skills = SkillRegistry()
        self.history: list[FakeMessage] = []
        self._confirmed: set[tuple[str, frozenset]] = set()
        self._call_log: list[str] = []

        # Навык, требующий подтверждения
        executed = []

        def dangerous_handler(path: str) -> str:
            executed.append(path)
            if ("delete_file", frozenset({("path", path)})) not in self._confirmed:
                raise ConfirmationRequired(f"Удалить {path}?")
            return f"Удалено: {path}"

        self.executed = executed

        registry = SkillRegistry()
        registry.register(Skill(
            name="delete_file",
            description="test delete",
            parameters=object_schema({"path": {"type": "string"}}, required=["path"]),
            handler=dangerous_handler,
        ))
        self.skills = registry

        self._chat_count = 0
        self._chat_responses: list[FakeMessage] = []

    def _chat(self, messages: list) -> FakeMessage:
        """Имитирует ответы LLM."""
        self._chat_count += 1
        if self._chat_responses:
            return self._chat_responses.pop(0)
        return FakeMessage("assistant", "Готово.")


def test_confirmation_flow_ask_user():
    """При первом вызове навык запрашивает подтверждение, Brain передаёт вопрос пользователю."""
    brain = FakeBrain()
    # LLM сначала вызывает delete_file
    tool_call = FakeToolCall("call_1", "delete_file", {"path": "/tmp/test.txt"})
    first_response = FakeMessage("assistant", "", tool_calls=[tool_call])
    # После подтверждения LLM передаёт вопрос пользователю
    user_reply = FakeMessage("assistant", "Удалить /tmp/test.txt? Подтвердите.")
    brain._chat_responses = [user_reply]

    # Имитируем ask() логику
    brain.history.append(FakeMessage("user", "удали файл test.txt"))
    reply = first_response
    brain.history.append(reply)

    for call in reply.tool_calls:
        call_key = (call.name, frozenset((k, v) for k, v in (call.arguments or {}).items()))
        is_confirmed = call_key in brain._confirmed
        try:
            result = brain.skills.call(call.name, call.arguments)
        except ConfirmationRequired as cr:
            assert not is_confirmed
            brain._confirmed.add(call_key)
            confirm_msg = f"Требуется подтверждение: {cr.message}"
            assert "Удалить /tmp/test.txt?" in confirm_msg
            # Подтверждение сохранено
            assert call_key in brain._confirmed
            return  # Тест прошёл

    pytest.fail("Ожидалось ConfirmationRequired")


def test_confirmation_second_call_executes():
    """При повторном вызове с теми же аргументами — выполняется напрямую."""
    from jarvis.skills.registry import ConfirmationRequired, Skill, object_schema, _confirm_handler

    executed = []

    def delete_file(path: str) -> str:
        executed.append(path)
        return f"Удалено: {path}"

    registry = SkillRegistry()
    wrapped = _confirm_handler(delete_file, "Удалить {path}?")
    registry.register(Skill(
        name="delete_file",
        description="test",
        parameters=object_schema({"path": {"type": "string"}}, required=["path"]),
        handler=wrapped,
    ))

    # Первый вызов — подтверждение
    with pytest.raises(ConfirmationRequired):
        registry.call("delete_file", {"path": "/tmp/test"})
    assert executed == []

    # Прямой вызов оригинала (имитация подтверждённого повторного вызова)
    result = wrapped._original(path="/tmp/test")
    assert result == "Удалено: /tmp/test"
    assert executed == ["/tmp/test"]


# ── Integration: проверка что защищённые навыки действительно защищены ──


def test_delete_file_skill_has_confirmation():
    """Навык delete_file обёрнут в _confirm_handler."""
    from jarvis.skills import build_registry
    from jarvis.config import Config
    from jarvis.skills.registry import ConfirmationRequired

    config = Config()
    registry, services = build_registry(config, lambda t: None)
    try:
        services.shutdown()
    except Exception:
        pass

    skill = registry._skills["delete_file"]
    assert hasattr(skill.handler, '_original'), "delete_file handler должен иметь _original"
    with pytest.raises(ConfirmationRequired):
        skill.handler(path="/tmp/nonexistent_test_file")


def test_close_app_skill_has_confirmation():
    """Навык close_app обёрнут в _confirm_handler."""
    from jarvis.skills import build_registry
    from jarvis.config import Config
    from jarvis.skills.registry import ConfirmationRequired

    config = Config()
    registry, services = build_registry(config, lambda t: None)
    try:
        services.shutdown()
    except Exception:
        pass

    skill = registry._skills["close_app"]
    assert hasattr(skill.handler, '_original'), "close_app handler должен иметь _original"
    with pytest.raises(ConfirmationRequired):
        skill.handler(name="test_app")


def test_git_push_skill_has_confirmation():
    """Навык git_push обёрнут в _confirm_handler."""
    from jarvis.skills import build_registry
    from jarvis.config import Config
    from jarvis.skills.registry import ConfirmationRequired

    config = Config()
    registry, services = build_registry(config, lambda t: None)
    try:
        services.shutdown()
    except Exception:
        pass

    skill = registry._skills["git_push"]
    assert hasattr(skill.handler, '_original'), "git_push handler должен иметь _original"
    with pytest.raises(ConfirmationRequired):
        skill.handler(cwd=".")


def test_git_commit_skill_has_confirmation():
    """Навык git_commit обёрнут в _confirm_handler."""
    from jarvis.skills import build_registry
    from jarvis.config import Config
    from jarvis.skills.registry import ConfirmationRequired

    config = Config()
    registry, services = build_registry(config, lambda t: None)
    try:
        services.shutdown()
    except Exception:
        pass

    skill = registry._skills["git_commit"]
    assert hasattr(skill.handler, '_original'), "git_commit handler должен иметь _original"
    with pytest.raises(ConfirmationRequired):
        skill.handler(message="test commit")


def test_self_update_skill_has_confirmation():
    """Навык self_update обёрнут в _confirm_handler."""
    from jarvis.skills import build_registry
    from jarvis.config import Config
    from jarvis.skills.registry import ConfirmationRequired

    config = Config()
    registry, services = build_registry(config, lambda t: None)
    try:
        services.shutdown()
    except Exception:
        pass

    skill = registry._skills["self_update"]
    assert hasattr(skill.handler, '_original'), "self_update handler должен иметь _original"
    with pytest.raises(ConfirmationRequired):
        skill.handler()


def test_run_update_skill_has_confirmation():
    """Навык run_update обёрнут в _confirm_handler."""
    from jarvis.skills import build_registry
    from jarvis.config import Config
    from jarvis.skills.registry import ConfirmationRequired

    config = Config()
    registry, services = build_registry(config, lambda t: None)
    try:
        services.shutdown()
    except Exception:
        pass

    skill = registry._skills["run_update"]
    assert hasattr(skill.handler, '_original'), "run_update handler должен иметь _original"
    with pytest.raises(ConfirmationRequired):
        skill.handler()


def test_power_action_skill_has_confirmation():
    """Навык power_action обёрнут в _confirm_handler."""
    from jarvis.skills import build_registry
    from jarvis.config import Config
    from jarvis.skills.registry import ConfirmationRequired

    config = Config()
    registry, services = build_registry(config, lambda t: None)
    try:
        services.shutdown()
    except Exception:
        pass

    skill = registry._skills["power_action"]
    assert hasattr(skill.handler, '_original'), "power_action handler должен иметь _original"
    with pytest.raises(ConfirmationRequired):
        skill.handler(action="shutdown")


def test_safe_skills_do_not_require_confirmation():
    """Обычные навыки (list_files, git_status) работают без подтверждения."""
    from jarvis.skills import build_registry
    from jarvis.config import Config

    config = Config()
    registry, services = build_registry(config, lambda t: None)
    try:
        services.shutdown()
    except Exception:
        pass

    # git_status — безопасный, без подтверждения
    result = registry.call("git_status", {"cwd": "."})
    assert isinstance(result, str)

    # list_files — безопасный
    result = registry.call("list_files", {"directory": "/tmp", "pattern": ""})
    assert isinstance(result, str)
