"""Конвертер единиц измерения (длина, вес, скорость, данные)."""

from __future__ import annotations

import logging

from .registry import Skill, object_schema

log = logging.getLogger(__name__)

_UNITS: dict[str, dict[str, float]] = {
    "length": {
        "mm": 0.001, "cm": 0.01, "m": 1.0, "km": 1000.0,
        "in": 0.0254, "ft": 0.3048, "yd": 0.9144, "mi": 1609.344,
    },
    "weight": {
        "mg": 0.001, "g": 1.0, "kg": 1000.0, "t": 1_000_000.0,
        "oz": 28.3495, "lb": 453.592,
    },
    "speed": {
        "m/s": 1.0, "km/h": 0.277778, "mph": 0.44704, "kn": 0.514444,
    },
    "data": {
        "b": 1, "kb": 1024, "mb": 1048576, "gb": 1073741824, "tb": 1099511627776,
    },
}


def convert(value: float, from_unit: str, to_unit: str) -> str:
    fu, tu = from_unit.lower().strip(), to_unit.lower().strip()
    for cat, units in _UNITS.items():
        if fu in units and tu in units:
            result = value * units[fu] / units[tu]
            return f"{value} {fu} = {result:.6g} {tu}, сэр."
    return f"Конвертация {fu} → {tu} не поддерживается. Доступные: длина, вес, скорость, данные, сэр."


def build_skills() -> list[Skill]:
    return [
        Skill(name="unit_convert", description="Конвертировать единицы (100 mi → km, 1 kg → lb и т.д.).",
              parameters=object_schema({
                  "value": {"type": "number", "description": "Значение"},
                  "from_unit": {"type": "string", "description": "Из какой единицы (km, mi, kg, lb, mb, gb...)"},
                  "to_unit": {"type": "string", "description": "В какую единицу"},
              }, required=["value", "from_unit", "to_unit"]),
              handler=lambda value, from_unit, to_unit: convert(float(value), from_unit, to_unit)),
    ]
