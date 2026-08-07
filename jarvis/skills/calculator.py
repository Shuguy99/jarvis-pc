"""Безопасный калькулятор."""

from __future__ import annotations

import logging
import math
import re

from .registry import Skill, object_schema

log = logging.getLogger(__name__)

_SAFE_NAMES = {n: getattr(math, n) for n in dir(math) if not n.startswith("_")}
_SAFE_NAMES.update({"abs": abs, "round": round, "min": min, "max": max, "sum": sum, "pow": pow, "int": int, "float": float})


def _safe_eval(expr: str) -> float:
    cleaned = expr.replace(",", ".")
    if not re.match(r"^[\d+\-*/.()\s^%a-zA-Z_]+$", cleaned):
        raise ValueError("Недопустимые символы")
    return float(eval(cleaned, {"__builtins__": {}}, _SAFE_NAMES))  # noqa: S307


def calculate(expression: str) -> str:
    try:
        result = _safe_eval(expression)
        return f"Результат: {int(result)}, сэр." if result == int(result) else f"Результат: {result:.6g}, сэр."
    except ZeroDivisionError:
        return "Деление на ноль, сэр."
    except (ValueError, SyntaxError) as exc:
        return f"Не удалось вычислить: {exc}, сэр."
    except Exception as exc:
        return f"Ошибка: {exc}, сэр."


def percentage(value: float, percent: float) -> str:
    try:
        result = value * percent / 100
        if result == int(result):
            return f"{percent}% от {value} = {int(result)}, сэр."
        return f"{percent}% от {value} = {result:.4g}, сэр."
    except Exception as exc:
        return f"Ошибка: {exc}, сэр."


def convert_temperature(value: float, from_unit: str = "C", to_unit: str = "F") -> str:
    try:
        fr, to = from_unit.upper(), to_unit.upper()
        if fr == "C" and to == "F":
            result = value * 9 / 5 + 32
        elif fr == "F" and to == "C":
            result = (value - 32) * 5 / 9
        elif fr == "C" and to == "K":
            result = value + 273.15
        elif fr == "K" and to == "C":
            result = value - 273.15
        elif fr == to:
            return f"{value}°{fr} = {value}°{to}, сэр."
        else:
            return f"Конвертация {fr} → {to} не поддерживается, сэр."
        return f"{value}°{fr} = {result:.1f}°{to}, сэр."
    except Exception as exc:
        return f"Ошибка: {exc}, сэр."


def build_skills() -> list[Skill]:
    return [
        Skill(name="calculate", description="Вычислить математическое выражение.",
              parameters=object_schema({"expression": {"type": "string", "description": "Например (2+3)*4 или 15/100*2400"}}, required=["expression"]),
              handler=lambda expression: calculate(expression)),
        Skill(name="percentage", description="Вычислить процент от числа.",
              parameters=object_schema({"value": {"type": "number", "description": "Число"}, "percent": {"type": "number", "description": "Процент"}}, required=["value", "percent"]),
              handler=lambda value, percent: percentage(float(value), float(percent))),
        Skill(name="convert_temperature", description="Конвертировать температуру (C/F/K).",
              parameters=object_schema({"value": {"type": "number", "description": "Температура"}, "from_unit": {"type": "string", "description": "C, F или K"}, "to_unit": {"type": "string", "description": "C, F или K"}}, required=["value", "from_unit", "to_unit"]),
              handler=lambda value, from_unit="C", to_unit="F": convert_temperature(float(value), from_unit, to_unit)),
    ]
