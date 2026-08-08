"""Навыки погоды: текущая погода, прогноз, через wttr.in или OpenWeatherMap."""

from __future__ import annotations

from datetime import datetime
import json
import logging
import urllib.request
import urllib.parse
from typing import Any

from ..config import WeatherConfig
from ..rate_limit import rate_limiter
from .registry import Skill, object_schema

log = logging.getLogger(__name__)


# ROSCOMPASS направления по градусам
_WIND_ROSE = [
    (0, "северный"), (45, "северо-восточный"), (90, "восточный"),
    (135, "юго-восточный"), (180, "южный"), (225, "юго-западный"),
    (270, "западный"), (315, "северо-западный"), (360, "северный"),
]


def _wind_direction(deg: float) -> str:
    """Возвращает название направления ветра по градусам."""
    deg = deg % 360
    best = _WIND_ROSE[0]
    for entry in _WIND_ROSE:
        if abs(deg - entry[0]) < abs(deg - best[0]):
            best = entry
    return best[1]


def _wttr_request(location: str, format_str: str) -> str:
    """Запрос к wttr.in. Возвращает текст ответа или пустую строку."""
    rate_limiter.wait("weather")
    try:
        url = f"https://wttr.in/{urllib.parse.quote(location)}?format={format_str}&lang=ru"
        req = urllib.request.Request(url, headers={"User-Agent": "curl/7.68"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.read().decode("utf-8").strip()
    except Exception as exc:
        log.warning("wttr.in запрос не удался: %s", exc)
        return ""


def _owm_request(api_key: str, endpoint: str, params: dict[str, str]) -> dict[str, Any] | None:
    """Запрос к OpenWeatherMap API. Возвращает JSON или None."""
    rate_limiter.wait("weather")
    try:
        params["appid"] = api_key
        params["lang"] = "ru"
        qs = urllib.parse.urlencode(params)
        url = f"https://api.openweathermap.org/data/2.5/{endpoint}?{qs}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        log.warning("OWM запрос не удался: %s", exc)
        return None


def _temp_k_to_c(k: float) -> float:
    return round(k - 273.15, 1)


def _get_weather_wttr(location: str) -> str:
    """Текущая погода через wttr.in (не требует API ключа)."""
    # Формат: температура, ощущаемая, ветер, влажность, описание
    fmt = "%C+%t+%f+%w+%h+%p"
    raw = _wttr_request(location, fmt)
    if not raw:
        return f"Не удалось получить погоду для {location}, сэр."
    parts = [p.strip() for p in raw.split("+") if p.strip()]
    # parts: [описание, температура, ощущаемая, ветер, влажность, давление]
    result = f"В {location}: "
    if len(parts) >= 2:
        result += f"{parts[0].lower()}, температура {parts[1]}"
    if len(parts) >= 3:
        result += f", ощущается как {parts[2]}"
    if len(parts) >= 4:
        result += f", ветер {parts[3]}"
    if len(parts) >= 5:
        result += f", влажность {parts[4]}"
    if len(parts) >= 6:
        result += f", давление {parts[5]}"
    return result + "."


def _get_weather_owm(location: str, api_key: str) -> str:
    """Текущая погода через OpenWeatherMap."""
    data = _owm_request(api_key, "weather", {"q": location})
    if not data or data.get("cod") != 200:
        return f"Не удалось получить погоду для {location}, сэр."
    main = data.get("main", {})
    weather = data.get("weather", [{}])[0]
    wind = data.get("wind", {})
    temp = _temp_k_to_c(main.get("temp", 0))
    feels = _temp_k_to_c(main.get("feels_like", 0))
    desc = weather.get("description", "неизвестно")
    humidity = main.get("humidity", 0)
    pressure = main.get("pressure", 0)
    wind_speed = wind.get("speed", 0)
    wind_dir = _wind_direction(wind.get("deg", 0))
    return (
        f"В {location}: {desc}, температура {temp} градусов, "
        f"ощущается как {feels}, ветер {wind_dir} {wind_speed} м/с, "
        f"влажность {humidity}%, давление {pressure} гПа."
    )


def _get_forecast_owm(location: str, api_key: str) -> str:
    """Прогноз на 3 дня через OpenWeatherMap (3-hour forecast)."""
    data = _owm_request(api_key, "forecast", {"q": location, "cnt": "24"})
    if not data or data.get("cod") != "200":
        return f"Не удалось получить прогноз для {location}, сэр."
    items = data.get("list", [])
    if not items:
        return "Прогноз пуст, сэр."
    # Группируем по дням, берём середину дня (12:00-15:00)
    daily: dict[str, dict] = {}
    for item in items:
        dt_txt = item.get("dt_txt", "")
        try:
            dt = datetime.fromisoformat(dt_txt)
            day_key = dt.strftime("%d.%m")
        except (ValueError, TypeError):
            continue
        hour = dt.hour
        if hour < 6 or hour >= 21:
            continue  # пропускаем ночь
        if day_key not in daily or abs(hour - 12) < abs(daily[day_key].get("_hour", 99) - 12):
            item["_hour"] = hour
            daily[day_key] = item
    lines = [f"Прогноз для {location}:"]
    for day_key, item in list(daily.items())[:3]:
        main = item.get("main", {})
        weather = item.get("weather", [{}])[0]
        temp = _temp_k_to_c(main.get("temp", 0))
        desc = weather.get("description", "")
        lines.append(f"{day_key}: {desc}, {temp} градусов")
    if len(lines) == 1:
        return "Не удалось собрать прогноз, сэр."
    return ". ".join(lines) + "."


def get_weather(config: WeatherConfig, location: str) -> str:
    """Получает текущую погоду для указанного города.

    Если задан API ключ OpenWeatherMap — использует его, иначе — wttr.in.
    """
    if not location.strip():
        return "Укажите город, сэр."
    if config.api_key:
        return _get_weather_owm(location, config.api_key)
    return _get_weather_wttr(location)


def get_forecast(config: WeatherConfig, location: str) -> str:
    """Прогноз погоды на несколько дней.

    Требует OpenWeatherMap API ключ.
    """
    if not location.strip():
        return "Укажите город, сэр."
    if not config.api_key:
        return "Для прогноза нужен API ключ OpenWeatherMap, сэр."
    return _get_forecast_owm(location, config.api_key)


def build_skills(config: WeatherConfig) -> list[Skill]:
    """Создаёт навыки погоды."""
    return [
        Skill(
            name="get_weather",
            description=(
                "Получить текущую погоду для города. "
                "Если не указан город — используется город по умолчанию из конфига."
            ),
            parameters=object_schema(
                {
                    "location": {
                        "type": "string",
                        "description": "Название города, например 'Москва' или 'Новосибирск'",
                    },
                },
            ),
            handler=lambda location="": get_weather(config, location or config.default_city),
        ),
        Skill(
            name="get_forecast",
            description=(
                "Получить прогноз погоды на несколько дней для города. "
                "Требует настройку API ключа OpenWeatherMap."
            ),
            parameters=object_schema(
                {
                    "location": {
                        "type": "string",
                        "description": "Название города",
                    },
                },
            ),
            handler=lambda location="": get_forecast(config, location or config.default_city),
        ),
    ]
