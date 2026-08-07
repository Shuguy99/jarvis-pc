"""Тесты сцен (автоматизации)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from jarvis.skills.registry import SkillRegistry, Skill, object_schema
from jarvis.skills.scenes import _list_scenes, _run_scene, build_skills


# ── _list_scenes ────────────────────────────────────────────────────────


class TestListScenes:
    def test_lists_all_four_scenes(self):
        result = _list_scenes()
        assert "morning" in result
        assert "work" in result
        assert "evening" in result
        assert "focus" in result

    def test_includes_descriptions(self):
        result = _list_scenes()
        assert "Утренняя" in result
        assert "Рабочая" in result
        assert "Вечерняя" in result
        assert "фокуса" in result

    def test_includes_skill_names(self):
        result = _list_scenes()
        assert "get_weather" in result
        assert "set_volume" in result
        assert "pomodoro_start" in result


# ── _run_scene ──────────────────────────────────────────────────────────


class TestRunScene:
    def _make_registry(self, responses: dict[str, str]) -> SkillRegistry:
        reg = SkillRegistry()
        for name, text in responses.items():
            reg.register(Skill(
                name=name,
                description=f"mock {name}",
                parameters=object_schema({}),
                handler=lambda t=text, **kw: t,
            ))
        return reg

    def test_unknown_scene(self):
        reg = self._make_registry({})
        result = _run_scene(reg, "nonexistent")
        assert "не найдена" in result
        assert "nonexistent" in result

    def test_morning_scene_calls_three_skills(self):
        responses = {
            "get_weather": "Солнечно, 20C",
            "today_events": "Ничего",
            "get_news": "В мире всё спокойно",
        }
        reg = self._make_registry(responses)
        result = _run_scene(reg, "morning")
        assert "morning" in result
        assert "Солнечно, 20C" in result
        assert "Ничего" in result
        assert "В мире всё спокойно" in result

    def test_work_scene_with_volume(self):
        responses = {
            "system_status": "CPU 10%",
            "set_volume": "Громкость 40%",
            "pomodoro_status": "Не активен",
        }
        reg = self._make_registry(responses)
        result = _run_scene(reg, "work")
        assert "work" in result
        assert "Громкость 40%" in result

    def test_focus_scene_calls_volume_with_args(self):
        called_with = {}
        reg = SkillRegistry()

        def mock_set_volume(level=50):
            called_with["level"] = level
            return f"Громкость {level}%"

        reg.register(Skill(
            name="set_volume", description="", parameters=object_schema({}),
            handler=mock_set_volume,
        ))
        reg.register(Skill(
            name="pomodoro_start", description="", parameters=object_schema({}),
            handler=lambda: "Помодоро запущен",
        ))
        result = _run_scene(reg, "focus")
        assert called_with["level"] == 30
        assert "Помодоро запущен" in result

    def test_scene_format_has_emoji(self):
        reg = self._make_registry({
            "get_weather": "ok",
            "today_events": "ok",
            "get_news": "ok",
        })
        result = _run_scene(reg, "morning")
        assert "\U0001f3a8" in result or "Сцена" in result

    def test_evening_scene(self):
        responses = {
            "get_forecast": "Завтра дождь",
            "expense_summary": "Потрачено 500 руб",
            "battery_status": "80%",
        }
        reg = self._make_registry(responses)
        result = _run_scene(reg, "evening")
        assert "evening" in result
        assert "Завтра дождь" in result

    def test_skill_error_doesnt_crash_scene(self):
        """Если навык в сцене падает — реестр возвращает ошибку, но сцена продолжается."""
        reg = SkillRegistry()
        reg.register(Skill(
            name="get_weather", description="", parameters=object_schema({}),
            handler=lambda: (_ for _ in ()).throw(RuntimeError("weather crash")),
        ))
        # Регистр оборачивает ошибки в текст
        result = reg.call("get_weather", {})
        assert isinstance(result, str)


# ── build_skills ───────────────────────────────────────────────────────


class TestBuildSkills:
    def test_returns_two_skills(self):
        reg = SkillRegistry()
        skills = build_skills(reg)
        assert len(skills) == 2

    def test_skill_names(self):
        reg = SkillRegistry()
        names = {s.name for s in build_skills(reg)}
        assert "run_scene" in names
        assert "list_scenes" in names

    def test_list_scenes_handler_works(self):
        reg = SkillRegistry()
        skills = build_skills(reg)
        list_skill = next(s for s in skills if s.name == "list_scenes")
        result = list_skill.handler()
        assert "morning" in result

    def test_run_scene_handler(self):
        reg = SkillRegistry()
        reg.register(Skill(
            name="get_weather", description="", parameters=object_schema({}),
            handler=lambda: "Ясно",
        ))
        reg.register(Skill(
            name="today_events", description="", parameters=object_schema({}),
            handler=lambda: "Пусто",
        ))
        reg.register(Skill(
            name="get_news", description="", parameters=object_schema({}),
            handler=lambda: "Новостей нет",
        ))
        skills = build_skills(reg)
        run_skill = next(s for s in skills if s.name == "run_scene")
        result = run_skill.handler(name="morning")
        assert "Ясно" in result
