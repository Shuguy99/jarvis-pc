"""Предустановленные сцены: автоматический запуск нескольких навыков."""

from __future__ import annotations

import logging
from typing import Any

from .registry import Skill, SkillRegistry, object_schema

log = logging.getLogger(__name__)

# Описание сцен: имя → (описание, список кортежей (навык, аргументы))
_SCENES: dict[str, tuple[str, list[tuple[str, dict[str, Any]]]]] = {
    "morning": (
        "Утренняя сцена: погода, события на сегодня, новости.",
        [
            ("get_weather", {}),
            ("today_events", {}),
            ("get_news", {}),
        ],
    ),
    "work": (
        "Рабочая сцена: статус системы, громкость 40%, статус помодоро.",
        [
            ("system_status", {}),
            ("set_volume", {"level": 40}),
            ("pomodoro_status", {}),
        ],
    ),
    "evening": (
        "Вечерняя сцена: прогноз погоды, расходы за день, заряд батареи.",
        [
            ("get_forecast", {}),
            ("expense_summary", {"period": "day"}),
            ("battery_status", {}),
        ],
    ),
    "focus": (
        "Сцена фокуса: громкость 30%, запуск помодоро.",
        [
            ("set_volume", {"level": 30}),
            ("pomodoro_start", {}),
        ],
    ),
}


def _run_scene(registry: SkillRegistry, name: str) -> str:
    """Выполняет сцену по имени, вызывая навыки через реестр."""
    scene = _SCENES.get(name)
    if scene is None:
        available = ", ".join(sorted(_SCENES))
        return f"Сцена «{name}» не найдена. Доступные: {available}, сэр."

    description, steps = scene
    results: list[str] = [f"🎨 Сцена «{name}»: {description}"]
    for skill_name, args in steps:
        result = registry.call(skill_name, args)
        results.append(f"  [{skill_name}] {result}")
    return "\n".join(results)


def _list_scenes() -> str:
    """Показывает доступные сцены."""
    lines = ["Доступные сцены:"]
    for name, (description, steps) in _SCENES.items():
        skill_names = ", ".join(s[0] for s in steps)
        lines.append(f"  {name} — {description} (навыки: {skill_names})")
    return "\n".join(lines)


def build_skills(registry: SkillRegistry) -> list[Skill]:
    """Создаёт навыки сцен. Требует реестр для вызова других навыков."""
    return [
        Skill(
            name="run_scene",
            description=(
                "Выполнить предустановленную сцену по имени. "
                "Доступные: morning, work, evening, focus."
            ),
            parameters=object_schema(
                {
                    "name": {
                        "type": "string",
                        "description": "Имя сцены: morning, work, evening, focus",
                    },
                },
                required=["name"],
            ),
            handler=lambda name: _run_scene(registry, name),
        ),
        Skill(
            name="list_scenes",
            description="Показать доступные предустановленные сцены.",
            parameters=object_schema({}),
            handler=lambda: _list_scenes(),
        ),
    ]
