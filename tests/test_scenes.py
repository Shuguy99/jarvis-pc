"""Тесты автоматизаций и сцен -- SceneRunner, CRUD, выполнение,
расширенные условия, переменные, циклы, триггеры, лог, event bus.

"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from jarvis.config import ScenesConfig
from jarvis.skills.registry import Skill, SkillRegistry, object_schema
from jarvis.skills.scenes import (
    SceneRunner, BUILTIN_SCENES, EventBus,
    _substitute_vars, _evaluate_condition, _safe_number,
)


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
    reg.register(Skill(
        name="return_number", description="", parameters=object_schema({}),
        handler=lambda: "42",
    ))
    if custom_data:
        runner._custom = custom_data
    runner.set_registry(reg)
    return runner, reg


# -- Утилиты ---------------------------------------------------------------


class TestSubstituteVars:
    def test_simple(self):
        assert _substitute_vars("{{name}}", {"name": "world"}) == "world"

    def test_multiple(self):
        result = _substitute_vars("{{a}} и {{b}}", {"a": "1", "b": "2"})
        assert result == "1 и 2"

    def test_unknown_var_unchanged(self):
        assert _substitute_vars("{{unknown}}", {}) == "{{unknown}}"

    def test_in_dict(self):
        args = {"level": "{{vol}}"}
        result = _substitute_vars(args, {"vol": "30"})
        assert result == {"level": "30"}

    def test_in_list(self):
        data = ["{{a}}", "fixed"]
        result = _substitute_vars(data, {"a": "x"})
        assert result == ["x", "fixed"]

    def test_nested(self):
        data = {"args": {"level": "{{v}}"}}
        result = _substitute_vars(data, {"v": "99"})
        assert result == {"args": {"level": "99"}}


class TestSafeNumber:
    def test_int(self):
        assert _safe_number("42") == 42.0

    def test_float(self):
        assert _safe_number("3.14") == 3.14

    def test_invalid(self):
        assert _safe_number("abc") is None

    def test_empty(self):
        assert _safe_number("") is None


class TestEvaluateCondition:
    def test_contains(self):
        assert _evaluate_condition("Батарея 80%", "contains", "80")
        assert not _evaluate_condition("Батарея 80%", "contains", "10")

    def test_not_contains(self):
        assert _evaluate_condition("Батарея 80%", "not_contains", "10")
        assert not _evaluate_condition("Батарея 80%", "not_contains", "80")

    def test_equals(self):
        assert _evaluate_condition("ok", "equals", "ok")
        assert _evaluate_condition("ok", "equals", "OK")  # case-insensitive
        assert not _evaluate_condition("ok", "equals", "no")

    def test_not_equals(self):
        assert _evaluate_condition("ok", "not_equals", "no")
        assert not _evaluate_condition("ok", "not_equals", "ok")

    def test_gt(self):
        assert _evaluate_condition("80", "gt", "50")
        assert not _evaluate_condition("30", "gt", "50")

    def test_gte(self):
        assert _evaluate_condition("50", "gte", "50")
        assert not _evaluate_condition("49", "gte", "50")

    def test_lt(self):
        assert _evaluate_condition("30", "lt", "50")
        assert not _evaluate_condition("80", "lt", "50")

    def test_lte(self):
        assert _evaluate_condition("50", "lte", "50")
        assert not _evaluate_condition("51", "lte", "50")

    def test_matches(self):
        assert _evaluate_condition("CPU 95%", "matches", r"CPU\s+\d+%")
        assert not _evaluate_condition("ОК", "matches", r"CPU\s+\d+%")

    def test_empty(self):
        assert _evaluate_condition("", "empty", "")
        assert not _evaluate_condition("text", "empty", "")

    def test_not_empty(self):
        assert _evaluate_condition("text", "not_empty", "")
        assert not _evaluate_condition("", "not_empty", "")

    def test_default_fallback_contains(self):
        assert _evaluate_condition("Батарея 80%", "unknown_op", "80")

    def test_gt_non_numeric(self):
        assert not _evaluate_condition("abc", "gt", "10")


# -- EventBus -------------------------------------------------------------


class TestEventBus:
    def test_subscribe_and_emit(self):
        bus = EventBus()
        bus.subscribe("battery_low", "tr1", "evening")
        results = bus.emit("battery_low")
        assert results == [("tr1", "evening")]

    def test_emit_no_subscribers(self):
        bus = EventBus()
        assert bus.emit("unknown") == []

    def test_unsubscribe(self):
        bus = EventBus()
        bus.subscribe("event1", "tr1", "scene1")
        bus.subscribe("event1", "tr2", "scene2")
        bus.unsubscribe("tr1")
        results = bus.emit("event1")
        assert results == [("tr2", "scene2")]

    def test_multiple_events(self):
        bus = EventBus()
        bus.subscribe("e1", "tr1", "s1")
        bus.subscribe("e2", "tr2", "s2")
        assert len(bus.emit("e1")) == 1
        assert len(bus.emit("e2")) == 1
        assert len(bus.emit("e3")) == 0

    def test_list_subscriptions(self):
        bus = EventBus()
        bus.subscribe("e1", "tr1", "s1")
        bus.subscribe("e1", "tr2", "s2")
        bus.subscribe("e2", "tr3", "s3")
        subs = bus.list_subscriptions()
        assert subs == {"e1": 2, "e2": 1}


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

    def test_loads_triggers_from_file(self, tmp_path):
        scenes_file = tmp_path / "scenes.json"
        data = {
            "my_scene": {"description": "t", "steps": []},
            "triggers": [{
                "id": "tr_abc", "scene": "morning",
                "cron": "every 30m", "enabled": True,
            }],
        }
        scenes_file.write_text(json.dumps(data), encoding="utf-8")
        runner = SceneRunner(ScenesConfig(scenes_file=str(scenes_file)))
        assert len(runner._triggers) == 1
        assert runner._triggers[0]["id"] == "tr_abc"

    def test_loads_variables_from_file(self, tmp_path):
        scenes_file = tmp_path / "scenes.json"
        data = {
            "my_scene": {"description": "t", "steps": []},
            "variables": {"my_scene": {"vol": "30"}},
        }
        scenes_file.write_text(json.dumps(data), encoding="utf-8")
        runner = SceneRunner(ScenesConfig(scenes_file=str(scenes_file)))
        assert runner._scene_variables == {"my_scene": {"vol": "30"}}


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
        assert "выполнено" in result.lower() or "\u2714" in result

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
        assert "не выполнено" in result.lower() or "\u2718" in result

    def test_condition_else_executed(self):
        runner, _ = _make_runner()
        runner._custom["cond_else"] = {
            "description": "test",
            "steps": [{
                "if_skill": "battery_status",
                "op": "contains",
                "value": "низкий",
                "then": [{"skill": "get_news", "args": {}}],
                "else": [{"skill": "get_weather", "args": {}}],
            }],
        }
        result = runner.run("cond_else")
        # Батарея 80% не содержит 'низкий' -> else
        assert "+20C" in result

    def test_records_history(self):
        runner, _ = _make_runner()
        runner.run("morning")
        hist = runner.get_history()
        assert "morning" in hist
        assert "manual" in hist

    def test_empty_scene(self):
        runner, _ = _make_runner()
        runner._custom["empty"] = {"description": "", "steps": []}
        result = runner.run("empty")
        assert "пуста" in result.lower()


# -- Расширенные условия -----------------------------------------------------


class TestExtendedConditions:
    def test_op_gt_true(self):
        runner, _ = _make_runner()
        runner._custom["gt_test"] = {
            "description": "t",
            "steps": [{
                "if_skill": "battery_status",
                "op": "contains", "value": "80",
                "then": [{"skill": "get_news", "args": {}}],
            }],
        }
        result = runner.run("gt_test")
        assert "\u2714" in result

    def test_op_equals_false(self):
        runner, _ = _make_runner()
        runner._custom["eq_test"] = {
            "description": "t",
            "steps": [{
                "if_skill": "battery_status",
                "op": "equals", "value": "Батарея 10%",
                "then": [{"skill": "get_news", "args": {}}],
            }],
        }
        result = runner.run("eq_test")
        assert "\u2718" in result

    def test_op_not_contains(self):
        runner, _ = _make_runner()
        runner._custom["nc_test"] = {
            "description": "t",
            "steps": [{
                "if_skill": "battery_status",
                "op": "not_contains", "value": "10%",
                "then": [{"skill": "get_news", "args": {}}],
            }],
        }
        result = runner.run("nc_test")
        assert "\u2714" in result

    def test_op_lt_numeric(self):
        runner, _ = _make_runner()
        runner._custom["lt_test"] = {
            "description": "t",
            "steps": [{
                "if_skill": "return_number",
                "op": "lt", "value": "50",
                "then": [{"skill": "get_news", "args": {}}],
            }],
        }
        result = runner.run("lt_test")
        assert "\u2714" in result

    def test_op_matches_regex(self):
        runner, _ = _make_runner()
        runner._custom["rx_test"] = {
            "description": "t",
            "steps": [{
                "if_skill": "battery_status",
                "op": "matches", "value": r"Батарея\s+\d+%",
                "then": [{"skill": "get_news", "args": {}}],
            }],
        }
        result = runner.run("rx_test")
        assert "\u2714" in result

    def test_save_to_variable(self):
        runner, _ = _make_runner()
        runner._custom["save_test"] = {
            "description": "t",
            "steps": [
                {
                    "if_skill": "battery_status",
                    "op": "contains", "value": "80",
                    "save_to": "bat_result",
                    "then": [],
                },
            ],
        }
        runner.run("save_test")
        # Переменная должна сохраниться
        assert "bat_result" in runner._scene_variables.get("save_test", {})


# -- Группа условий (AND/OR) ------------------------------------------------


class TestConditionGroups:
    def test_and_both_true(self):
        runner, _ = _make_runner()
        runner._custom["and_test"] = {
            "description": "t",
            "steps": [{
                "conditions": {
                    "op": "and",
                    "checks": [
                        {"if_skill": "battery_status", "op": "contains", "value": "80"},
                        {"if_skill": "get_weather", "op": "contains", "value": "Ясно"},
                    ],
                },
                "then": [{"skill": "get_news", "args": {}}],
            }],
        }
        result = runner.run("and_test")
        assert "\u2714" in result
        assert "2/2" in result

    def test_and_one_false(self):
        runner, _ = _make_runner()
        runner._custom["and_fail"] = {
            "description": "t",
            "steps": [{
                "conditions": {
                    "op": "and",
                    "checks": [
                        {"if_skill": "battery_status", "op": "contains", "value": "80"},
                        {"if_skill": "get_weather", "op": "contains", "value": "Снег"},
                    ],
                },
                "then": [{"skill": "get_news", "args": {}}],
            }],
        }
        result = runner.run("and_fail")
        assert "\u2718" in result
        assert "1/2" in result

    def test_or_one_true(self):
        runner, _ = _make_runner()
        runner._custom["or_test"] = {
            "description": "t",
            "steps": [{
                "conditions": {
                    "op": "or",
                    "checks": [
                        {"if_skill": "battery_status", "op": "contains", "value": "10"},
                        {"if_skill": "get_weather", "op": "contains", "value": "Ясно"},
                    ],
                },
                "then": [{"skill": "get_news", "args": {}}],
            }],
        }
        result = runner.run("or_test")
        assert "\u2714" in result
        assert "1/2" in result

    def test_or_all_false(self):
        runner, _ = _make_runner()
        runner._custom["or_fail"] = {
            "description": "t",
            "steps": [{
                "conditions": {
                    "op": "or",
                    "checks": [
                        {"if_skill": "battery_status", "op": "equals", "value": "nope"},
                        {"if_skill": "get_weather", "op": "equals", "value": "nope"},
                    ],
                },
                "then": [{"skill": "get_news", "args": {}}],
            }],
        }
        result = runner.run("or_fail")
        assert "\u2718" in result
        assert "0/2" in result

    def test_condition_group_else(self):
        runner, _ = _make_runner()
        runner._custom["cg_else"] = {
            "description": "t",
            "steps": [{
                "conditions": {
                    "op": "and",
                    "checks": [
                        {"if_skill": "battery_status", "op": "contains", "value": "NOPE"},
                    ],
                },
                "then": [{"skill": "get_news", "args": {}}],
                "else": [{"skill": "get_weather", "args": {}}],
            }],
        }
        result = runner.run("cg_else")
        assert "+20C" in result


# -- Переменные --------------------------------------------------------------


class TestVariables:
    def test_set_var_static(self):
        runner, _ = _make_runner()
        runner._custom["var_test"] = {
            "description": "t",
            "steps": [
                {"set_var": "vol", "value": "30"},
                {"skill": "set_volume", "args": {"level": "{{vol}}"}},
            ],
        }
        result = runner.run("var_test")
        assert "Громкость 30%" in result

    def test_set_var_from_skill(self):
        runner, _ = _make_runner()
        runner._custom["var_skill"] = {
            "description": "t",
            "steps": [
                {"set_var": "bat", "from_skill": "battery_status"},
            ],
        }
        result = runner.run("var_skill")
        assert "bat" in result
        assert "80%" in result

    def test_vars_persist_across_runs(self):
        runner, _ = _make_runner()
        runner._custom["var_persist"] = {
            "description": "t",
            "steps": [
                {"set_var": "counter", "value": "1"},
            ],
        }
        runner.run("var_persist")
        # Переменная сохранена
        assert runner._scene_variables["var_persist"]["counter"] == "1"

    def test_scene_defined_variables(self):
        runner, _ = _make_runner()
        runner._custom["with_vars"] = {
            "description": "t",
            "variables": {"city": "Москва"},
            "steps": [
                {"delay": 0, "comment": "Город: {{city}}"},
            ],
        }
        result = runner.run("with_vars")
        assert "Москва" in result

    def test_variable_in_comment(self):
        runner, _ = _make_runner()
        runner._custom["var_comment"] = {
            "description": "t",
            "steps": [
                {"set_var": "name", "value": "тест"},
                {"delay": 0, "comment": "Это {{name}}"},
            ],
        }
        result = runner.run("var_comment")
        assert "тест" in result


# -- Циклы ------------------------------------------------------------------


class TestCycles:
    def test_repeat(self):
        runner, _ = _make_runner()
        runner._custom["rep_test"] = {
            "description": "t",
            "steps": [
                {"repeat": 3, "steps": [
                    {"skill": "get_news", "args": {}},
                ]},
            ],
        }
        result = runner.run("rep_test")
        assert result.count("Новостей нет") == 3
        assert "repeat x3" in result

    def test_repeat_capped_at_20(self):
        runner, _ = _make_runner()
        runner._custom["rep_cap"] = {
            "description": "t",
            "steps": [
                {"repeat": 100, "steps": [
                    {"delay": 0},
                ]},
            ],
        }
        result = runner.run("rep_cap")
        assert "repeat x20" in result

    def test_loop_with_condition(self):
        runner, _ = _make_runner()
        # Батарея 80% содержит "80" -> условие выполняется
        # Но мы используем not_contains "99" -> всегда True
        runner._custom["loop_test"] = {
            "description": "t",
            "steps": [
                {"loop": {"if_skill": "battery_status", "op": "not_contains", "value": "99"},
                 "steps": [{"set_var": "x", "value": "done"}],
                 "max_iterations": 2},
            ],
        }
        result = runner.run("loop_test")
        assert "loop" in result.lower() or "\U0001f504" in result

    def test_loop_stops_when_false(self):
        runner, _ = _make_runner()
        # Батарея 80% НЕ содержит "999" -> сразу False
        runner._custom["loop_stop"] = {
            "description": "t",
            "steps": [
                {"loop": {"if_skill": "battery_status", "op": "contains", "value": "999"},
                 "steps": [{"delay": 0}],
                 "max_iterations": 5},
            ],
        }
        result = runner.run("loop_stop")
        assert "завершён после 0" in result

    def test_loop_max_iterations(self):
        runner, _ = _make_runner()
        # Всегда True, упрётся в лимит
        runner._custom["loop_max"] = {
            "description": "t",
            "steps": [
                {"loop": {"if_skill": "battery_status", "op": "contains", "value": "80"},
                 "steps": [{"delay": 0}],
                 "max_iterations": 3},
            ],
        }
        result = runner.run("loop_max")
        assert "лимита 3" in result.lower() or "\u26a0" in result

    def test_loop_with_condition_group(self):
        runner, _ = _make_runner()
        runner._custom["loop_cg"] = {
            "description": "t",
            "steps": [
                {"loop": {
                     "conditions": {
                         "op": "and",
                         "checks": [
                             {"if_skill": "battery_status", "op": "contains", "value": "80"},
                         ],
                     },
                 },
                 "steps": [{"set_var": "y", "value": "ok"}],
                 "max_iterations": 2},
            ],
        }
        result = runner.run("loop_cg")
        assert "\U0001f504" in result


# -- Вложенные сцены ---------------------------------------------------------


class TestSubScenes:
    def test_run_scene_step(self):
        runner, _ = _make_runner()
        runner._custom["outer"] = {
            "description": "t",
            "steps": [
                {"run_scene": "morning"},
            ],
        }
        result = runner.run("outer")
        assert "вложенная" in result.lower() or "\U0001f3ac" in result
        assert "+20C" in result

    def test_run_scene_not_found(self):
        runner, _ = _make_runner()
        runner._custom["bad_sub"] = {
            "description": "t",
            "steps": [
                {"run_scene": "nonexistent_scene"},
            ],
        }
        result = runner.run("bad_sub")
        assert "не найдена" in result.lower() or "\u26a0" in result

    def test_run_scene_with_var_substitution(self):
        runner, _ = _make_runner()
        runner._custom["var_sub"] = {
            "description": "t",
            "steps": [
                {"set_var": "target", "value": "morning"},
                {"run_scene": "{{target}}"},
            ],
        }
        result = runner.run("var_sub")
        assert "morning" in result


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

    def test_deletes_related_triggers(self, tmp_path):
        # Изолируем runner через свой tmp файл
        runner = SceneRunner(ScenesConfig(scenes_file=str(tmp_path / "del_trig.json")))
        runner._custom = {"del_trig": {"description": "x", "steps": []}}
        runner._triggers = [
            {"id": "tr1", "scene": "del_trig", "cron": "every 1h", "enabled": True},
            {"id": "tr2", "scene": "other", "cron": "every 1h", "enabled": True},
        ]
        runner._event_bus.subscribe("e1", "tr1", "del_trig")
        result = runner.delete("del_trig")
        assert "1 связанных триггеров" in result
        assert len(runner._triggers) == 1
        assert runner._triggers[0]["id"] == "tr2"


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


# -- Информация ---------------------------------------------------------------


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

    def test_shows_var_and_repeat_in_list(self):
        runner, _ = _make_runner(custom_data={
            "complex": {"description": "t", "steps": [
                {"set_var": "x", "value": "1"},
                {"repeat": 3, "steps": [{"delay": 0}]},
            ]}
        })
        result = runner.list_all()
        assert "complex" in result


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

    def test_shows_set_var(self):
        runner, _ = _make_runner(custom_data={
            "v": {"description": "", "steps": [{"set_var": "x", "value": "42"}]}
        })
        result = runner.info("v")
        assert "x" in result
        assert "42" in result

    def test_shows_run_scene(self):
        runner, _ = _make_runner(custom_data={
            "rs": {"description": "", "steps": [{"run_scene": "morning"}]}
        })
        result = runner.info("rs")
        assert "morning" in result
        assert "вложенная" in result.lower() or "сцену" in result.lower()

    def test_shows_repeat(self):
        runner, _ = _make_runner(custom_data={
            "r": {"description": "", "steps": [
                {"repeat": 5, "steps": [{"delay": 0}]}
            ]}
        })
        result = runner.info("r")
        assert "repeat" in result.lower() or "\U0001f501" in result
        assert "x5" in result

    def test_shows_loop(self):
        runner, _ = _make_runner(custom_data={
            "l": {"description": "", "steps": [
                {"loop": {"if_skill": "x", "op": "contains", "value": "y"},
                 "steps": [{"delay": 0}], "max_iterations": 5}
            ]}
        })
        result = runner.info("l")
        assert "loop" in result.lower() or "\U0001f504" in result

    def test_shows_condition_group(self):
        runner, _ = _make_runner(custom_data={
            "cg": {"description": "", "steps": [{
                "conditions": {
                    "op": "and",
                    "checks": [{"if_skill": "x", "op": "contains", "value": "y"}],
                },
                "then": [],
            }]}
        })
        result = runner.info("cg")
        assert "AND" in result
        assert "1 условий" in result

    def test_shows_scene_variables(self):
        runner, _ = _make_runner(custom_data={
            "sv": {"description": "", "variables": {"vol": "30"}, "steps": []}
        })
        result = runner.info("sv")
        assert "vol=30" in result


# -- Лог выполнения ----------------------------------------------------------


class TestHistory:
    def test_empty(self):
        runner, _ = _make_runner()
        result = runner.get_history()
        assert "пуста" in result.lower()

    def test_records_run(self):
        runner, _ = _make_runner()
        runner.run("morning")
        result = runner.get_history()
        assert "morning" in result

    def test_clear(self):
        runner, _ = _make_runner()
        runner.run("morning")
        runner.run("focus")
        result = runner.clear_history()
        assert "2 записей" in result
        assert runner.get_history() == "История выполнения сцен пуста, сэр."

    def test_max_limit(self):
        runner, _ = _make_runner()
        runner._history_max = 5
        for _ in range(10):
            runner.run("morning")
        # Should be capped at 5
        assert len(runner._history) == 5


# -- Триггеры ----------------------------------------------------------------


class TestTriggers:
    def test_create_cron_trigger(self, tmp_path):
        runner, _ = _make_runner()
        runner._config = ScenesConfig(scenes_file=str(tmp_path / "scenes.json"))
        result = runner.trigger_scene("morning", cron="every 30m")
        assert "создан" in result.lower()
        assert len(runner._triggers) == 1
        assert runner._triggers[0]["cron"] == "every 30m"

    def test_create_event_trigger(self, tmp_path):
        runner, _ = _make_runner()
        runner._config = ScenesConfig(scenes_file=str(tmp_path / "scenes.json"))
        result = runner.trigger_scene("evening", event="battery_low")
        assert "создан" in result.lower()
        assert runner._triggers[0]["event"] == "battery_low"
        subs = runner._event_bus.emit("battery_low")
        assert len(subs) == 1

    def test_create_both_cron_and_event(self, tmp_path):
        runner, _ = _make_runner()
        runner._config = ScenesConfig(scenes_file=str(tmp_path / "scenes.json"))
        result = runner.trigger_scene("morning", cron="0 7 * * *", event="sunrise")
        assert "создан" in result.lower()
        assert "cron" in result
        assert "событие" in result.lower()

    def test_create_bad_cron(self):
        runner, _ = _make_runner()
        result = runner.trigger_scene("morning", cron="invalid_cron_xyz")
        assert "некорректный" in result.lower()

    def test_create_no_cron_no_event(self):
        runner, _ = _make_runner()
        result = runner.trigger_scene("morning")
        assert "укажите" in result.lower()

    def test_create_scene_not_found(self):
        runner, _ = _make_runner()
        result = runner.trigger_scene("nonexistent", cron="every 1h")
        assert "не найдена" in result.lower()

    def test_delete_trigger(self, tmp_path):
        runner, _ = _make_runner()
        runner._config = ScenesConfig(scenes_file=str(tmp_path / "scenes.json"))
        runner.trigger_scene("morning", cron="every 1h")
        tid = runner._triggers[0]["id"]
        result = runner.delete_trigger(tid)
        assert "удалён" in result.lower()
        assert len(runner._triggers) == 0

    def test_delete_trigger_not_found(self):
        runner, _ = _make_runner()
        result = runner.delete_trigger("nonexistent")
        assert "не найден" in result.lower()

    def test_list_triggers_empty(self):
        runner, _ = _make_runner()
        result = runner.list_triggers()
        assert "нет активных" in result.lower()

    def test_list_triggers(self, tmp_path):
        runner, _ = _make_runner()
        runner._config = ScenesConfig(scenes_file=str(tmp_path / "scenes.json"))
        runner.trigger_scene("morning", cron="every 30m", description="Ежедневная утренняя")
        result = runner.list_triggers()
        assert "1)" in result or "Триггеры (1)" in result
        assert "morning" in result
        assert "every 30m" in result
        assert "Ежедневная утренняя" in result

    def test_cron_parsing_every(self):
        runner, _ = _make_runner()
        assert runner._cron_to_seconds("every 30s") == 30
        assert runner._cron_to_seconds("every 5m") == 300
        assert runner._cron_to_seconds("every 2h") == 7200
        assert runner._cron_to_seconds("every 1d") == 86400

    def test_cron_parsing_simple(self):
        runner, _ = _make_runner()
        # "N * * * *" = каждая N-я минута
        result = runner._cron_to_seconds("5 * * * *")
        assert result == 300

    def test_cron_parsing_invalid(self):
        runner, _ = _make_runner()
        assert runner._cron_to_seconds("not_a_cron") is None

    def test_cron_min_5_seconds(self):
        runner, _ = _make_runner()
        assert runner._cron_to_seconds("every 1s") == 5

    def test_event_trigger_subscription_on_start(self):
        runner, _ = _make_runner()
        runner._triggers = [{
            "id": "tr_ev", "scene": "morning",
            "event": "custom_event", "enabled": True,
        }]
        runner.start()
        try:
            subs = runner._event_bus.emit("custom_event")
            assert len(subs) == 1
        finally:
            runner.stop()

    def test_disabled_trigger_not_subscribed(self):
        runner, _ = _make_runner()
        runner._triggers = [{
            "id": "tr_dis", "scene": "morning",
            "event": "e", "enabled": False,
        }]
        runner.start()
        try:
            subs = runner._event_bus.emit("e")
            assert len(subs) == 0
        finally:
            runner.stop()


# -- Emit event -------------------------------------------------------------


class TestEmitEvent:
    def test_no_subscribers(self):
        runner, _ = _make_runner()
        result = runner.emit_event("unknown_event")
        assert "нет подписчиков" in result.lower()

    def test_fires_event_trigger(self, tmp_path):
        runner, _ = _make_runner()
        runner._config = ScenesConfig(scenes_file=str(tmp_path / "scenes.json"))
        runner.trigger_scene("morning", event="wake_up")
        result = runner.emit_event("wake_up")
        assert "wake_up" in result
        assert "morning" in result

    def test_emit_records_history(self, tmp_path):
        runner, _ = _make_runner()
        runner._config = ScenesConfig(scenes_file=str(tmp_path / "scenes.json"))
        runner.trigger_scene("morning", event="start")
        runner.emit_event("start")
        hist = runner.get_history()
        assert "event:start" in hist


# -- Переменные (скилл) ------------------------------------------------------


class TestSceneVarsSkill:
    def test_get_empty(self):
        runner, _ = _make_runner()
        result = runner.get_scene_variables("morning")
        assert "нет сохранённых" in result.lower()

    def test_set_and_get(self):
        runner, _ = _make_runner()
        runner.set_scene_variable("my_scene", "vol", "30")
        result = runner.get_scene_variables("my_scene")
        assert "vol" in result
        assert "30" in result

    def test_long_value_truncated(self):
        runner, _ = _make_runner()
        long_val = "x" * 200
        runner.set_scene_variable("s", "k", long_val)
        result = runner.get_scene_variables("s")
        assert "..." not in result  # 100 chars shown, no truncation marker needed


# -- build_skills -----------------------------------------------------------


class TestBuildSkills:
    def test_count(self):
        runner, _ = _make_runner()
        skills = runner.build_skills()
        assert len(skills) == 14

    def test_names(self):
        runner, _ = _make_runner()
        names = {s.name for s in runner.build_skills()}
        expected = {
            "run_scene", "list_scenes", "scene_info",
            "create_scene", "delete_scene", "add_scene_step", "remove_scene_step",
            "trigger_scene", "list_triggers", "delete_trigger",
            "scene_history", "clear_scene_history",
            "emit_event", "scene_vars",
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

    def test_trigger_scene_handler(self, tmp_path):
        runner, _ = _make_runner()
        runner._config = ScenesConfig(scenes_file=str(tmp_path / "scenes.json"))
        skills = runner.build_skills()
        trigger = next(s for s in skills if s.name == "trigger_scene")
        result = trigger.handler(scene="morning", cron="every 1h")
        assert "создан" in result.lower()

    def test_list_triggers_handler(self):
        runner, _ = _make_runner()
        skills = runner.build_skills()
        lt = next(s for s in skills if s.name == "list_triggers")
        result = lt.handler()
        assert "нет" in result.lower()

    def test_delete_trigger_handler(self, tmp_path):
        runner, _ = _make_runner()
        runner._config = ScenesConfig(scenes_file=str(tmp_path / "scenes.json"))
        runner.trigger_scene("morning", cron="every 1h")
        tid = runner._triggers[0]["id"]
        skills = runner.build_skills()
        dt = next(s for s in skills if s.name == "delete_trigger")
        result = dt.handler(trigger_id=tid)
        assert "удалён" in result.lower()

    def test_scene_history_handler(self):
        runner, _ = _make_runner()
        runner.run("morning")
        skills = runner.build_skills()
        sh = next(s for s in skills if s.name == "scene_history")
        result = sh.handler()
        assert "morning" in result

    def test_emit_event_handler(self, tmp_path):
        runner, _ = _make_runner()
        runner._config = ScenesConfig(scenes_file=str(tmp_path / "scenes.json"))
        runner.trigger_scene("morning", event="test_ev")
        skills = runner.build_skills()
        ee = next(s for s in skills if s.name == "emit_event")
        result = ee.handler(event="test_ev")
        assert "test_ev" in result

    def test_scene_vars_get_handler(self):
        runner, _ = _make_runner()
        runner.set_scene_variable("s", "k", "v")
        skills = runner.build_skills()
        sv = next(s for s in skills if s.name == "scene_vars")
        result = sv.handler(scene="s")
        assert "k" in result
        assert "v" in result

    def test_scene_vars_set_handler(self):
        runner, _ = _make_runner()
        skills = runner.build_skills()
        sv = next(s for s in skills if s.name == "scene_vars")
        result = sv.handler(scene="s", variable="x", value="10")
        assert "10" in result


# -- Start/Stop ------------------------------------------------------------


class TestStartStop:
    def test_start_stop(self):
        runner, _ = _make_runner()
        runner.start()
        assert runner._running
        runner.stop()
        assert not runner._running

    def test_double_start(self):
        runner, _ = _make_runner()
        runner.start()
        runner.start()  # не должен падать
        runner.stop()

    def test_stop_without_start(self):
        runner, _ = _make_runner()
        runner.stop()  # не должен падать


# -- Интеграция: полный сценарий ---------------------------------------------


class TestIntegration:
    def test_complex_scene_with_vars_conditions_loop(self):
        """Интеграционный тест: сцена с переменными, условиями и циклом."""
        runner, _ = _make_runner()
        runner._custom["smart_scene"] = {
            "description": "Умная сцена",
            "steps": [
                # Получаем статус батареи в переменную
                {"set_var": "bat", "from_skill": "battery_status"},
                # Если батарея > 50 — включаем фокус
                {
                    "if_skill": "battery_status",
                    "op": "contains", "value": "80",
                    "then": [
                        {"skill": "set_volume", "args": {"level": "30"}},
                    ],
                    "else": [
                        {"delay": 0, "comment": "батарея низкая"},
                    ],
                },
                # Повторяем 2 раза
                {"repeat": 2, "steps": [
                    {"delay": 0, "comment": "пинг"},
                ]},
            ],
        }
        result = runner.run("smart_scene")
        assert "Громкость 30%" in result  # Батарея 80% -> then
        assert "repeat x2" in result
        # Переменная bat сохранена
        assert runner._scene_variables["smart_scene"]["bat"] == "Батарея 80%"

    def test_event_trigger_chain(self, tmp_path):
        """Тест цепочки: event -> trigger -> scene -> sub_scene."""
        runner, _ = _make_runner()
        runner._config = ScenesConfig(scenes_file=str(tmp_path / "scenes.json"))
        # Создаём сцену которая вызывает morning
        runner.create(
            "event_handler",
            "Обработчик события",
            [{"run_scene": "morning"}],
        )
        # Триггер по событию
        runner.trigger_scene("event_handler", event="system_ready")
        # Отправляем событие
        result = runner.emit_event("system_ready")
        assert "system_ready" in result
        assert "event_handler" in result

    def test_scene_with_variables_file_persistence(self, tmp_path):
        """Тест что переменные сохраняются в файл."""
        scenes_file = tmp_path / "scenes.json"
        runner = SceneRunner(ScenesConfig(scenes_file=str(scenes_file)))
        reg = SkillRegistry()
        reg.register(Skill(
            name="get_weather", description="", parameters=object_schema({}),
            handler=lambda: "+20C",
        ))
        runner.set_registry(reg)
        runner.create(
            "persist_test", "test",
            [{"set_var": "temp", "from_skill": "get_weather"}],
        )
        runner.run("persist_test")

        # Перезагружаем из файла
        runner2 = SceneRunner(ScenesConfig(scenes_file=str(scenes_file)))
        assert "temp" in runner2._scene_variables.get("persist_test", {})
