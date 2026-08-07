"""Умный дом: управление через Home Assistant REST API."""

from __future__ import annotations

import json
import logging
import urllib.error
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


# ── Новые навыки ─────────────────────────────────────────────────────────


def _ha_list_devices_impl(config: HomeAssistantConfig) -> str:
    """Получает список всех устройств через /api/devices."""
    result = _ha_request(config, "GET", "/devices")
    if not isinstance(result, list):
        return "Не удалось получить список устройств, сэр. Проверьте подключение к Home Assistant, сэр."
    if not result:
        return "Устройства не найдены в Home Assistant, сэр."
    lines: list[str] = []
    for dev in result[:50]:
        dev_id = dev.get("id", "?")
        name = dev.get("name", dev_id)
        area = dev.get("area_id", "")
        model = dev.get("model", "")
        manufacturer = dev.get("manufacturer", "")
        dev_type = dev.get("type", "")
        info_parts = [name]
        if manufacturer or model:
            info_parts.append(f"{manufacturer} {model}".strip())
        if dev_type:
            info_parts.append(f"[{dev_type}]")
        lines.append(f"  {' | '.join(info_parts)} (id: {dev_id}, area: {area or '—'})")
    total = len(result)
    shown = len(lines)
    suffix = f" (показано {shown} из {total})" if total > shown else ""
    return f"Устройства Home Assistant{suffix}:\n" + "\n".join(lines) + ", сэр."


def _ha_toggle_device_impl(config: HomeAssistantConfig, entity_id: str) -> str:
    """Переключает устройство через доменный сервис toggle."""
    domain = entity_id.split(".")[0] if "." in entity_id else "homeassistant"
    # Пробуем сначала доменный toggle (light.toggle, switch.toggle и т.д.)
    result = _ha_request(config, "POST", f"/services/{domain}/toggle", {
        "entity_id": entity_id,
    })
    if result is not None:
        return f"Устройство {entity_id} переключено, сэр."
    # Fallback на homeassistant.toggle
    result = _ha_request(config, "POST", "/services/homeassistant/toggle", {
        "entity_id": entity_id,
    })
    if result is not None:
        return f"Устройство {entity_id} переключено, сэр."
    return f"Не удалось переключить устройство {entity_id}, сэр."


def _ha_set_light_impl(
    config: HomeAssistantConfig,
    entity_id: str,
    brightness: int | None = None,
    color_temp: int | None = None,
    rgb_color: list[int] | None = None,
    color_name: str | None = None,
) -> str:
    """Устанавливает яркость и/или цвет света."""
    data: dict[str, Any] = {"entity_id": entity_id}
    if brightness is not None:
        # HA brightness: 0-255
        data["brightness_pct"] = max(0, min(100, brightness))
    if color_temp is not None:
        data["color_temp"] = color_temp
    if rgb_color is not None and len(rgb_color) == 3:
        data["rgb_color"] = rgb_color
    elif color_name is not None:
        # Простая карта имён цветов → RGB
        _COLOR_MAP: dict[str, list[int]] = {
            "красный": [255, 0, 0], "red": [255, 0, 0],
            "зелёный": [0, 255, 0], "green": [0, 255, 0],
            "синий": [0, 0, 255], "blue": [0, 0, 255],
            "жёлтый": [255, 255, 0], "yellow": [255, 255, 0],
            "белый": [255, 255, 255], "white": [255, 255, 255],
            "оранжевый": [255, 165, 0], "orange": [255, 165, 0],
            "фиолетовый": [128, 0, 128], "purple": [128, 0, 128],
            "розовый": [255, 192, 203], "pink": [255, 192, 203],
            "голубой": [0, 191, 255], "cyan": [0, 255, 255],
            "тёплый": [255, 176, 59], "warm": [255, 176, 59],
            "холодный": [171, 209, 227], "cool": [171, 209, 227],
        }
        rgb = _COLOR_MAP.get(color_name.lower())
        if rgb:
            data["rgb_color"] = rgb
    result = _ha_request(config, "POST", "/services/light/turn_on", data)
    if result is not None:
        parts: list[str] = [f"Свет {entity_id} настроен"]
        if brightness is not None:
            parts.append(f"яркость {brightness}%")
        if rgb_color is not None:
            parts.append(f"RGB {rgb_color}")
        elif color_name is not None:
            parts.append(f"цвет «{color_name}»")
        if color_temp is not None:
            parts.append(f"цветовая температура {color_temp}")
        return ", ".join(parts) + ", сэр."
    return f"Не удалось настроить свет {entity_id}, сэр."


def _ha_get_state_impl(config: HomeAssistantConfig, entity_id: str) -> str:
    """Получает полный дамп состояния entity."""
    result = _ha_request(config, "GET", f"/states/{entity_id}")
    if not isinstance(result, dict):
        return f"Не удалось получить состояние {entity_id}, сэр."
    state = result.get("state", "unknown")
    attrs = result.get("attributes", {})
    ctx = result.get("context", {})
    last_changed = result.get("last_changed", "")
    last_updated = result.get("last_updated", "")
    lines = [
        f"Полное состояние {entity_id}:",
        f"  Состояние: {state}",
        f"  Последнее изменение: {last_changed}",
        f"  Последнее обновление: {last_updated}",
        f"  Контекст: {ctx.get('id', '?')} (parent_id: {ctx.get('parent_id', '—')})",
        "  Атрибуты:",
    ]
    for key, val in attrs.items():
        if isinstance(val, (dict, list)):
            val_str = json.dumps(val, ensure_ascii=False)
            if len(val_str) > 200:
                val_str = val_str[:200] + "..."
            lines.append(f"    {key}: {val_str}")
        else:
            lines.append(f"    {key}: {val}")
    return "\n".join(lines) + "\n, сэр."


def _ha_run_script_impl(config: HomeAssistantConfig, entity_id: str) -> str:
    """Запускает скрипт или автоматизацию по entity_id."""
    domain = entity_id.split(".")[0] if "." in entity_id else ""
    if domain == "script":
        result = _ha_request(config, "POST", f"/services/script/turn_on", {
            "entity_id": entity_id,
        })
    elif domain == "automation":
        result = _ha_request(config, "POST", f"/services/automation/trigger", {
            "entity_id": entity_id,
        })
    else:
        # Пытаемся запустить через homeassistant.turn_on
        result = _ha_request(config, "POST", "/services/homeassistant/turn_on", {
            "entity_id": entity_id,
        })
    if result is not None:
        domain_ru = {"script": "скрипт", "automation": "автоматизацию"}.get(domain, "сценарий")
        return f"{domain_ru.capitalize()} {entity_id} запущен, сэр."
    return f"Не удалось запустить {entity_id}, сэр."


def build_skills(config: HomeAssistantConfig) -> list[Skill]:
    """Создаёт навыки умного дома."""
    return [
        # ── Исходные навыки ──
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
        # ── Новые навыки ──
        Skill(
            name="ha_list_devices",
            description="Показать список всех устройств Home Assistant (id, тип, модель, область).",
            parameters=object_schema({}),
            handler=lambda: _ha_list_devices_impl(config),
        ),
        Skill(
            name="ha_toggle_device",
            description="Переключить устройство (свет, выключатель и т.д.) через доменный toggle.",
            parameters=object_schema(
                {"entity_id": {"type": "string", "description": "Entity ID (light.bedroom, switch.kitchen_lamp)"}},
                required=["entity_id"],
            ),
            handler=lambda entity_id: _ha_toggle_device_impl(config, entity_id),
        ),
        Skill(
            name="ha_set_light",
            description="Настроить свет: яркость (%), цветовая температура, RGB или цвет по имени.",
            parameters=object_schema(
                {
                    "entity_id": {"type": "string", "description": "Entity ID света (light.bedroom)"},
                    "brightness": {"type": "integer", "description": "Яркость в процентах 0–100 (необязательно)"},
                    "color_temp": {"type": "integer", "description": "Цветовая температура в mired (необязательно)"},
                    "rgb_color": {"type": "array", "description": "RGB цвет [r, g, b] 0–255 (необязательно)", "items": {"type": "integer"}},
                    "color_name": {"type": "string", "description": "Название цвета: красный, синий, тёплый и т.д. (необязательно)"},
                },
                required=["entity_id"],
            ),
            handler=lambda entity_id, brightness=None, color_temp=None, rgb_color=None, color_name=None: _ha_set_light_impl(
                config, entity_id, brightness, color_temp, rgb_color, color_name,
            ),
        ),
        Skill(
            name="ha_get_state",
            description="Получить полный дамп состояния entity: все атрибуты, контекст, таймстемпы.",
            parameters=object_schema(
                {"entity_id": {"type": "string", "description": "Entity ID"}},
                required=["entity_id"],
            ),
            handler=lambda entity_id: _ha_get_state_impl(config, entity_id),
        ),
        Skill(
            name="ha_run_script",
            description="Запустить скрипт или автоматизацию в Home Assistant по entity_id.",
            parameters=object_schema(
                {"entity_id": {"type": "string", "description": "Entity ID (script.goodnight, automation.welcome_home)"}},
                required=["entity_id"],
            ),
            handler=lambda entity_id: _ha_run_script_impl(config, entity_id),
        ),
    ]
