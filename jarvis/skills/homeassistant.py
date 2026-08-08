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


# ── Климат-контроль ─────────────────────────────────────────────────


def _ha_set_temperature_impl(
    config: HomeAssistantConfig,
    entity_id: str,
    temperature: float | None = None,
    hvac_mode: str = "",
) -> str:
    """Устанавливает температуру и/или режим климат-контроля."""
    data: dict[str, Any] = {"entity_id": entity_id}
    parts: list[str] = []
    if temperature is not None:
        data["temperature"] = float(temperature)
        parts.append(f"температура {temperature}°C")
    if hvac_mode:
        _MODES = {
            "auto": "auto", "heat": "heat", "cool": "cool",
            "off": "off", "dry": "dry", "fan_only": "fan_only",
            "heat_cool": "heat_cool",
            "обогрев": "heat", "охлаждение": "cool", "авто": "auto",
            "выкл": "off", "осушение": "dry", "вентиляция": "fan_only",
        }
        mode = _MODES.get(hvac_mode.lower(), hvac_mode.lower())
        data["hvac_mode"] = mode
        parts.append(f"режим {hvac_mode}")
    if not parts:
        return "Укажите температуру и/или режим, сэр."
    result = _ha_request(config, "POST", "/services/climate/set_temperature", data)
    if result is not None:
        return f"Климат {entity_id}: {', '.join(parts)}, сэр."
    # Fallback: попробовать через set_hvac_mode
    if hvac_mode:
        result2 = _ha_request(config, "POST", "/services/climate/set_hvac_mode", {
            "entity_id": entity_id, "hvac_mode": data["hvac_mode"],
        })
        if result2 is not None:
            return f"Режим климат {entity_id}: {hvac_mode}, сэр."
    return f"Не удалось настроить климат {entity_id}, сэр."


# ── Сцены ───────────────────────────────────────────────────────────


def _ha_list_scenes_impl(config: HomeAssistantConfig) -> str:
    """Показывает доступные сцены."""
    result = _ha_request(config, "GET", "/states")
    if not isinstance(result, list):
        return "Не удалось получить список сцен, сэр."
    scenes = [e for e in result if e.get("entity_id", "").startswith("scene.")]
    if not scenes:
        return "Сцены не найдены, сэр."
    lines = []
    for s in scenes:
        eid = s["entity_id"]
        name = s.get("attributes", {}).get("friendly_name", eid)
        lines.append(f"  {name} ({eid})")
    return f"Сцены ({len(scenes)}):\n" + "\n".join(lines) + "\n, сэр."


def _ha_activate_scene_impl(config: HomeAssistantConfig, entity_id: str) -> str:
    """Активирует сцену."""
    result = _ha_request(config, "POST", "/services/scene/turn_on", {
        "entity_id": entity_id,
    })
    if result is not None:
        return f"Сцена {entity_id} активирована, сэр."
    return f"Не удалось активировать сцену {entity_id}, сэр."


# ── Комнаты / Области ────────────────────────────────────────────────


def _ha_list_areas_impl(config: HomeAssistantConfig) -> str:
    """Показывает области/комнаты Home Assistant."""
    result = _ha_request(config, "GET", "/areas")
    if not isinstance(result, list):
        return "Не удалось получить список областей, сэр."
    if not result:
        return "Области не найдены, сэр."
    lines = []
    for area in result:
        aid = area.get("id", "?")
        name = area.get("name", aid)
        lines.append(f"  {name} (id: {aid})")
    return f"Области ({len(result)}):\n" + "\n".join(lines) + "\n, сэр."


def _ha_area_control_impl(
    config: HomeAssistantConfig,
    area_name: str,
    action: str = "toggle",
    domain: str = "",
) -> str:
    """Управляет всеми устройствами в области/комнате.

    Args:
        area_name: Название области.
        action: toggle | turn_on | turn_off.
        domain: Опциональный фильтр домена (light, switch, ...).
    """
    # Получаем ID области по имени
    areas = _ha_request(config, "GET", "/areas")
    if not isinstance(areas, list):
        return "Не удалось получить области, сэр."
    area_id = None
    for a in areas:
        if a.get("name", "").lower() == area_name.lower():
            area_id = a.get("id")
            break
    if not area_id:
        available = ", ".join(a.get("name", "?") for a in areas[:10])
        return f"Область '{area_name}' не найдена, сэр. Доступные: {available}."

    # Получаем устройства в области
    devices = _ha_request(config, "GET", f"/areas/{area_id}/devices")
    if not isinstance(devices, list):
        return "Не удалось получить устройства области, сэр."
    if not devices:
        return f"В области '{area_name}' нет устройств, сэр."

    # Собираем entity_id устройств
    entity_ids: list[str] = []
    for dev in devices:
        dev_id = dev.get("id", "")
        entities = _ha_request(config, "GET", f"/devices/{dev_id}/entities")
        if isinstance(entities, list):
            for ent in entities:
                eid = ent.get("entity_id", "")
                # Пропускаем нерегулируемые типы
                ent_domain = eid.split(".")[0] if "." in eid else ""
                skip_domains = ("sensor", "binary_sensor", "automation", "script",
                                "camera", "update", "number", "input_",
                                "person", "zone", "sun", "weather")
                if any(ent_domain.startswith(d) for d in skip_domains):
                    continue
                if domain and ent_domain != domain:
                    continue
                entity_ids.append(eid)

    if not entity_ids:
        return f"В области '{area_name}' нет управляемых устройств, сэр."

    # Вызываем действие
    result = _ha_request(config, "POST", f"/services/homeassistant/{action}", {
        "entity_id": entity_ids,
    })
    if result is not None:
        action_ru = {"toggle": "переключены", "turn_on": "включены", "turn_off": "выключены"}.get(action, action)
        domain_info = f" ({domain})" if domain else ""
        return f"В '{area_name}'{domain_info} {action_ru} {len(entity_ids)} устройств, сэр."
    return f"Не удалось выполнить {action} в '{area_name}', сэр."


# ── Медиаплеер ───────────────────────────────────────────────────────


def _ha_media_control_impl(
    config: HomeAssistantConfig,
    entity_id: str,
    action: str = "play",
    volume_level: float | None = None,
    media_content_id: str = "",
    media_content_type: str = "",
) -> str:
    """Управляет медиаплеером: play/pause/stop, громкость, источник."""
    _ACTIONS = {
        "play": "media_play", "pause": "media_pause",
        "stop": "media_stop", "next": "media_next_track",
        "prev": "media_previous_track", "mute": "volume_mute",
        "play_pause": "media_play_pause",
        "воспроизвести": "media_play", "пауза": "media_pause",
        "стоп": "media_stop", "следующий": "media_next_track",
        "предыдущий": "media_previous_track", "муть": "volume_mute",
    }
    service = _ACTIONS.get(action.lower(), action.lower())

    # Громкость
    if volume_level is not None and action.lower() in ("mute", "муть"):
        result = _ha_request(config, "POST", "/services/media_player/volume_mute", {
            "entity_id": entity_id, "is_volume_muted": True,
        })
        if result is not None:
            return f"Медиаплеер {entity_id} заглушён, сэр."
        return f"Не удалось заглушить {entity_id}, сэр."

    if volume_level is not None:
        vol = max(0.0, min(1.0, float(volume_level) / 100.0))
        result = _ha_request(config, "POST", "/services/media_player/volume_set", {
            "entity_id": entity_id, "volume_level": vol,
        })
        if result is not None:
            return f"Громкость {entity_id}: {volume_level}%, сэр."
        return f"Не удалось установить громкость {entity_id}, сэр."

    # Воспроизведение по URL/источнику
    if media_content_id:
        data: dict[str, Any] = {"entity_id": entity_id, "media_content_id": media_content_id}
        if media_content_type:
            data["media_content_type"] = media_content_type
        result = _ha_request(config, "POST", "/services/media_player/play_media", data)
        if result is not None:
            return f"Воспроизвожу на {entity_id}, сэр."
        return f"Не удалось воспроизвести на {entity_id}, сэр."

    # Обычное действие (play/pause/next/...)
    result = _ha_request(config, "POST", f"/services/media_player/{service}", {
        "entity_id": entity_id,
    })
    if result is not None:
        action_ru = {"media_play": "Воспроизведение", "media_pause": "Пауза",
                     "media_stop": "Остановка", "media_next_track": "Следующий трек",
                     "media_previous_track": "Предыдущий трек", "media_play_pause": "Пауза/воспроизведение"}
        return f"{action_ru.get(service, action)} на {entity_id}, сэр."
    return f"Не удалось выполнить {action} на {entity_id}, сэр."


# ── Сенсорный дашборд ────────────────────────────────────────────────


def _ha_sensor_dashboard_impl(
    config: HomeAssistantConfig,
    sensor_type: str = "",
) -> str:
    """Быстрый обзор сенсоров: температура, влажность, энергия и т.д."""
    result = _ha_request(config, "GET", "/states")
    if not isinstance(result, list):
        return "Не удалось получить данные сенсоров, сэр."

    _CATEGORIES: dict[str, list[str]] = {
        "температура": ["temperature"],
        "влажность": ["humidity"],
        "энергия": ["energy", "power", "voltage", "current"],
        "погода": ["temperature", "humidity", "pressure", "wind_speed", "precipitation"],
    }
    filter_words = []
    if sensor_type:
        filter_words = _CATEGORIES.get(sensor_type.lower(), [sensor_type.lower()])

    lines: list[str] = []
    for e in result:
        eid = e.get("entity_id", "")
        if not eid.startswith("sensor."):
            continue
        attrs = e.get("attributes", {})
        state = e.get("state", "?")
        unit = attrs.get("unit_of_measurement", "")
        name = attrs.get("friendly_name", eid)

        # Фильтрация
        if filter_words:
            match = any(w in eid.lower() or w in name.lower() for w in filter_words)
            if not match:
                continue
        # Пропускаем unavailability
        if state in ("unavailable", "unknown", ""):
            continue

        lines.append(f"  {name}: {state}{unit}")
        if len(lines) >= 20:
            break

    if not lines:
        if sensor_type:
            return f"Сенсоры категории '{sensor_type}' не найдены, сэр."
        return "Активные сенсоры не найдены, сэр."
    return f"Сенсоры ({len(lines)}):\n" + "\n".join(lines) + "\n, сэр."


# ── Камеры ───────────────────────────────────────────────────────────


def _ha_camera_snapshot_impl(
    config: HomeAssistantConfig,
    entity_id: str,
    save_path: str = "",
) -> str:
    """Делает снимок с камеры и сохраняет в файл."""
    from pathlib import Path as _Path

    if not save_path:
        from datetime import datetime
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        save_path = str(_Path.home() / "Pictures" / "Jarvis" / f"ha-camera-{stamp}.jpg")

    # Вызываем сервис camera.snapshot
    result = _ha_request(config, "POST", "/services/camera/snapshot", {
        "entity_id": entity_id,
        "filename": save_path,
    })
    if result is not None:
        return f"Снимок камеры {entity_id} сохранён: {save_path}, сэр."
    return f"Не удалось сделать снимок {entity_id}, сэр."


def _ha_list_cameras_impl(config: HomeAssistantConfig) -> str:
    """Показывает все камеры."""
    result = _ha_request(config, "GET", "/states")
    if not isinstance(result, list):
        return "Не удалось получить список камер, сэр."
    cameras = [e for e in result if e.get("entity_id", "").startswith("camera.")]
    if not cameras:
        return "Камеры не найдены, сэр."
    lines = []
    for c in cameras:
        eid = c["entity_id"]
        name = c.get("attributes", {}).get("friendly_name", eid)
        state = c.get("state", "?")
        lines.append(f"  {name}: {state} ({eid})")
    return f"Камеры ({len(cameras)}):\n" + "\n".join(lines) + "\n, сэр."


# ── История ──────────────────────────────────────────────────────────


def _ha_history_impl(
    config: HomeAssistantConfig,
    entity_id: str,
    hours: float = 1.0,
) -> str:
    """Получает историю состояний entity за последние N часов."""
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    start = (now - timedelta(hours=hours)).isoformat()
    url = f"/history/period/{start}?filter_entity_id={entity_id}"
    result = _ha_request(config, "GET", url)
    if not isinstance(result, list) or not result:
        return f"История {entity_id} за последние {hours}ч не найдена, сэр."

    lines = [f"История {entity_id} (последние {hours}ч):"]
    for state_entry in result[0][:15]:  # первое состояние = нужный entity
        ts = state_entry.get("last_changed", "?")[:16]
        st = state_entry.get("state", "?")
        attrs = state_entry.get("attributes", {})
        name = attrs.get("friendly_name", entity_id)
        unit = attrs.get("unit_of_measurement", "")
        lines.append(f"  {ts} → {st}{unit}")

    if len(lines) == 1:
        return f"Нет записей в истории для {entity_id}, сэр."
    return "\n".join(lines) + "\n, сэр."


def _ha_entity_search_impl(config: HomeAssistantConfig, query: str) -> str:
    """Ищет entity по имени или ID (похожий поиск)."""
    result = _ha_request(config, "GET", "/states")
    if not isinstance(result, list):
        return "Не удалось выполнить поиск, сэр."
    q = query.lower()
    matches: list[str] = []
    for e in result:
        eid = e.get("entity_id", "")
        name = e.get("attributes", {}).get("friendly_name", "")
        state = e.get("state", "?")
        if q in eid.lower() or q in name.lower():
            matches.append(f"  {name}: {state} ({eid})")
    if not matches:
        return f"По запросу '{query}' ничего не найдено, сэр."
    shown = min(len(matches), 15)
    suffix = f" (показано {shown} из {len(matches)})" if len(matches) > shown else ""
    return f"Найдено{suffix}:\n" + "\n".join(matches[:15]) + "\n, сэр."


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
        # ── Климат-контроль ──
        Skill(
            name="ha_set_temperature",
            description=(
                "Установить температуру и/или режим климат-контроля (кондиционер, термостат). "
                "Режимы: auto, heat, cool, off, dry, fan_only, тепло, холод."
            ),
            parameters=object_schema(
                {
                    "entity_id": {"type": "string", "description": "Entity ID климат (climate.living_room)"},
                    "temperature": {"type": "number", "description": "Температура в °C (необязательно)"},
                    "hvac_mode": {"type": "string", "description": "Режим: heat/cool/auto/off/dry/fan_only/обогрев/охлаждение (необязательно)"},
                },
                required=["entity_id"],
            ),
            handler=lambda entity_id, temperature=None, hvac_mode="": _ha_set_temperature_impl(
                config, entity_id, temperature, hvac_mode,
            ),
        ),
        # ── Сцены ──
        Skill(
            name="ha_list_scenes",
            description="Показать все доступные сцены Home Assistant.",
            parameters=object_schema({}),
            handler=lambda: _ha_list_scenes_impl(config),
        ),
        Skill(
            name="ha_activate_scene",
            description="Активировать сцену (набор настроек устройств).",
            parameters=object_schema(
                {"entity_id": {"type": "string", "description": "Entity ID сцены (scene.movie_night)"}},
                required=["entity_id"],
            ),
            handler=lambda entity_id: _ha_activate_scene_impl(config, entity_id),
        ),
        # ── Комнаты / Области ──
        Skill(
            name="ha_list_areas",
            description="Показать все комнаты/области в Home Assistant.",
            parameters=object_schema({}),
            handler=lambda: _ha_list_areas_impl(config),
        ),
        Skill(
            name="ha_area_control",
            description=(
                "Управление всеми устройствами в комнате/области. "
                "Можно включить/выключить/переключить все устройства комнаты."
            ),
            parameters=object_schema(
                {
                    "area_name": {"type": "string", "description": "Название комнаты (Спальня, Кухня)"},
                    "action": {"type": "string", "description": "Действие: toggle/turn_on/turn_off (по умолчанию toggle)"},
                    "domain": {"type": "string", "description": "Фильтр домена: light/switch/... (необязательно)"},
                },
                required=["area_name"],
            ),
            handler=lambda area_name, action="toggle", domain="": _ha_area_control_impl(
                config, area_name, action, domain,
            ),
        ),
        # ── Медиаплеер ──
        Skill(
            name="ha_media_control",
            description=(
                "Управление медиаплеером: play/pause/stop/next/prev, громкость. "
                "Поддерживает русские команды: пауза, стоп, следующий."
            ),
            parameters=object_schema(
                {
                    "entity_id": {"type": "string", "description": "Entity ID медиаплеера"},
                    "action": {"type": "string", "description": "Действие: play/pause/stop/next/prev/mute/play_pause"},
                    "volume_level": {"type": "number", "description": "Громкость 0-100% (необязательно)"},
                    "media_content_id": {"type": "string", "description": "URL или ID контента для воспроизведения (необязательно)"},
                    "media_content_type": {"type": "string", "description": "Тип контента: music/video (необязательно)"},
                },
                required=["entity_id"],
            ),
            handler=lambda entity_id, action="play", volume_level=None, media_content_id="", media_content_type="": _ha_media_control_impl(
                config, entity_id, action, volume_level, media_content_id, media_content_type,
            ),
        ),
        # ── Сенсоры ──
        Skill(
            name="ha_sensor_dashboard",
            description=(
                "Быстрый обзор сенсоров. Категории: температура, влажность, энергия, погода. "
                "Без категории — все активные сенсоры."
            ),
            parameters=object_schema(
                {"sensor_type": {"type": "string", "description": "Категория: температура/влажность/энергия/погода (необязательно)"}}
            ),
            handler=lambda sensor_type="": _ha_sensor_dashboard_impl(config, sensor_type),
        ),
        # ── Камеры ──
        Skill(
            name="ha_list_cameras",
            description="Показать все камеры Home Assistant.",
            parameters=object_schema({}),
            handler=lambda: _ha_list_cameras_impl(config),
        ),
        Skill(
            name="ha_camera_snapshot",
            description="Сделать снимок с камеры и сохранить в файл.",
            parameters=object_schema(
                {
                    "entity_id": {"type": "string", "description": "Entity ID камеры (camera.front_door)"},
                    "save_path": {"type": "string", "description": "Путь сохранения (необязательно, по умолчанию ~/Pictures/Jarvis/)"},
                },
                required=["entity_id"],
            ),
            handler=lambda entity_id, save_path="": _ha_camera_snapshot_impl(config, entity_id, save_path),
        ),
        # ── История ──
        Skill(
            name="ha_history",
            description="Показать историю состояний устройства за последние N часов.",
            parameters=object_schema(
                {
                    "entity_id": {"type": "string", "description": "Entity ID"},
                    "hours": {"type": "number", "description": "Количество часов (по умолчанию 1)"},
                },
                required=["entity_id"],
            ),
            handler=lambda entity_id, hours=1.0: _ha_history_impl(config, entity_id, hours),
        ),
        # ── Поиск ──
        Skill(
            name="ha_entity_search",
            description="Найти устройство по имени или ID (похожий поиск).",
            parameters=object_schema(
                {"query": {"type": "string", "description": "Поисковый запрос (имя или часть entity_id)"}},
                required=["query"],
            ),
            handler=lambda query: _ha_entity_search_impl(config, query),
        ),
    ]
