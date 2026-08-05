"""Тесты правил офлайн-мозга и реестра навыков."""

from __future__ import annotations

import pytest

from jarvis.brain.offline_brain import OfflineBrain, match_rule
from jarvis.config import BrainConfig
from jarvis.skills.registry import Skill, SkillRegistry, object_schema


@pytest.mark.parametrize(
    ("phrase", "skill"),
    [
        ("Джарвис, который час", "current_time"),
        ("какое сегодня число", "current_date"),
        ("открой блокнот", "open_app"),
        ("закрой chrome", "close_app"),
        ("найди рецепт борща", "web_search"),
        ("погода в Москве", "weather"),
        ("сделай громче", "change_volume"),
        ("поставь громкость на 30", "set_volume"),
        ("сделай скриншот", "take_screenshot"),
        ("поставь таймер на 5 минут чай", "set_timer"),
        ("запиши заметку: купить репульсоры", "add_note"),
        ("статус системы", "system_status"),
        ("что такое палладий", "fetch_summary"),
    ],
)
def test_rules_match_expected_skill(phrase: str, skill: str) -> None:
    """Каждая фраза попадает в ожидаемый навык."""
    matched = match_rule(phrase)
    assert matched is not None
    assert matched[0] == skill


def test_volume_level_extracted() -> None:
    """Из фразы извлекается числовой уровень громкости."""
    matched = match_rule("поставь громкость на 42")
    assert matched == ("set_volume", {"level": 42})


def test_timer_minutes_converted_to_seconds() -> None:
    """Минуты в таймере переводятся в секунды."""
    matched = match_rule("таймер на 3 минуты кофе")
    assert matched is not None
    assert matched[1]["seconds"] == pytest.approx(180.0)
    assert matched[1]["label"] == "кофе"


def test_unknown_phrase_returns_none() -> None:
    """Незнакомая фраза не сопоставляется ни с одним правилом."""
    assert match_rule("расскажи о своих чувствах к Пеппер") is None


def _registry() -> SkillRegistry:
    """Реестр с одним тестовым навыком."""
    registry = SkillRegistry()
    registry.register(
        Skill(
            name="open_app",
            description="Открыть приложение",
            parameters=object_schema({"name": {"type": "string"}}, ["name"]),
            handler=lambda name: f"Запускаю {name}",
        )
    )
    return registry


def test_offline_brain_executes_matched_skill() -> None:
    """Офлайн-мозг вызывает найденный навык."""
    brain = OfflineBrain(BrainConfig(backend="offline"), _registry())
    assert brain.ask("открой блокнот") == "Запускаю блокнот"


def test_offline_brain_reports_unknown_command() -> None:
    """На непонятную фразу мозг честно сообщает об ограничении."""
    reply = OfflineBrain(BrainConfig(backend="offline"), _registry()).ask("спой песню")
    assert "прямые команды" in reply
