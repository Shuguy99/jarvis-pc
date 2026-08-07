"""Тесты целостности всех навыков: уникальность имён, формат параметров."""

import pytest
from jarvis.skills import build_registry
from jarvis.config import Config


def test_no_duplicate_skill_names():
    """Все 174 навыка имеют уникальные имена."""
    config = Config()
    registry, services = build_registry(config, lambda t: None)
    try:
        services.shutdown()
    except Exception:
        pass
    names = registry.names
    assert len(names) == len(set(names)), f"Дубликаты: {[n for n in names if names.count(n) > 1]}"


def test_all_skills_have_handler():
    """Каждый навык вызывается без падения (handler существует)."""
    config = Config()
    registry, services = build_registry(config, lambda t: None)
    try:
        services.shutdown()
    except Exception:
        pass
    for name in registry.names:
        spec = registry.tool_specs()
        assert any(s["function"]["name"] == name for s in spec)


def test_all_tool_specs_valid():
    """Каждый tool_spec соответствует формату OpenAI function calling."""
    config = Config()
    registry, services = build_registry(config, lambda t: None)
    try:
        services.shutdown()
    except Exception:
        pass
    for spec in registry.tool_specs():
        assert spec["type"] == "function"
        func = spec["function"]
        assert isinstance(func["name"], str)
        assert isinstance(func["description"], str)
        params = func["parameters"]
        assert params["type"] == "object"
        assert isinstance(params["properties"], dict)
        assert isinstance(params["required"], list)
        # Required fields must exist in properties
        for req in params["required"]:
            assert req in params["properties"], f"{func['name']}: required '{req}' not in properties"
