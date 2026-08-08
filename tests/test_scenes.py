"""Тесты автоматизаций и сцен -- SceneRunner, CRUD, выполнение."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from jarvis.config import ScenesConfig
from jarvis.skills.registry import Skill, SkillRegistry, object_schema
from jarvis.skills.scenes import SceneRunner, BUILTIN_SCENES


cfg = ScenesConfig()


def _make_runner(custom_data=None, **cfg_overrides):
    """Создаёт SceneRunner с моковым файлом и инжектированным реестром."""
    c = ScenesConfig(**cfg_overrides)
    runner = SceneRunner(c)
    reg = SkillRegistry()
    reg.register(Skill(
        name="get_weather", description="", parameters=object_schema({}),
        handler=lambda: "Ясно, +20C",
    ))
    reg.register(Skill(
        name="set_volume", description="", parameters=object_schema({}),
        handler=lambda level=50: f"Громкость {level}%",
    ))
    reg.register(Skill(
        name="battery_status", description="", parameters=object_schema({}),
        handler=lambda: "Батарея 80%",
    ))
    reg.register(Skill(
        name="pomodoro_start", description="", parameters=object_schema({}),
        handler=lambda: "Помодоро запущен",
    ))
    reg.register(Skill(
        name="system_status", description="", parameters=object_schema({}),
        handler=lambda: "CPU 10%",
    ))
    reg.register(Skill(
        name="get_news", description="", parameters=object_schema({}),
        handler=lambda: "Новостей нет",
    ))
    reg.register(Skill(
        name="today_events", description="", parameters=object_schema({}),
        handler=lambda: "Ничего",
    ))
    reg.register(Skill(
        name="get_forecast", description="", parameters=object_schema({}),
        handler=lambda: "Завтра дождь",
    ))
    reg.register(Skill(
        name="expense_summary", description="", parameters=object_schema({}),
        handler=lambda period="day": "Потрачено 500 руб",
    ))
    reg.register(Skill(
        name="alarm_status", description="", parameters=object_schema({}),
        handler=lambda: "Будильник: 07:00",
    ))
    if custom_data:
        runner._custom = custom_data
    runner.set_registry(reg)
    return runner, reg


# -- Инициализация ----------------------------------------------------------


class TestInit:
    def test_loads_builtin(self):
        runner, _ = _make_runner()
        scene = runner.get_scene("morning")
        assert scene is not None
        assert len(scene.get("steps", [])) == 3

    def test_loads_custom_from_file(self, tmp_path):
        scenes_file = tmp_path / "scenes.json"
        scenes_file.write_text(json.dumps({
            "my_scene": {"description": "test", "steps": []}
        }), encoding="utf-8")
        runner = SceneRunner(ScenesConfig(scenes_file=str(scenes_file)))
        assert "my_scene" in runner._custom

    def test_ignores_invalid_file(self, tmp_path):
        scenes_file = tmp_path / "bad.json"
        scenes_file.write_text("not json", encoding="utf-8")
        runner = SceneRunner(ScenesConfig(scenes_file=str(scenes_file)))
        assert runner._custom == {}

    def test_ignores_invalid_entries(self, tmp_path):
        scenes_file = tmp_path / "scenes.json"
        scenes_file.write_text(json.dumps({
            "good": {"description": "ok", "steps": []},
            "bad": {"no_steps": True},
            "also_bad": "not a dict",
        }), encoding="utf-8")
        runner = SceneRunner(ScenesConfig(scenes_file=str(scenes_file)))
        assert "good" in runner._custom
        assert "bad" not in runner._custom


# -- Выполнение сцен --------------------------------------------------------


class TestRunScene:
    def test_morning(self):
        runner, _ = _make_runner()
        result = runner.run("morning")
        assert "morning" in result
        assert "+20C" in result

    def test_focus_with_args(self):
        runner, _ = _make_runner()
        result = runner.run("focus")
        assert "Громкость 30%" in result
        assert "Помодоро запущен" in result

    def test_night(self):
        runner, _ = _make_runner()
        result = runner.run("night")
        assert "10%" in result

    def test_unknown(self):
        runner, _ = _make_runner()
        result = runner.run("nonexistent")
        assert "не найдена" in result

    def test_no_registry(self):
        runner = SceneRunner(cfg)
        result = runner.run("morning")
        assert "не инициализирован" in result.lower()

    def test_delay_step(self):
        runner, _ = _make_runner()
        runner._custom["test_delay"] = {
            "description": "test",
            "steps": [{"delay": 0, "comment": "fast"}],
        }
        result = runner.run("test_delay")
        assert "fast" in result

    def test_skill_error_caught(self):
        reg = SkillRegistry()
        reg.register(Skill(
            name="failing_skill", description="", parameters=object_schema({}),
            handler=lambda: (_ for _ in ()).throw(RuntimeError("boom")),
        ))
        runner = SceneRunner(cfg)
        runner._custom["test_fail"] = {
            "description": "test",
            "steps": [{"skill": "failing_skill", "args": {}}],
        }
        runner.set_registry(reg)
        result = runner.run("test_fail")
        assert isinstance(result, str)

    def test_condition_true(self):
        runner, _ = _make_runner()
        runner._custom["cond_test"] = {
            "description": "test",
            "steps": [{
                "if_skill": "battery_status",
                "contains": "80",
                "then": [{"skill": "get_news", "args": {}}],
            }],
        }
        result = runner.run("cond_test")
        assert "выполнено" in result.lower()

    def test_condition_false(self):
        runner, _ = _make_runner()
        runner._custom["cond_false"] = {
            "description": "test",
            "steps": [{
                "if_skill": "battery_status",
                "contains": "низкий",
                "then": [{"skill": "get_news", "args": {}}],
            }],
        }
        result = runner.run("cond_false")
        assert "не выполнено" in result.lower()


# -- CRUD ---------------------------------------------------------------


class TestCreateScene:
    def test_success(self, tmp_path):
        runner, _ = _make_runner()
        runner._config = ScenesConfig(scenes_file=str(tmp_path / "scenes.json"))
        result = runner.create("my_test", "desc", [
            {"skill": "get_weather", "args": {}},
        ])
        assert "создана" in result.lower()
        assert "my_test" in runner._custom

    def test_empty_steps(self):
        runner, _ = _make_runner()
        result = runner.create("empty", "desc", [])
        assert "хотя бы один" in result.lower()

    def test_cannot_overwrite_builtin(self):
        runner, _ = _make_runner()
        result = runner.create("morning", "new desc", [{"skill": "x", "args": {}}])
        assert "встроенн" in result.lower()


class TestDeleteScene:
    def test_success(self, tmp_path):
        runner, _ = _make_runner(custom_data={"del_me": {"description": "x", "steps": []}})
        runner._config = ScenesConfig(scenes_file=str(tmp_path / "scenes.json"))
        result = runner.delete("del_me")
        assert "удалена" in result.lower()
        assert "del_me" not in runner._custom

    def test_cannot_delete_builtin(self):
        runner, _ = _make_runner()
        result = runner.delete("morning")
        assert "встроенн" in result.lower()

    def test_not_found(self):
        runner, _ = _make_runner()
        result = runner.delete("ghost")
        assert "не найдена" in result.lower()


class TestAddStep:
    def test_append(self):
        runner, _ = _make_runner(custom_data={
            "test": {"description": "t", "steps": [{"skill": "get_weather", "args": {}}]}
        })
        result = runner.add_step("test", {"skill": "get_news", "args": {}})
        assert "добавлен" in result.lower()
        assert len(runner._custom["test"]["steps"]) == 2

    def test_insert_position(self):
        runner, _ = _make_runner(custom_data={
            "test": {"description": "t", "steps": [
                {"skill": "get_weather", "args": {}},
                {"skill": "get_news", "args": {}},
            ]}
        })
        runner.add_step("test", {"skill": "battery_status", "args": {}}, position=1)
        assert runner._custom["test"]["steps"][1]["skill"] == "battery_status"

    def test_scene_not_found(self):
        runner, _ = _make_runner()
        result = runner.add_step("ghost", {"skill": "x", "args": {}})
        assert "не найдена" in result.lower()

    def test_builtin_copies_to_custom(self, tmp_path):
        runner, _ = _make_runner()
        runner._config = ScenesConfig(scenes_file=str(tmp_path / "scenes.json"))
        result = runner.add_step("morning", {"delay": 1})
        assert "добавлен" in result.lower()
        assert "morning" in runner._custom
        assert len(runner._custom["morning"]["steps"]) == 4


class TestRemoveStep:
    def test_success(self):
        runner, _ = _make_runner(custom_data={
            "test": {"description": "t", "steps": [
                {"skill": "get_weather", "args": {}},
                {"skill": "get_news", "args": {}},
            ]}
        })
        result = runner.remove_step("test", 1)
        assert "удалён" in result.lower()
        assert len(runner._custom["test"]["steps"]) == 1
        assert runner._custom["test"]["steps"][0]["skill"] == "get_news"

    def test_out_of_range(self):
        runner, _ = _make_runner(custom_data={
            "test": {"description": "t", "steps": [{"skill": "x", "args": {}}]}
        })
        result = runner.remove_step("test", 99)
        assert "вне диапазона" in result.lower()

    def test_scene_not_found(self):
        runner, _ = _make_runner()
        result = runner.remove_step("ghost", 1)
        assert "не найдена" in result.lower()


# -- Информация ------------------------------------------------------------


class TestListAll:
    def test_lists_builtin(self):
        runner, _ = _make_runner()
        result = runner.list_all()
        assert "morning" in result
        assert "work" in result
        assert "evening" in result
        assert "focus" in result

    def test_shows_custom(self):
        runner, _ = _make_runner(custom_data={
            "custom_one": {"description": "My scene", "steps": [{"skill": "x", "args": {}}]}
        })
        result = runner.list_all()
        assert "custom_one" in result
        assert "\u2605" in result

    def test_counts(self):
        data = {"a": {"description": "", "steps": []}}
        runner, _ = _make_runner(custom_data=data)
        result = runner.list_all()
        assert "6 встроенных" in result
        assert "1 пользовательск" in result


class TestInfo:
    def test_builtin(self):
        runner, _ = _make_runner()
        result = runner.info("morning")
        assert "встроенная" in result
        assert "get_weather" in result

    def test_custom(self):
        runner, _ = _make_runner(custom_data={
            "my": {"description": "Test", "steps": [{"skill": "x", "args": {}}]}
        })
        result = runner.info("my")
        assert "пользовательская" in result

    def test_not_found(self):
        runner, _ = _make_runner()
        result = runner.info("ghost")
        assert "не найдена" in result.lower()

    def test_shows_delay(self):
        runner, _ = _make_runner(custom_data={
            "d": {"description": "", "steps": [{"delay": 5, "comment": "пауза"}]}
        })
        result = runner.info("d")
        assert "задержка" in result.lower()
        assert "пауза" in result

    def test_shows_condition(self):
        runner, _ = _make_runner(custom_data={
            "c": {"description": "", "steps": [{
                "if_skill": "battery_status", "contains": "низкий", "then": []
            }]}
        })
        result = runner.info("c")
        assert "если" in result.lower()


# -- build_skills --------------------------------------------------------


class TestBuildSkills:
    def test_count(self):
        runner, _ = _make_runner()
        skills = runner.build_skills()
        assert len(skills) == 7

    def test_names(self):
        runner, _ = _make_runner()
        names = {s.name for s in runner.build_skills()}
        expected = {
            "run_scene", "list_scenes", "scene_info",
            "create_scene", "delete_scene", "add_scene_step", "remove_scene_step",
        }
        assert names == expected

    def test_all_have_descriptions(self):
        runner, _ = _make_runner()
        for s in runner.build_skills():
            assert len(s.description) > 10

    def test_run_scene_handler(self):
        runner, _ = _make_runner()
        skills = runner.build_skills()
        run = next(s for s in skills if s.name == "run_scene")
        result = run.handler(name="focus")
        assert "Громкость 30%" in result

    def test_create_scene_handler(self, tmp_path):
        runner, _ = _make_runner()
        runner._config = ScenesConfig(scenes_file=str(tmp_path / "scenes.json"))
        skills = runner.build_skills()
        create = next(s for s in skills if s.name == "create_scene")
        result = create.handler(name="test", steps=[{"skill": "get_weather", "args": {}}])
        assert "создана" in result.lower()

    def test_delete_scene_handler(self):
        runner, _ = _make_runner(custom_data={"del": {"description": "", "steps": []}})
        skills = runner.build_skills()
        delete = next(s for s in skills if s.name == "delete_scene")
        result = delete.handler(name="del")
        assert "удалена" in result.lower()
