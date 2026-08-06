"""Пример пользовательского навыка.

Скопируйте в ~/.jarvis/skills/hello.py и перезапустите Джарвиса.
После этого можно сказать: «Джарвис, поздоровайся».
"""

from jarvis.skills.registry import Skill, object_schema


def build_skills():
    return [
        Skill(
            name="hello_custom",
            description=(
                "Поприветствовать пользователя кастомным приветствием. "
                "Используй, когда просят поздороваться нестандартно."
            ),
            parameters=object_schema(
                {
                    "name": {
                        "type": "string",
                        "description": "Имя пользователя (если известно)",
                    }
                }
            ),
            handler=lambda name="": (
                f"Привет, {name}! Добро пожаловать, сэр."
                if name
                else "Привет, сэр! Я — кастомный навык."
            ),
        )
    ]
