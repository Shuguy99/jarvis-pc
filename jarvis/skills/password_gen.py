"""Генератор паролей."""

from __future__ import annotations

import logging
import random
import string

from .registry import Skill, object_schema

log = logging.getLogger(__name__)


def generate(length: int = 16, upper: bool = True, digits: bool = True, symbols: bool = True) -> str:
    pool = [string.ascii_lowercase]
    if upper:
        pool.append(string.ascii_uppercase)
    if digits:
        pool.append(string.digits)
    if symbols:
        pool.append("!@#$%^&*()_+-=[]{}|;:,.<>?")
    charset = "".join(pool)
    if not charset:
        return "Нечего генерировать, сэр."
    password = "".join(random.SystemRandom().choices(charset, k=length))
    return f"Пароль: {password} (длина {length}), сэр."


def build_skills() -> list[Skill]:
    return [
        Skill(name="generate_password", description="Сгенерировать надёжный случайный пароль.",
              parameters=object_schema({
                  "length": {"type": "integer", "description": "Длина (по умолчанию 16)"},
                  "upper": {"type": "boolean", "description": "Заглавные буквы (по умолчанию true)"},
                  "digits": {"type": "boolean", "description": "Цифры (по умолчанию true)"},
                  "symbols": {"type": "boolean", "description": "Символы (по умолчанию true)"},
              }),
              handler=lambda length=16, upper=True, digits=True, symbols=True: generate(length, upper, digits, symbols)),
    ]
