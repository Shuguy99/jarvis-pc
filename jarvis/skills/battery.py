"""Статус батареи ноутбука."""

from __future__ import annotations

import logging

from .registry import Skill, object_schema

log = logging.getLogger(__name__)


def battery_status() -> str:
    try:
        import psutil
        bat = psutil.sensors_battery()
        if bat is None:
            return "Батарея не обнаружена, сэр."
        percent = int(bat.percent)
        plugged = "заряжается" if bat.power_plugged else "от батареи"
        if bat.secsleft >= 0:
            h, m = divmod(bat.secsleft // 60, 60)
            time_left = f", осталось {h}ч {m}мин" if h else f", осталось {m} мин"
        else:
            time_left = ""
        return f"Батарея: {percent}% ({plugged}{time_left}), сэр."
    except Exception as exc:
        return f"Ошибка: {exc}, сэр."


def build_skills() -> list[Skill]:
    return [
        Skill(name="battery_status", description="Узнать уровень заряда батареи.",
              parameters=object_schema({}), handler=battery_status),
    ]
