"""Умный дом: управление через Home Assistant REST API."""

from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from typing import Any

from ..config import HomeAssistantConfig
from .registry import Skill, object_schema

log = logging.getLogger(__name__)


def _ha_request(
    config: HomeAssistantConfig,
    method: str,
    endpoint: str,
    data: dict | None = None,
) -> dict | list | None:
    """Запрос к Home Assistant REST API."""
    url = f"{config.url.rstrip('/')}/api{endpoint}"
    headers = {
        "Authorization": f"Bearer {config.token}",
        "Content-Type": "application/json",
    }
    body = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw)
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")[:200]
        log.warning("HA API %s %s: HTTP %s — %s", method, endpoint, e.code, error_body)
        return None
    except Exception as exc:
        log.warning("HA API ошибка: %s", exc)
        return None


def ha_toggle(config: HomeAssistantConfig, entity_id: str) -> str:
    """Переключает состояние entity (вкл/выкл)."""
    result = _ha_request(config, "POST", f"/services/homeassistant/toggle", {
        "entity_id": entity_id,
    })
    if result is not None:
        return f"Переключил {entity_id}, сэр."
    return f"Не удалось переключить {entity_id}, сэр. Проверьте токен и URL, сэр."


def ha_turn_on(config: HomeAssistantConfig, entity_id: str) -> str:
    """Включает entity."""
    result = _ha_request(config, "POST", f"/services/homeassistant/turn_on", {
        "entity_id": entity_id,
    })
    if result is not None:
        return f"Включил {entity_id}, сэр."
    return f"Не удалось включить {entity_id}, сэр."


def ha_turn_off(config: HomeAssistantConfig, entity_id: str) -> str:
    """Выключает entity."""
    result = _ha_request(config, "POST", f"/services/homeassistant/turn_off", {
        "entity_id": entity_id,
    })
    if result is not None:
        return f"Выключил {entity_id}, сэр."
    return f"Не удалось выключить {entity_id}, сэр."


def ha_state(config: HomeAssistantConfig, entity_id: str) -> str:
    """Получает текущее состояние entity."""
    result = _ha_request(config, "GET", f"/states/{entity_id}")
    if isinstance(result, dict):
        state = result.get("state", "unknown")
        attrs = result.get("attributes", {})
        friendly = attrs.get("friendly_name", entity_id)
        # Дополнительные полезные атрибуты
        extras = []
        for key in ("brightness", "color_temp", "temperature", "humidity", "unit_of_measurement"):
            if key in attrs:
                extras.append(f"{key}: {attrs[key]}")
        extra_str = f" ({', '.join(extras)})" if extras else ""
        return f"{friendly}: {state}{extra_str}, сэр."
    return f"Не удалось получить состояние {entity_id}, сэр."


def ha_list(config: HomeAssistantConfig, domain: str = "") -> str:
    """Показывает список entities, опционально отфильтрованный по домену."""
    result = _ha_request(config, "GET", "/states")
    if not isinstance(result, list):
        return "Не удалось получить список устройств, сэр. Проверьте подключение к Home Assistant, сэр."
    entities = result
    if domain:
        entities = [e for e in result if e.get("entity_id", "").startswith(f"{domain}.")]
    if not entities:
        return f"Устройства не найдены{f' (домен {domain})' if domain else ''}, сэр."
    lines = []
    for e in entities[:30]:
        eid = e.get("entity_id", "")
        state = e.get("state", "?")
        attrs = e.get("attributes", {})
        name = attrs.get("friendly_name", eid)
        lines.append(f"  {name}: {state} ({eid})")
    total = len(entities)
    shown = len(lines)
    suffix = f" (показано {shown} из {total})" if total > shown else ""
    return f"Устройства{suffix}:\n" + "\n".join(lines)


def ha_call_service(
    config: HomeAssistantConfig,
    domain: str,
    service: str,
    entity_id: str = "",
    **kwargs: Any,
) -> str:
    """Вызывает произвольный сервис Home Assistant."""
    data: dict[str, Any] = {}
    if entity_id:
        data["entity_id"] = entity_id
    data.update(kwargs)
    result = _ha_request(config, "POST", f"/services/{domain}/{service}", data)
    if result is not None:
        return f"Сервис {domain}.{service} вызван, сэр."
    return f"Не удалось вызвать {domain}.{service}, сэр."


def build_skills(config: HomeAssistantConfig) -> list[Skill]:
    """Создаёт навыки умного дома."""
    return [
        Skill(
            name="ha_toggle",
            description="Переключить устройство (вкл/выкл).",
            parameters=object_schema(
                {"entity_id": {"type": "string", "description": "Entity ID (light.bedroom, switch.lamp)"}},
                required=["entity_id"],
            ),
            handler=lambda entity_id: ha_toggle(config, entity_id),
        ),
        Skill(
            name="ha_turn_on",
            description="Включить устройство.",
            parameters=object_schema(
                {"entity_id": {"type": "string", "description": "Entity ID"}},
                required=["entity_id"],
            ),
            handler=lambda entity_id: ha_turn_on(config, entity_id),
        ),
        Skill(
            name="ha_turn_off",
            description="Выключить устройство.",
            parameters=object_schema(
                {"entity_id": {"type": "string", "description": "Entity ID"}},
                required=["entity_id"],
            ),
            handler=lambda entity_id: ha_turn_off(config, entity_id),
        ),
        Skill(
            name="ha_state",
            description="Узнать состояние устройства.",
            parameters=object_schema(
                {"entity_id": {"type": "string", "description": "Entity ID"}},
                required=["entity_id"],
            ),
            handler=lambda entity_id: ha_state(config, entity_id),
        ),
        Skill(
            name="ha_list",
            description="Показать список устройств (опционально по домену: light, switch, sensor).",
            parameters=object_schema(
                {"domain": {"type": "string", "description": "Домен (light, switch, sensor и т.д.)"}}
            ),
            handler=lambda domain="": ha_list(config, domain),
        ),
        Skill(
            name="ha_call_service",
            description="Вызвать произвольный сервис Home Assistant.",
            parameters=object_schema(
                {
                    "domain": {"type": "string", "description": "Домен сервиса (light, climate, ...)"},
                    "service": {"type": "string", "description": "Имя сервиса (turn_on, set_temperature, ...)"},
                    "entity_id": {"type": "string", "description": "Entity ID (необязательно)"},
                },
                required=["domain", "service"],
            ),
            handler=lambda domain, service, entity_id="", **kw: ha_call_service(config, domain, service, entity_id, **kw),
        ),
    ]
