"""Реестр навыков: описание инструментов для LLM и их исполнение."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)

SkillHandler = Callable[..., str]


@dataclass(frozen=True)
class Skill:
    """Один навык — функция, которую может вызвать модель."""

    name: str
    description: str
    parameters: dict[str, Any]
    handler: SkillHandler

    def to_openai_tool(self) -> dict[str, Any]:
        """Описание навыка в формате function calling."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class SkillRegistry:
    """Хранит навыки и выполняет их по имени."""

    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}

    def register(self, skill: Skill) -> None:
        """Добавляет навык, запрещая дубликаты имён."""
        if skill.name in self._skills:
            raise ValueError(f"Навык {skill.name} уже зарегистрирован")
        self._skills[skill.name] = skill

    def extend(self, skills: Iterable[Skill]) -> None:
        """Регистрирует несколько навыков."""
        for skill in skills:
            self.register(skill)

    def __contains__(self, name: object) -> bool:
        return name in self._skills

    def __len__(self) -> int:
        return len(self._skills)

    @property
    def names(self) -> list[str]:
        """Имена всех навыков."""
        return sorted(self._skills)

    def tool_specs(self) -> list[dict[str, Any]]:
        """Список описаний инструментов для LLM."""
        return [self._skills[name].to_openai_tool() for name in self.names]

    def call(self, name: str, arguments: dict[str, Any] | None = None) -> str:
        """Выполняет навык и всегда возвращает текстовый результат."""
        skill = self._skills.get(name)
        if skill is None:
            return f"Навык «{name}» не найден."
        try:
            return skill.handler(**(arguments or {}))
        except TypeError as exc:
            log.warning("Некорректные аргументы для %s: %s", name, exc)
            return f"Некорректные аргументы для навыка «{name}»: {exc}"
        except Exception as exc:  # навык не должен ронять ассистента
            log.exception("Ошибка навыка %s", name)
            return f"Навык «{name}» завершился ошибкой: {exc}"


def string_param(description: str) -> dict[str, Any]:
    """Схема одиночного строкового параметра."""
    return {"type": "string", "description": description}


def object_schema(properties: dict[str, Any], required: Iterable[str] = ()) -> dict[str, Any]:
    """Схема объекта параметров для function calling."""
    return {
        "type": "object",
        "properties": properties,
        "required": list(required),
    }
