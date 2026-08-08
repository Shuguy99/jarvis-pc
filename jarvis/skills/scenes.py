"""Автоматизации и сцены: создание, выполнение и управление.

Сцена -- это именованная последовательность шагов (вызовов навыков).
Шаг может быть:
  - вызовом навыка с аргументами: {"skill": "set_volume", "args": {"level": 30}}}
  - задержкой: {"delay": 2, "comment": "пауза"}
  - условием: {"if_skill": "battery_status", "contains": "низкий", "then": [...]}

Пользовательские сцены сохраняются в JSON файл.
Встроенные сцены всегда доступны.

Голосовые команды:
  \"Джарвис, запусти сцену утро\"
  \"Джарвис, создай сцену работа: громкость 40, помодоро\"
  \"Джарвис, удали сцену работа\"
  \"Джарвис, покажи сцены\"
  \"Джарвис, добавь шаг в сцену работа: погода\"
  \"Джарвис, информация о сцене утро\"

Пример JSON::

    {
        \"my_scene\": {
            \"description\": \"Моя сцена\",
            \"steps\": [
                {"skill": \"set_volume\", \"args\": {\"level\": 30}}},
                {"delay": 2},
                {"skill": \"get_weather\", \"args\": {}}}
            ]
        }
    }
"""

from __future__ import annotations

import json
import logging
import time
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


class SceneRunner:
    """Хранит, выполняет и управляет сценами (встроенные + пользовательские)."""

    def __init__(self, config: ScenesConfig) -> None:
        self._config = config
        self._registry: SkillRegistry | None = None
        self._custom: dict[str, dict[str, Any]] = {}
        self._load_custom()

    def set_registry(self, registry: SkillRegistry) -> None:
        """Инжектит реестр для вызова навыков внутри сцен."""
        self._registry = registry

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
                    log.info("Загружено %d пользовательских сцен", len(self._custom))
            except (json.JSONDecodeError, OSError):
                log.warning("Ошибка чтения файла сцен %s", path)

    def _save_custom(self) -> None:
        try:
            self._scenes_path().write_text(
                json.dumps(self._custom, ensure_ascii=False, indent=2),
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

    # -- Выполнение ---------------------------------------------------------------

    def _execute_step(self, step: dict[str, Any]) -> str:
        """Выполняет один шаг сцены."""
        if "delay" in step:
            delay_s = step["delay"]
            comment = step.get("comment", f"задержка {delay_s}с")
            time.sleep(min(delay_s, 30))  # максимум 30 сек
            return f"  \u23f1 {comment}"

        if "if_skill" in step:
            if not self._registry:
                return "  \u26a0 Реестр не инициализирован"
            result = self._registry.call(step["if_skill"], step.get("if_args", {}))
            condition = step.get("contains", "")
            if condition and condition.lower() in result.lower():
                sub_results = []
                for sub in step.get("then", []):
                    sub_results.append(self._execute_step(sub))
                return "  \u2714 Условие выполнено\n" + "\n".join(sub_results)
            else:
                for sub in step.get("else", []):
                    self._execute_step(sub)
                return f"  \u2718 Условие не выполнено ({condition})"

        if "skill" in step:
            if not self._registry:
                return "  \u26a0 Реестр не инициализирован"
            skill_name = step["skill"]
            args = step.get("args", {})
            result = self._registry.call(skill_name, args)
            comment = step.get("comment", "")
            line = f"  [{skill_name}] {result}"
            if comment:
                line = f"  // {comment}\n" + line
            return line

        return f"  \u26a0 Неизвестный шаг: {step}"

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

        results: list[str] = [f"\U0001f3a8 Сцена '{name}': {description}"]
        for i, step in enumerate(steps, 1):
            step_result = self._execute_step(step)
            results.append(f"{i}.{step_result}")
            if "прерван" in step_result.lower():
                results.append("  \u26d4 Сцена прервана.")
                break

        return "\n".join(results)

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
            s.get("skill", f"задержка {s.get('delay', '?')}с") for s in steps
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
        self._save_custom()
        return f"Сцена '{safe_name}' удалена, сэр."

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
        skill_name = removed.get("skill", f"задержка")
        return f"Шаг {position} ({skill_name}) удалён из '{safe_name}', сэр."

    # -- Информация ---------------------------------------------------------------

    def list_all(self) -> str:
        """Показывает все доступные сцены."""
        all_scenes = self._all_scenes()
        if not all_scenes:
            return "Нет доступных сцен, сэр."

        builtin_count = len(BUILTIN_SCENES)
        custom_count = len(self._custom)
        lines = [f"Сцены ({builtin_count} встроенных + {custom_count} пользовательских):\n"]
        for name, scene in sorted(all_scenes.items()):
            desc = scene.get("description", "")
            steps = scene.get("steps", [])
            is_custom = "\u2605" if name in self._custom else ""
            skill_names = ", ".join(
                s.get("skill", f"\u23f1{s.get('delay', '?')}с") for s in steps
            )
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
        for i, step in enumerate(steps, 1):
            if "skill" in step:
                args_str = ""
                args = step.get("args", {})
                if args:
                    args_str = ", " + ", ".join(f"{k}={v}" for k, v in args.items())
                lines.append(f"  {i}. {step['skill']}{args_str}")
            elif "delay" in step:
                comment = step.get("comment", "")
                lines.append(f"  {i}. \u23f1 задержка {step['delay']}с {comment}")
            elif "if_skill" in step:
                cond = step.get("contains", "")
                lines.append(f"  {i}. если {step['if_skill']} содержит '{cond}' -> {len(step.get('then', []))} шагов")
            else:
                lines.append(f"  {i}. {step}")
        return "\n".join(lines)

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
                description="Показать все доступные сцены (встроенные и пользовательские).",
                parameters=object_schema({}),
                handler=self.list_all,
            ),
            Skill(
                name="scene_info",
                description="Подробная информация о сцене: шаги, тип, описание.",
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
                        "description": {"type": "string", "description": "Описание"},
                        "steps": {
                            "type": "array",
                            "description": "JSON-массив шагов (см. документацию)",
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
                description="Удалить пользовательскую сцену (встроенные нельзя удалить).",
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
                handler=lambda name, step, position=-1: self.add_step(name, step, position),
            ),
            Skill(
                name="remove_scene_step",
                description="Удалить шаг из сцены по позиции (1-based).",
                parameters=object_schema(
                    {
                        "name": {"type": "string", "description": "Имя сцены"},
                        "position": {"type": "integer", "description": "Номер шага (с 1)"},
                    },
                    required=["name", "position"],
                ),
                handler=self.remove_step,
            ),
        ]
