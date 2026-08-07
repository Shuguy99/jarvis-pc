"""Погода-оповещения: прогноз с рекомендацией."""

from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request

from .registry import Skill, object_schema

log = logging.getLogger(__name__)


def weather_alert(city: str = "Moscow") -> str:
    try:
        url = f"https://wttr.in/{urllib.parse.quote(city)}?format=j1"
        req = urllib.request.Request(url, headers={"User-Agent": "Jarvis/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        lines = []
        for i, label in enumerate(["Сегодня", "Завтра"]):
            if i >= len(data.get("weather", [])):
                break
            day = data["weather"][i]
            hourly = day.get("hourly", [{}])
            desc_r = hourly[0].get("lang_ru", [{}])[0].get("value", "") if hourly else ""
            desc_e = hourly[0].get("weatherDesc", [{}])[0].get("value", "") if hourly else ""
            desc = desc_r or desc_e
            tmin = day["mintempC"]
            tmax = day["maxtempC"]
            rain = int(hourly[0].get("chanceofrain", "0")) if hourly else 0
            wind = int(hourly[0].get("windspeedKmph", "0")) if hourly else 0
            line = f"{label}: {desc}, {tmin}..{tmax} C, ветер {wind} км/ч, дождь {rain}%"
            if rain > 50:
                line += " - возьмите зонт!"
            lines.append(line)
        return chr(10).join(lines) + chr(10) + "Сэр."
    except Exception as exc:
        return f"Ошибка: {exc}, сэр."


def build_skills() -> list[Skill]:
    return [
        Skill(name="weather_alert",
              description="Прогноз на сегодня и завтра с рекомендацией по зонту.",
              parameters=object_schema({"city": {"type": "string", "description": "Город"}}),
              handler=lambda city="Moscow": weather_alert(city)),
    ]
