"""Навыки управления голосовыми профилями Джарвиса."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .registry import Skill, object_schema, string_param

if TYPE_CHECKING:
    from ..profiles import ProfileManager


def _build_skills(manager: ProfileManager) -> list[Skill]:
    """Создаёт навыки для работы с профилями."""

    def switch_profile(profile_id: str = "") -> str:
        """Переключает голосовой профиль Джарвиса."""
        if not profile_id:
            return (
                f"Текущий профиль: «{manager.current.name}». "
                f"Укажите какой переключить."
            )
        # Нормализация: пробелы -> нижний регистр, убираем лишнее
        profile_id = profile_id.strip().lower()
        ok, msg = manager.switch(profile_id)
        return msg

    def list_profiles() -> str:
        """Показывает все доступные голосовые профили."""
        profiles = manager.list_profiles()
        current_id = manager.current_id
        lines = []
        for p in profiles:
            marker = " <- активный" if p.id == current_id else ""
            lines.append(f"  {p.id}: {p.description}{marker}")
        if not lines:
            return "Профили не найдены."
        return "Доступные профили:\n" + "\n".join(lines)

    def current_profile() -> str:
        """Показывает текущий активный профиль."""
        p = manager.current
        return f"Текущий профиль: «{p.name}» ({p.id}). {p.description}"

    return [
        Skill(
            name="switch_profile",
            description=(
                "Переключает голосовой профиль Джарвиса (личность, голос, стиль общения). "
                "Например: default, casual, strict, pirate."
            ),
            parameters=object_schema(
                {
                    "profile_id": {
                        "type": "string",
                        "description": (
                            "ID профиля: default (классический), casual (дружелюбный), "
                            "strict (военный), pirate (пиратский), или кастомный"
                        ),
                    }
                },
                required=["profile_id"],
            ),
            handler=switch_profile,
        ),
        Skill(
            name="list_profiles",
            description="Показывает все доступные голосовые профили Джарвиса.",
            parameters=object_schema({}),
            handler=list_profiles,
        ),
        Skill(
            name="current_profile",
            description="Показывает текущий активный голосовой профиль.",
            parameters=object_schema({}),
            handler=current_profile,
        ),
    ]
