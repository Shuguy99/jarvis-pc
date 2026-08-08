"""Автоматизации и сцены: создание, выполнение и управление.

Сцена -- это именованная последовательность шагов (вызовов навыков).
Шаг может быть:
  - вызовом навыка с аргументами: {"skill": "set_volume", "args": {"level": 30}}}
  - задержкой: {"delay": 2, "comment": "пауза"}
  - условием (простое):
      {"if_skill": "battery_status", "contains": "низкий", "then": [...]}
  - условием (расширенное):
      {"if_skill": "battery_status",
       "op": "lt", "value": "20",
       "then": [...], "else": [...]}
      Операторы: contains, not_contains, equals, not_equals,
                  gt, gte, lt, lte, matches (regex), empty, not_empty
  - группа условий (AND/OR):
      {"conditions": {
        "op": "and",  # или "or"
        "checks": [
          {"if_skill": "battery_status", "op": "lt", "value": "20"},
          {"if_skill": "get_weather", "contains": "дождь"}
        ]},
       "then": [...], "else": [...]}
  - установка переменной: {"set_var": "volume_level", "value": "30"}
  - получение переменной в аргументы: {"skill": "set_volume",
      "args": {"level": "{{volume_level}}"}}
  - переменная из навыка: {"set_var": "status", "from_skill": "battery_status"}
  - повтор (N раз):
      {"repeat": 3, "steps": [{"skill": "beep", "args": {}}]}
  - цикл (пока условие):
      {"loop": {"if_skill": "some_check", "contains": "go"},
       "steps": [...], "max_iterations": 10}
  - вызов другой сцены:
      {"run_scene": "morning"}

Триггеры:
  - по времени (cron): {"scene": "morning", "cron": "0 7 * * *"}
  - по событию:     {"scene": "evening", "event": "battery_low"}

Переменные:
  - {{var_name}} подставляются в args и comment перед выполнением
  - set_var сохраняет результат для использования в последующих шагах

Пользовательские сцены, триггеры и переменные сохраняются в JSON файл.
Встроенные сцены всегда доступны.

Голосовые команды:
  "Джарвис, запусти сцену утро"
  "Джарвис, создай сцену работа: громкость 40, помодоро"
  "Джарвис, удали сцену работа"
  "Джарвис, покажи сцены"
  "Джарвис, добавь шаг в сцену работа: погода"
  "Джарвис, информация о сцене утро"
  "Джарвис, поставь триггер на сцену утро каждый день в 7 утра"
  "Джарвис, удали триггер утро"
  "Джарвис, покажи триггеры"
  "Джарвис, история сцен"
  "Джарвис, отправь событие battery_low"

Пример JSON::

    {
        "my_scene": {
            "description": "Моя сцена",
            "variables": {"volume": "30"},
            "steps": [
                {"skill": "set_volume", "args": {"level": "{{volume}}"}},
                {"delay": 2},
                {"skill": "get_weather", "args": {}}
            ]
        },
        "triggers": [
            {"id": "tr_1", "scene": "morning", "cron": "0 7 * * 1-5", "enabled": true}
        ]
    }
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from ..config import ScenesConfig
from .registry import Skill, SkillRegistry, object_schema

log = logging.getLogger(__name__)


# -- Встроенные сцены -----------------------------------------------------------


BUILTIN_SCENES: dict[str, dict[str, Any]] = {
    "morning": {
        "description": "Утренняя сцена: погода, события, новости.",
        "steps": [
            {"skill": "get_weather", "args": {}},
            {"skill": "today_events", "args": {}},
            {"skill": "get_news", "args": {}},
        ],
    },
    "work": {
        "description": "Рабочая сцена: статус системы, громкость 40%, помодоро.",
        "steps": [
            {"skill": "system_status", "args": {}},
            {"skill": "set_volume", "args": {"level": 40}},
            {"skill": "pomodoro_status", "args": {}},
        ],
    },
    "evening": {
        "description": "Вечерняя сцена: прогноз, расходы, батарея.",
        "steps": [
            {"skill": "get_forecast", "args": {}},
            {"skill": "expense_summary", "args": {"period": "day"}},
            {"skill": "battery_status", "args": {}},
        ],
    },
    "focus": {
        "description": "Сцена фокуса: громкость 30%, запуск помодоро.",
        "steps": [
            {"skill": "set_volume", "args": {"level": 30}},
            {"skill": "pomodoro_start", "args": {}},
        ],
    },
    "night": {
        "description": "Ночная сцена: тихий режим, статус будильника, батареи.",
        "steps": [
            {"skill": "set_volume", "args": {"level": 10}},
            {"skill": "alarm_status", "args": {}},
            {"skill": "battery_status", "args": {}},
        ],
    },
    "goodbye": {
        "description": "Сцена прощания: сохранить заметки, статус системы, выход.",
        "steps": [
            {"skill": "system_status", "args": {}},
            {"skill": "battery_status", "args": {}},
        ],
    },
}


# -- Утилиты -------------------------------------------------------------------


_VAR_RE = re.compile(r"\{\{(\w+)\}\}")


def _substitute_vars(obj: Any, variables: dict[str, str]) -> Any:
    """Рекурсивная подстановка {{var}} в строках, списках, словарях."""
    if isinstance(obj, str):
        return _VAR_RE.sub(lambda m: variables.get(m.group(1), m.group(0)), obj)
    if isinstance(obj, dict):
        return {k: _substitute_vars(v, variables) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_substitute_vars(item, variables) for item in obj]
    return obj


def _safe_number(value: str) -> float | None:
    """Пытается привести строку к числу."""
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _evaluate_condition(
    result_text: str,
    op: str,
    value: str,
) -> bool:
    """Проверяет условие по результату вызова навыка.

    Поддерживаемые операторы:
      contains, not_contains, equals, not_equals,
      gt, gte, lt, lte, matches, empty, not_empty
    """
    result_lower = result_text.lower()
    value_lower = value.lower()

    if op == "contains":
        return value_lower in result_lower
    if op == "not_contains":
        return value_lower not in result_lower
    if op == "equals":
        return result_lower == value_lower
    if op == "not_equals":
        return result_lower != value_lower
    if op in ("gt", "gte", "lt", "lte"):
        r_num = _safe_number(result_text.strip())
        v_num = _safe_number(value.strip())
        if r_num is not None and v_num is not None:
            if op == "gt":
                return r_num > v_num
            if op == "gte":
                return r_num >= v_num
            if op == "lt":
                return r_num < v_num
            if op == "lte":
                return r_num <= v_num
        return False
    if op == "matches":
        try:
            return bool(re.search(value, result_text, re.IGNORECASE))
        except re.error:
            return False
    if op == "empty":
        return len(result_text.strip()) == 0
    if op == "not_empty":
        return len(result_text.strip()) > 0
    # fallback: как contains
    return value_lower in result_lower


class EventBus:
    """Простой шина событий: подписчики по имени события."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[tuple[str, str]]] = {}
        # {event_name: [(trigger_id, scene_name), ...]}
        self._lock = threading.Lock()

    def subscribe(self, event: str, trigger_id: str, scene_name: str) -> None:
        with self._lock:
            self._subscribers.setdefault(event, []).append(
                (trigger_id, scene_name)
            )

    def unsubscribe(self, trigger_id: str) -> None:
        with self._lock:
            for event in list(self._subscribers):
                self._subscribers[event] = [
                    (tid, sname) for tid, sname in self._subscribers[event]
                    if tid != trigger_id
                ]
                if not self._subscribers[event]:
                    del self._subscribers[event]

    def emit(self, event: str) -> list[tuple[str, str]]:
        """Возвращает список (trigger_id, scene_name) для события."""
        with self._lock:
            return list(self._subscribers.get(event, []))

    def list_subscriptions(self) -> dict[str, int]:
        with self._lock:
            return {
                event: len(subs)
                for event, subs in sorted(self._subscribers.items())
            }


class SceneRunner:
    """Хранит, выполняет и управляет сценами (встроенные + пользовательские).

    Расширенные возможности:
    - Переменные сцены с подстановкой {{var}}
    - Расширенные условия (gt/lt/regex/equals и т.д.)
    - Группы условий (AND/OR)
    - Циклы repeat и loop
    - Вызов сцен из сцен (run_scene)
    - Триггеры по времени (cron) и событиям
    - Лог выполнения сцен
    - Event bus для межнавыкового взаимодействия
    """

    def __init__(self, config: ScenesConfig) -> None:
        self._config = config
        self._registry: SkillRegistry | None = None
        self._custom: dict[str, dict[str, Any]] = {}
        self._triggers: list[dict[str, Any]] = []
        self._history: list[dict[str, Any]] = []
        self._scene_variables: dict[str, dict[str, str]] = {}
        self._event_bus = EventBus()
        self._running: bool = False
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._history_max = 100
        self._load_custom()

    def set_registry(self, registry: SkillRegistry) -> None:
        """Инжектит реестр для вызова навыков внутри сцен."""
        self._registry = registry

    @property
    def event_bus(self) -> EventBus:
        """Доступ к шине событий для emit из других навыков."""
        return self._event_bus

    # -- Персистенция ---------------------------------------------------------------

    def _scenes_path(self) -> Path:
        p = Path(self._config.scenes_file).expanduser()
        p.parent.mkdir(parents=True, exist_ok=True)
        return p
    def _load_custom(self) -> None:
        path = self._scenes_path()
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    self._custom = {
                        k: v for k, v in data.items()
                        if isinstance(v, dict) and "steps" in v
                    }
                    self._triggers = data.get("triggers", [])
                    self._scene_variables = data.get("variables", {})
                    log.info(
                        "Загружено %d сцен, %d триггеров, %d наборов переменных",
                        len(self._custom), len(self._triggers),
                        len(self._scene_variables),
                    )
            except (json.JSONDecodeError, OSError):
                log.warning("Ошибка чтения файла сцен %s", path)

    def _save_custom(self) -> None:
        try:
            payload: dict[str, Any] = dict(self._custom)
            if self._triggers:
                payload["triggers"] = self._triggers
            if self._scene_variables:
                payload["variables"] = self._scene_variables
            self._scenes_path().write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            log.exception("Ошибка сохранения сцен")

    # -- Доступ к сценам --------------------------------------------------------------

    def _all_scenes(self) -> dict[str, dict[str, Any]]:
        """Все сцены: встроенные + пользовательские (пользовательские приоритетнее)."""
        merged = dict(BUILTIN_SCENES)
        merged.update(self._custom)
        return merged

    def get_scene(self, name: str) -> dict[str, Any] | None:
        return self._all_scenes().get(name)

    # -- Лог выполнения -----------------------------------------------------------

    def _add_history(
        self, scene_name: str, trigger: str = "manual",
        success: bool = True, steps_run: int = 0,
        result_summary: str = "",
    ) -> None:
        entry = {
            "scene": scene_name,
            "trigger": trigger,
            "success": success,
            "steps_run": steps_run,
            "summary": result_summary[:200],
            "time": datetime.now().isoformat(timespec="seconds"),
        }
        with self._lock:
            self._history.append(entry)
            if len(self._history) > self._history_max:
                self._history = self._history[-self._history_max:]

    def get_history(self) -> str:
        with self._lock:
            if not self._history:
                return "История выполнения сцен пуста, сэр."
            lines = [f"История сцен (последние {len(self._history)}):\n"]
            for entry in reversed(self._history):
                status = "ok" if entry["success"] else "FAIL"
                icon = "\u2705" if entry["success"] else "\u274c"
                lines.append(
                    f"  {icon} {entry['time']} | {entry['scene']} "
                    f"({entry['trigger']}, {entry['steps_run']} шагов) [{status}]"
                )
            return "\n".join(lines)

    def clear_history(self) -> str:
        with self._lock:
            count = len(self._history)
            self._history.clear()
        return f"История очищена ({count} записей), сэр."

    # -- Выполнение ---------------------------------------------------------------

    def _evaluate_single_condition(
        self, step: dict[str, Any], variables: dict[str, str],
    ) -> bool:
        """Вычисляет одно условие (if_skill). Возвращает True/False."""
        if not self._registry:
            return False

        skill_result = self._registry.call(
            step["if_skill"],
            _substitute_vars(step.get("if_args", {}), variables),
        )
        # Сохраняем результат навыка в переменную если указано
        if "save_to" in step:
            variables[step["save_to"]] = skill_result

        op = step.get("op", "contains")
        value = step.get("value", step.get("contains", ""))
        return _evaluate_condition(skill_result, op, value)

    def _execute_step(self, step: dict[str, Any], variables: dict[str, str]) -> str:
        """Выполняет один шаг сцены."""
        # -- set_var --
        if "set_var" in step:
            var_name = step["set_var"]
            if "from_skill" in step:
                if not self._registry:
                    return "  \u26a0 Реестр не инициализирован"
                value = self._registry.call(
                    step["from_skill"],
                    _substitute_vars(step.get("from_args", {}), variables),
                )
            else:
                value = _substitute_vars(str(step.get("value", "")), variables)
            variables[var_name] = value
            return f"  \U0001f4cb {var_name} = {value[:80]}"

        # -- delay --
        if "delay" in step:
            delay_s = step["delay"]
            comment = _substitute_vars(
                step.get("comment", f"задержка {delay_s}с"), variables,
            )
            time.sleep(min(delay_s, 30))
            return f"  \u23f1 {comment}"

        # -- condition group (AND/OR) --
        if "conditions" in step:
            return self._execute_condition_group(step, variables)

        # -- single condition (if_skill) --
        if "if_skill" in step:
            return self._execute_if(step, variables)

        # -- repeat (N раз) --
        if "repeat" in step:
            return self._execute_repeat(step, variables)

        # -- loop (пока условие) --
        if "loop" in step:
            return self._execute_loop(step, variables)

        # -- run_scene (вызов другой сцены) --
        if "run_scene" in step:
            scene_name = _substitute_vars(step["run_scene"], variables)
            return self._execute_sub_scene(scene_name, variables)

        # -- skill --
        if "skill" in step:
            if not self._registry:
                return "  \u26a0 Реестр не инициализирован"
            skill_name = step["skill"]
            args = _substitute_vars(step.get("args", {}), variables)
            result = self._registry.call(skill_name, args)
            comment = _substitute_vars(step.get("comment", ""), variables)
            line = f"  [{skill_name}] {result}"
            if comment:
                line = f"  // {comment}\n" + line
            return line

        return f"  \u26a0 Неизвестный шаг: {step}"

    def _execute_if(self, step: dict[str, Any], variables: dict[str, str]) -> str:
        """Выполняет условный шаг if_skill."""
        if not self._registry:
            return "  \u26a0 Реестр не инициализирован"

        result = self._evaluate_single_condition(step, variables)
        if result:
            sub_results = []
            for sub in step.get("then", []):
                sub_results.append(self._execute_step(sub, variables))
            op = step.get("op", "contains")
            value = step.get("value", step.get("contains", ""))
            label = f"{step['if_skill']} {op} '{value}'"
            return f"  \u2714 {label}\n" + "\n".join(sub_results)
        else:
            else_results = []
            for sub in step.get("else", []):
                else_results.append(self._execute_step(sub, variables))
            op = step.get("op", "contains")
            value = step.get("value", step.get("contains", ""))
            label = f"{step['if_skill']} {op} '{value}'"
            parts = [f"  \u2718 {label}"]
            if else_results:
                parts.append("\n".join(else_results))
            return "\n".join(parts)

    def _execute_condition_group(
        self, step: dict[str, Any], variables: dict[str, str],
    ) -> str:
        """Выполняет группу условий (AND/OR)."""
        if not self._registry:
            return "  \u26a0 Реестр не инициализирован"

        group = step["conditions"]
        group_op = group.get("op", "and").lower()
        checks = group.get("checks", [])

        results = []
        all_true = True
        any_true = False
        for check in checks:
            passed = self._evaluate_single_condition(check, variables)
            results.append(passed)
            if not passed:
                all_true = False
            else:
                any_true = True

        if group_op == "or":
            condition_met = any_true
        else:
            condition_met = all_true

        op_label = group_op.upper()
        passed_count = sum(results)
        total_count = len(results)
        header = f"  {'\u2714' if condition_met else '\u2718'} [{op_label}] {passed_count}/{total_count} условий"

        sub_results: list[str] = []
        if condition_met:
            for sub in step.get("then", []):
                sub_results.append(self._execute_step(sub, variables))
        else:
            for sub in step.get("else", []):
                sub_results.append(self._execute_step(sub, variables))

        parts = [header]
        if sub_results:
            parts.append("\n".join(sub_results))
        return "\n".join(parts)

    def _execute_repeat(self, step: dict[str, Any], variables: dict[str, str]) -> str:
        """Выполняет шаги N раз."""
        count = min(step.get("repeat", 1), 20)
        steps = step.get("steps", [])
        if not steps:
            return "  \u26a0 Пустой repeat"
        results = [f"  \U0001f501 repeat x{count}"]
        for i in range(count):
            for sub in steps:
                results.append(self._execute_step(sub, variables))
        return "\n".join(results)

    def _execute_loop(self, step: dict[str, Any], variables: dict[str, str]) -> str:
        """Выполняет шаги в цикле, пока условие выполняется."""
        loop_def = step["loop"]
        max_iter = min(step.get("max_iterations", 10), 20)
        steps = step.get("steps", [])
        if not steps:
            return "  \u26a0 Пустой loop"

        results = [f"  \U0001f504 loop (макс {max_iter})"]
        for i in range(max_iter):
            if "conditions" in loop_def:
                group = loop_def["conditions"]
                group_op = group.get("op", "and").lower()
                checks = group.get("checks", [])
                check_results = []
                for check in checks:
                    check_results.append(
                        self._evaluate_single_condition(check, variables)
                    )
                if group_op == "or":
                    condition_met = any(check_results)
                else:
                    condition_met = all(check_results)
            elif "if_skill" in loop_def:
                condition_met = self._evaluate_single_condition(loop_def, variables)
            else:
                condition_met = False

            if not condition_met:
                results.append(f"  \u23f9 цикл завершён после {i} итераций")
                break

            for sub in steps:
                results.append(self._execute_step(sub, variables))
        else:
            results.append(f"  \u26a0 цикл достиг лимита {max_iter}")

        return "\n".join(results)

    def _execute_sub_scene(
        self, scene_name: str, parent_vars: dict[str, str],
    ) -> str:
        """Выполняет вложенную сцену с передачей переменных."""
        scene = self.get_scene(scene_name)
        if scene is None:
            return f"  \u26a0 Вложенная сцена '{scene_name}' не найдена"
        steps = scene.get("steps", [])
        if not steps:
            return f"  \u26a0 Вложенная сцена '{scene_name}' пуста"

        results = [f"  \U0001f3ac вложенная сцена '{scene_name}':"]
        for step in steps:
            results.append(self._execute_step(step, parent_vars))
        return "\n".join(results)

    def run(self, name: str) -> str:
        """Выполняет сцену по имени."""
        scene = self.get_scene(name)
        if scene is None:
            available = ", ".join(sorted(self._all_scenes()))
            return f"Сцена '{name}' не найдена. Доступные: {available}, сэр."

        description = scene.get("description", "")
        steps = scene.get("steps", [])
        if not steps:
            return f"Сцена '{name}' пуста, сэр."

        # Инициализируем переменные сцены
        variables: dict[str, str] = {}
        # Глобальные переменные из сохранённых
        if name in self._scene_variables:
            variables.update(self._scene_variables[name])
        # Локальные переменные из определения сцены
        for k, v in scene.get("variables", {}).items():
            variables[k] = str(v)

        results: list[str] = [
            f"\U0001f3a8 Сцена '{name}': {description}"
        ]
        steps_run = 0
        success = True
        try:
            for i, step in enumerate(steps, 1):
                step_result = self._execute_step(step, variables)
                steps_run += 1
                results.append(f"{i}.{step_result}")
                if "\u26d4" in step_result or "прерван" in step_result.lower():
                    results.append("  \u26d4 Сцена прервана.")
                    success = False
                    break
        except Exception as exc:
            log.exception("Ошибка выполнения сцены %s", name)
            results.append(f"  \u26a0 Ошибка: {exc}")
            success = False

        # Сохраняем переменные обратно (если были изменены через set_var)
        with self._lock:
            self._scene_variables[name] = variables
        self._save_custom()

        self._add_history(
            name, trigger="manual", success=success,
            steps_run=steps_run,
            result_summary=results[-1] if results else "",
        )
        return "\n".join(results)

    # -- Триггеры ------------------------------------------------------------------

    def _cron_to_seconds(self, cron: str) -> int | None:
        """Конвертирует простой cron в интервал в секундах.

        Поддерживаемые форматы:
          - "every Ns/m/h/d" — каждые N секунд/минут/часов/дней
          - "N * * * *" — каждую N-ю минуту
          - "* N * * *" — каждый час в N-ю минуту
          - "N M * * *" — ежедневно в M:N
          - "N M * * 1-5" — по будням в M:N
        """
        cron = cron.strip().lower()

        # every Ns / every Nm / every Nh / every Nd
        m = re.match(r"every\s+(\d+)\s*(s|m|h|d)", cron)
        if m:
            n = int(m.group(1))
            unit = m.group(2)
            if unit == "s":
                return max(n, 5)
            if unit == "m":
                return max(n * 60, 5)
            if unit == "h":
                return n * 3600
            if unit == "d":
                return n * 86400

        # Простой cron: разобьём на поля
        parts = cron.split()
        if len(parts) >= 5:
            try:
                minute = parts[0]
                hour = parts[1]
                dom = parts[2]
                month = parts[3]
                dow = parts[4]

                # Каждую N-ю минуту: "N * * * *"
                if (minute != "*" and hour == "*" and dom == "*"
                        and month == "*" and dow == "*"):
                    return max(int(minute) * 60, 5)

                # Каждый час в N-ю минуту: "* N * * *"
                if (minute == "*" and hour != "*" and dom == "*"
                        and month == "*" and dow == "*"):
                    return 3600  # проверяем раз в час

                # Ежедневно в M:N
                if (minute != "*" and hour != "*" and dom == "*"
                        and month == "*" and dow == "*"):
                    h, m_val = int(hour), int(minute)
                    now = datetime.now()
                    target = now.replace(hour=h, minute=m_val, second=0, microsecond=0)
                    if target <= now:
                        from datetime import timedelta
                        target += timedelta(days=1)
                    return max(int((target - now).total_seconds()), 5)

                # По будням в M:N
                if (minute != "*" and hour != "*" and dom == "*"
                        and month == "*" and dow != "*"):
                    h, m_val = int(hour), int(minute)
                    now = datetime.now()
                    target = now.replace(hour=h, minute=m_val, second=0, microsecond=0)
                    if target <= now:
                        from datetime import timedelta
                        target += timedelta(days=1)
                    return max(int((target - now).total_seconds()), 5)

                # "0 0 * * *" — каждый день в полночь
                if (minute == "0" and hour == "0" and dom == "*"
                        and month == "*" and dow == "*"):
                    now = datetime.now()
                    from datetime import timedelta
                    target = now.replace(hour=0, minute=0, second=0, microsecond=0)
                    target += timedelta(days=1)
                    return max(int((target - now).total_seconds()), 5)

            except (ValueError, IndexError):
                pass

        # Fallback: пробуем как число секунд
        try:
            return max(int(cron), 5)
        except ValueError:
            return None

    def _trigger_loop(self) -> None:
        """Фоновый поток: проверяет cron-триггеры."""
        log.info("Фоновый поток триггеров запущен")
        while self._running:
            time.sleep(10)  # проверяем каждые 10 секунд
            if not self._running:
                break
            now = datetime.now()
            with self._lock:
                triggers = list(self._triggers)
            for trigger in triggers:
                if not trigger.get("enabled", True):
                    continue
                cron = trigger.get("cron", "")
                if not cron:
                    continue
                scene_name = trigger.get("scene", "")
                if not scene_name:
                    continue

                # Проверяем, пора ли
                interval = self._cron_to_seconds(cron)
                if interval is None:
                    continue

                last_run = trigger.get("last_run", "")
                if last_run:
                    try:
                        last_dt = datetime.fromisoformat(last_run)
                        elapsed = (now - last_dt).total_seconds()
                        if elapsed < interval - 15:  # 15с погрешность
                            continue
                    except (ValueError, TypeError):
                        pass

                # Запускаем сцену
                log.info("Триггер %s: запуск сцены %s", trigger["id"], scene_name)
                try:
                    self.run(scene_name)
                    trigger["last_run"] = now.isoformat(timespec="seconds")
                    self._save_custom()
                except Exception:
                    log.exception("Ошибка триггера %s", trigger["id"])

        log.info("Фоновый поток триггеров остановлен")

    def start(self) -> None:
        """Запускает фоновый поток триггеров."""
        if self._running:
            return
        self._running = True
        # Подписываем event-триггеры
        for trigger in self._triggers:
            if trigger.get("event") and trigger.get("enabled", True):
                self._event_bus.subscribe(
                    trigger["event"], trigger["id"], trigger.get("scene", ""),
                )
        self._thread = threading.Thread(
            target=self._trigger_loop, daemon=True, name="scene-triggers",
        )
        self._thread.start()
        log.info("Триггеры сцен запущены (%d cron, %d events)",
                 sum(1 for t in self._triggers if t.get("cron")),
                 sum(1 for t in self._triggers if t.get("event")))

    def stop(self) -> None:
        """Останавливает фоновый поток триггеров."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None

    def trigger_scene(
        self, scene: str, cron: str = "", event: str = "", description: str = "",
    ) -> str:
        """Создаёт триггер для автоматического запуска сцены."""
        safe_name = scene.strip().lower().replace(" ", "_")
        if safe_name not in self._all_scenes():
            return (
                f"Сцена '{safe_name}' не найдена. "
                f"Сначала создайте её, сэр."
            )

        if not cron and not event:
            return "Укажите cron (расписание) или event (событие) для триггера, сэр."

        trigger_id = f"tr_{uuid.uuid4().hex[:8]}"
        trigger = {
            "id": trigger_id,
            "scene": safe_name,
            "description": description or f"Триггер: {safe_name}",
            "enabled": True,
        }
        if cron:
            interval = self._cron_to_seconds(cron)
            if interval is None:
                return f"Некорректный формат cron: '{cron}', сэр."
            trigger["cron"] = cron
            interval_min = interval / 60
            if interval_min >= 60:
                interval_str = f"{interval_min / 60:.1f}ч"
            else:
                interval_str = f"{interval_min:.0f}мин"
        if event:
            trigger["event"] = event
            self._event_bus.subscribe(event, trigger_id, safe_name)

        with self._lock:
            self._triggers.append(trigger)
        self._save_custom()

        parts = [f"Триггер {trigger_id} создан для сцены '{safe_name}'"]
        if cron:
            parts.append(f"(cron: {cron}, ~{interval_str})")
        if event:
            parts.append(f"(событие: {event})")
        return " ".join(parts) + ", сэр."

    def delete_trigger(self, trigger_id: str) -> str:
        """Удаляет триггер по ID."""
        with self._lock:
            for i, t in enumerate(self._triggers):
                if t["id"] == trigger_id:
                    self._triggers.pop(i)
                    self._event_bus.unsubscribe(trigger_id)
                    self._save_custom()
                    return f"Триггер {trigger_id} удалён, сэр."
        return f"Триггер {trigger_id} не найден, сэр."

    def list_triggers(self) -> str:
        """Показывает все триггеры."""
        with self._lock:
            triggers = list(self._triggers)
        if not triggers:
            return "Нет активных триггеров, сэр."
        lines = [f"Триггеры ({len(triggers)}):\n"]
        for t in triggers:
            tid = t["id"]
            scene = t.get("scene", "?")
            enabled = "\u2705" if t.get("enabled", True) else "\u274c"
            desc = t.get("description", "")
            parts = [f"  {enabled} {tid} -> {scene}"]
            if t.get("cron"):
                parts.append(f"[cron: {t['cron']}]")
            if t.get("event"):
                parts.append(f"[event: {t['event']}]")
            if desc:
                parts.append(f"\n    {desc}")
            lines.append(" ".join(parts))
        return "\n".join(lines)

    def emit_event(self, event: str) -> str:
        """Отправляет событие в шину, запуская привязанные сцены."""
        subscriptions = self._event_bus.emit(event)
        if not subscriptions:
            return f"Событие '{event}' отправлено (нет подписчиков), сэр."

        results = [f"\U0001f4e2 Событие '{event}' -> {len(subscriptions)} триггеров:"]
        for trigger_id, scene_name in subscriptions:
            results.append(f"  \U0001f504 Запуск '{scene_name}' (триггер {trigger_id})")
            try:
                run_result = self.run(scene_name)
                self._add_history(
                    scene_name, trigger=f"event:{event}",
                    success=True, steps_run=0, result_summary=run_result[:200],
                )
            except Exception as exc:
                results.append(f"  \u26a0 Ошибка: {exc}")
        return "\n".join(results)

    def get_scene_variables(self, scene_name: str) -> str:
        """Показывает переменные сцены."""
        with self._lock:
            variables = self._scene_variables.get(scene_name, {})
        if not variables:
            return f"У сцены '{scene_name}' нет сохранённых переменных, сэр."
        lines = [f"Переменные сцены '{scene_name}':"]
        for k, v in sorted(variables.items()):
            display = v[:100] if len(v) > 100 else v
            lines.append(f"  {k} = {display}")
        return "\n".join(lines)

    def set_scene_variable(
        self, scene_name: str, var_name: str, value: str,
    ) -> str:
        """Устанавливает переменную сцены."""
        with self._lock:
            if scene_name not in self._scene_variables:
                self._scene_variables[scene_name] = {}
            self._scene_variables[scene_name][var_name] = value
        self._save_custom()
        return f"{scene_name}.{var_name} = {value[:80]}, сэр."

    # -- CRUD пользовательских сцен -----------------------------------------------

    def create(self, name: str, description: str, steps: list[dict[str, Any]]) -> str:
        """Создаёт пользовательскую сцену."""
        if not steps:
            return "Укажите хотя бы один шаг для сцены, сэр."
        safe_name = name.strip().lower().replace(" ", "_")
        if safe_name in BUILTIN_SCENES:
            return f"Сцена '{safe_name}' -- встроенная, нельзя перезаписать, сэр."
        self._custom[safe_name] = {
            "description": description,
            "steps": steps,
        }
        self._save_custom()
        step_summary = ", ".join(
            s.get("skill", f"задержка {s.get('delay', '?')}с")
            for s in steps if "skill" in s or "delay" in s
        )
        return f"Сцена '{safe_name}' создана ({len(steps)} шагов: {step_summary}), сэр."

    def delete(self, name: str) -> str:
        """Удаляет пользовательскую сцену."""
        safe_name = name.strip().lower().replace(" ", "_")
        if safe_name in BUILTIN_SCENES:
            return f"Сцена '{safe_name}' -- встроенная, нельзя удалить, сэр."
        if safe_name not in self._custom:
            available = ", ".join(sorted(self._custom)) or "нет"
            return f"Пользовательская сцена '{safe_name}' не найдена. Есть: {available}, сэр."
        del self._custom[safe_name]
        # Удаляем связанные триггеры
        with self._lock:
            removed = [
                t for t in self._triggers
                if t.get("scene") == safe_name
            ]
            for t in removed:
                self._event_bus.unsubscribe(t["id"])
                self._triggers.remove(t)
        # Удаляем переменные
        with self._lock:
            self._scene_variables.pop(safe_name, None)
        self._save_custom()
        msg = f"Сцена '{safe_name}' удалена, сэр."
        if removed:
            msg += f" Удалено {len(removed)} связанных триггеров."
        return msg

    def add_step(self, name: str, step: dict[str, Any], position: int = -1) -> str:
        """Добавляет шаг в существующую сцену (в конец или на позицию)."""
        safe_name = name.strip().lower().replace(" ", "_")
        scenes = self._all_scenes()
        if safe_name not in scenes:
            return f"Сцена '{safe_name}' не найдена, сэр."

        scene = dict(scenes[safe_name])
        steps = list(scene.get("steps", []))
        if 0 <= position <= len(steps):
            steps.insert(position, step)
        else:
            steps.append(step)
        scene["steps"] = steps

        if safe_name in self._custom:
            self._custom[safe_name] = scene
            self._save_custom()
        elif safe_name in BUILTIN_SCENES:
            self._custom[safe_name] = scene
            self._save_custom()
        return f"Шаг добавлен в '{safe_name}' (позиция {len(steps)}), сэр."

    def remove_step(self, name: str, position: int) -> str:
        """Удаляет шаг из сцены по позиции (1-based)."""
        safe_name = name.strip().lower().replace(" ", "_")
        scenes = self._all_scenes()
        if safe_name not in scenes:
            return f"Сцена '{safe_name}' не найдена, сэр."

        scene = dict(scenes[safe_name])
        steps = list(scene.get("steps", []))
        idx = position - 1
        if idx < 0 or idx >= len(steps):
            return f"Позиция {position} вне диапазона (1--{len(steps)}), сэр."
        removed = steps.pop(idx)
        scene["steps"] = steps

        if safe_name in self._custom:
            self._custom[safe_name] = scene
            self._save_custom()
        elif safe_name in BUILTIN_SCENES:
            self._custom[safe_name] = scene
            self._save_custom()
        step_label = (
            removed.get("skill", "")
            or removed.get("set_var", "переменная")
            or removed.get("run_scene", f"сцена {removed.get('run_scene', '')}")
            or f"задержка"
        )
        return f"Шаг {position} ({step_label}) удалён из '{safe_name}', сэр."

    # -- Информация ---------------------------------------------------------------

    def list_all(self) -> str:
        """Показывает все доступные сцены."""
        all_scenes = self._all_scenes()
        if not all_scenes:
            return "Нет доступных сцен, сэр."

        builtin_count = len(BUILTIN_SCENES)
        custom_count = len(self._custom)
        lines = [
            f"Сцены ({builtin_count} встроенных + {custom_count} пользовательских):\n"
        ]
        for name, scene in sorted(all_scenes.items()):
            desc = scene.get("description", "")
            steps = scene.get("steps", [])
            is_custom = "\u2605" if name in self._custom else ""
            # Считаем только основные шаги (не вложенные)
            main_steps = [
                s for s in steps
                if any(k in s for k in ("skill", "delay", "set_var", "run_scene",
                                        "if_skill", "conditions", "repeat", "loop"))
            ]
            step_labels = []
            for s in main_steps[:5]:
                if "skill" in s:
                    step_labels.append(s["skill"])
                elif "delay" in s:
                    step_labels.append(f"\u23f1{s['delay']}с")
                elif "set_var" in s:
                    step_labels.append(f"\U0001f4cb{s['set_var']}")
                elif "run_scene" in s:
                    step_labels.append(f"\U0001f3ac{s['run_scene']}")
                elif "if_skill" in s or "conditions" in s:
                    step_labels.append("if?")
                elif "repeat" in s or "loop" in s:
                    step_labels.append("\U0001f501")
            if len(main_steps) > 5:
                step_labels.append("...")
            skill_names = ", ".join(step_labels)
            lines.append(f"  {is_custom}{name} -- {desc}")
            lines.append(f"    Шаги: {skill_names}")
        return "\n".join(lines)

    def info(self, name: str) -> str:
        """Подробная информация о сцене."""
        scene = self.get_scene(name)
        if scene is None:
            return f"Сцена '{name}' не найдена, сэр."

        is_builtin = name in BUILTIN_SCENES
        is_custom = name in self._custom
        kind = "встроенная" if is_builtin else "пользовательская"
        if is_builtin and is_custom:
            kind = "встроенная (модифицирована)"

        desc = scene.get("description", "")
        steps = scene.get("steps", [])
        lines = [f"Сцена '{name}' ({kind}): {desc}", f"Шагов: {len(steps)}"]

        # Переменные
        scene_vars = scene.get("variables", {})
        if scene_vars:
            lines.append(
                "Переменные: "
                + ", ".join(f"{k}={v}" for k, v in scene_vars.items())
            )

        for i, step in enumerate(steps, 1):
            lines.append(self._format_step_info(step, i))
        return "\n".join(lines)

    def _format_step_info(self, step: dict[str, Any], index: int) -> str:
        """Форматирует один шаг для отображения в info."""
        if "skill" in step:
            args_str = ""
            args = step.get("args", {})
            if args:
                args_str = ", " + ", ".join(
                    f"{k}={v}" for k, v in args.items()
                )
            return f"  {index}. {step['skill']}{args_str}"
        if "delay" in step:
            comment = step.get("comment", "")
            return f"  {index}. \u23f1 задержка {step['delay']}с {comment}"
        if "set_var" in step:
            if "from_skill" in step:
                return (
                    f"  {index}. \U0001f4cb {step['set_var']} "
                    f"= результат {step['from_skill']}"
                )
            return f"  {index}. \U0001f4cb {step['set_var']} = {step.get('value', '')}"
        if "run_scene" in step:
            return f"  {index}. \U0001f3ac вызвать сцену '{step['run_scene']}'"
        if "repeat" in step:
            count = step.get("repeat", "?")
            sub_count = len(step.get("steps", []))
            return f"  {index}. \U0001f501 repeat x{count} ({sub_count} шагов)"
        if "loop" in step:
            loop_def = step.get("loop", {})
            max_i = step.get("max_iterations", 10)
            if "if_skill" in loop_def:
                cond = f"пока {loop_def['if_skill']}"
            elif "conditions" in loop_def:
                cond = f"пока группа ({loop_def['conditions'].get('op', 'and').upper()})"
            else:
                cond = "пока ?"
            sub_count = len(step.get("steps", []))
            return f"  {index}. \U0001f504 {cond}, макс {max_i} ({sub_count} шагов)"
        if "if_skill" in step:
            op = step.get("op", "contains")
            value = step.get("value", step.get("contains", ""))
            then_n = len(step.get("then", []))
            else_n = len(step.get("else", []))
            parts = [f"  {index}. если {step['if_skill']} {op} '{value}'"]
            parts.append(f"    тогда: {then_n} шагов")
            if else_n:
                parts.append(f"    иначе: {else_n} шагов")
            return "\n".join(parts)
        if "conditions" in step:
            group = step["conditions"]
            group_op = group.get("op", "and").upper()
            checks = group.get("checks", [])
            then_n = len(step.get("then", []))
            else_n = len(step.get("else", []))
            parts = [f"  {index}. [{group_op}] {len(checks)} условий:"]
            for j, check in enumerate(checks, 1):
                c_op = check.get("op", "contains")
                c_val = check.get("value", check.get("contains", ""))
                parts.append(
                    f"    {j}. {check.get('if_skill', '?')} {c_op} '{c_val}'"
                )
            parts.append(f"    тогда: {then_n} шагов")
            if else_n:
                parts.append(f"    иначе: {else_n} шагов")
            return "\n".join(parts)
        return f"  {index}. {step}"

    # -- Навыки ---------------------------------------------------------------

    def build_skills(self) -> list[Skill]:
        """Создаёт навыки управления сценами."""
        return [
            Skill(
                name="run_scene",
                description=(
                    "Выполнить сцену по имени. "
                    "Сцена -- это последовательность вызовов навыков."
                ),
                parameters=object_schema(
                    {"name": {"type": "string", "description": "Имя сцены"}},
                    required=["name"],
                ),
                handler=self.run,
            ),
            Skill(
                name="list_scenes",
                description=(
                    "Показать все доступные сцены "
                    "(встроенные и пользовательские)."
                ),
                parameters=object_schema({}),
                handler=self.list_all,
            ),
            Skill(
                name="scene_info",
                description=(
                    "Подробная информация о сцене: "
                    "шаги, тип, описание, переменные."
                ),
                parameters=object_schema(
                    {"name": {"type": "string", "description": "Имя сцены"}},
                    required=["name"],
                ),
                handler=self.info,
            ),
            Skill(
                name="create_scene",
                description=(
                    "Создать пользовательскую сцену. "
                    "steps -- JSON-массив шагов. "
                    'Пример: [{"skill": "set_volume", "args": {"level": 30}}]'
                ),
                parameters=object_schema(
                    {
                        "name": {"type": "string", "description": "Имя сцены"},
                        "description": {
                            "type": "string",
                            "description": "Описание сцены",
                        },
                        "steps": {
                            "type": "array",
                            "description": "JSON-массив шагов сцены",
                        },
                    },
                    required=["name", "steps"],
                ),
                handler=lambda name, description="", steps=None: self.create(
                    name, description, steps or []
                ),
            ),
            Skill(
                name="delete_scene",
                description=(
                    "Удалить пользовательскую сцену "
                    "(встроенные нельзя удалить)."
                ),
                parameters=object_schema(
                    {"name": {"type": "string", "description": "Имя сцены"}},
                    required=["name"],
                ),
                handler=self.delete,
            ),
            Skill(
                name="add_scene_step",
                description=(
                    "Добавить шаг в сцену. step -- JSON-объект шага. "
                    'Пример: {"skill": "get_weather", "args": {}}'
                ),
                parameters=object_schema(
                    {
                        "name": {"type": "string", "description": "Имя сцены"},
                        "step": {
                            "type": "object",
                            "description": "JSON-объект шага сцены",
                        },
                        "position": {
                            "type": "integer",
                            "description": "Позиция вставки (по умолчанию в конец)",
                        },
                    },
                    required=["name", "step"],
                ),
                handler=lambda name, step, position=-1: self.add_step(
                    name, step, position
                ),
            ),
            Skill(
                name="remove_scene_step",
                description="Удалить шаг из сцены по позиции (1-based).",
                parameters=object_schema(
                    {
                        "name": {"type": "string", "description": "Имя сцены"},
                        "position": {
                            "type": "integer",
                            "description": "Номер шага (с 1)",
                        },
                    },
                    required=["name", "position"],
                ),
                handler=self.remove_step,
            ),
            # -- Триггеры --
            Skill(
                name="trigger_scene",
                description=(
                    "Создать триггер для автоматического запуска сцены. "
                    'cron: "every 30m", "0 7 * * *" (каждый день в 7:00), '
                    '"0 7 * * 1-5" (по будням). '
                    'event: имя события (например "battery_low"). '
                    "Можно указать оба параметра."
                ),
                parameters=object_schema(
                    {
                        "scene": {
                            "type": "string",
                            "description": "Имя сцены",
                        },
                        "cron": {
                            "type": "string",
                            "description": (
                                "Расписание cron или "
                                '"every Ns/m/h/d"'
                            ),
                        },
                        "event": {
                            "type": "string",
                            "description": "Имя события",
                        },
                        "description": {
                            "type": "string",
                            "description": "Описание триггера",
                        },
                    },
                    required=["scene"],
                ),
                handler=self.trigger_scene,
            ),
            Skill(
                name="list_triggers",
                description="Показать все активные триггеры сцен.",
                parameters=object_schema({}),
                handler=self.list_triggers,
            ),
            Skill(
                name="delete_trigger",
                description="Удалить триггер по ID.",
                parameters=object_schema(
                    {
                        "trigger_id": {
                            "type": "string",
                            "description": "ID триггера (из list_triggers)",
                        },
                    },
                    required=["trigger_id"],
                ),
                handler=self.delete_trigger,
            ),
            # -- История --
            Skill(
                name="scene_history",
                description="Показать историю выполнения сцен.",
                parameters=object_schema({}),
                handler=self.get_history,
            ),
            Skill(
                name="clear_scene_history",
                description="Очистить историю выполнения сцен.",
                parameters=object_schema({}),
                handler=self.clear_history,
            ),
            # -- События --
            Skill(
                name="emit_event",
                description=(
                    "Отправить событие в шину событий, "
                    "запустив привязанные триггеры и сцены. "
                    'Пример: emit_event(event="battery_low")'
                ),
                parameters=object_schema(
                    {
                        "event": {
                            "type": "string",
                            "description": "Имя события",
                        },
                    },
                    required=["event"],
                ),
                handler=self.emit_event,
            ),
            # -- Переменные --
            Skill(
                name="scene_vars",
                description=(
                    "Показать или установить переменные сцены. "
                    "Переменные подставляются как {{name}} в аргументах шагов."
                ),
                parameters=object_schema(
                    {
                        "scene": {
                            "type": "string",
                            "description": "Имя сцены",
                        },
                        "variable": {
                            "type": "string",
                            "description": "Имя переменной (для установки)",
                        },
                        "value": {
                            "type": "string",
                            "description": "Значение (для установки)",
                        },
                    },
                    required=["scene"],
                ),
                handler=lambda scene, variable="", value="": (
                    self.set_scene_variable(scene, variable, value)
                    if variable
                    else self.get_scene_variables(scene)
                ),
            ),
        ]
