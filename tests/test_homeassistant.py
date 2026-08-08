"""Тесты умного дома (Home Assistant) — без реального HA."""

from unittest.mock import patch, MagicMock

import pytest

from jarvis.config import HomeAssistantConfig
from jarvis.skills.homeassistant import (
    _ha_request,
    ha_toggle,
    ha_turn_on,
    ha_turn_off,
    ha_state,
    ha_list,
    ha_call_service,
    _ha_set_temperature_impl,
    _ha_list_scenes_impl,
    _ha_activate_scene_impl,
    _ha_list_areas_impl,
    _ha_area_control_impl,
    _ha_media_control_impl,
    _ha_sensor_dashboard_impl,
    _ha_camera_snapshot_impl,
    _ha_list_cameras_impl,
    _ha_history_impl,
    _ha_entity_search_impl,
)


cfg = HomeAssistantConfig(enabled=True, url="http://localhost:8123", token="test-token")


# ── Хелпер ───────────────────────────────────────────────────────────


def _mock_request(return_value):
    """Патчит _ha_request для возврата заданного значения."""
    return patch("jarvis.skills.homeassistant._ha_request", return_value=return_value)


# ── Базовые навыки ───────────────────────────────────────────────────


class TestBasicSkills:
    """Тесты исходных 6 навыков."""

    def test_toggle_success(self):
        with _mock_request(["ok"]):
            result = ha_toggle(cfg, "light.bedroom")
            assert "переключил" in result.lower()

    def test_toggle_failure(self):
        with _mock_request(None):
            result = ha_toggle(cfg, "light.bedroom")
            assert "Не удалось" in result

    def test_turn_on_success(self):
        with _mock_request(["ok"]):
            result = ha_turn_on(cfg, "switch.lamp")
            assert "Включил" in result

    def test_turn_off_success(self):
        with _mock_request(["ok"]):
            result = ha_turn_off(cfg, "switch.lamp")
            assert "Выключил" in result

    def test_state_success(self):
        with _mock_request({"state": "on", "attributes": {"friendly_name": "Лампа"}}):
            result = ha_state(cfg, "light.bedroom")
            assert "Лампа: on" in result

    def test_state_with_attributes(self):
        with _mock_request({
            "state": "on",
            "attributes": {"friendly_name": "Свет", "brightness": 200, "temperature": "22.5", "unit_of_measurement": "°C"},
        }):
            result = ha_state(cfg, "sensor.temp")
            assert "brightness: 200" in result
            assert "temperature: 22.5" in result

    def test_state_failure(self):
        with _mock_request(None):
            result = ha_state(cfg, "light.bedroom")
            assert "Не удалось" in result

    def test_list_all(self):
        with _mock_request([{"entity_id": "light.bedroom", "state": "on", "attributes": {"friendly_name": "Свет"}}]):
            result = ha_list(cfg)
            assert "Свет: on" in result

    def test_list_by_domain(self):
        with _mock_request([
            {"entity_id": "light.bedroom", "state": "on", "attributes": {}},
            {"entity_id": "switch.lamp", "state": "off", "attributes": {}},
        ]):
            result = ha_list(cfg, domain="light")
            assert "light.bedroom" in result
            assert "switch.lamp" not in result

    def test_list_empty(self):
        with _mock_request([]):
            result = ha_list(cfg)
            assert "не найдены" in result.lower()

    def test_list_failure(self):
        with _mock_request(None):
            result = ha_list(cfg)
            assert "Не удалось" in result

    def test_call_service_success(self):
        with _mock_request(["ok"]):
            result = ha_call_service(cfg, "light", "turn_on", entity_id="light.bedroom")
            assert "вызван" in result.lower()

    def test_call_service_failure(self):
        with _mock_request(None):
            result = ha_call_service(cfg, "light", "turn_on")
            assert "Не удалось" in result


# ── Климат-контроль ─────────────────────────────────────────────────


class TestClimate:
    """Тесты климат-контроля."""

    def test_set_temperature_only(self):
        with _mock_request(["ok"]):
            result = _ha_set_temperature_impl(cfg, "climate.living", temperature=22)
            assert "22" in result

    def test_set_hvac_mode_russian(self):
        with _mock_request(["ok"]):
            result = _ha_set_temperature_impl(cfg, "climate.living", hvac_mode="обогрев")
            assert "обогрев" in result

    def test_set_both(self):
        with _mock_request(["ok"]):
            result = _ha_set_temperature_impl(cfg, "climate.living", temperature=24, hvac_mode="cool")
            assert "24" in result
            assert "cool" in result

    def test_no_params(self):
        result = _ha_set_temperature_impl(cfg, "climate.living")
        assert "Укажите" in result

    def test_fallback_to_hvac_mode(self):
        # set_temperature fails, set_hvac_mode succeeds
        call_count = [0]
        def _side_effect(config, method, endpoint, data=None):
            call_count[0] += 1
            if call_count[0] == 1:
                return None  # set_temperature fails
            return ["ok"]  # set_hvac_mode succeeds
        with patch("jarvis.skills.homeassistant._ha_request", side_effect=_side_effect):
            result = _ha_set_temperature_impl(cfg, "climate.room", hvac_mode="heat")
            assert "режим" in result.lower()


# ── Сцены ────────────────────────────────────────────────────────────


class TestScenes:
    """Тесты сцен."""

    def test_list_scenes(self):
        with _mock_request([
            {"entity_id": "scene.movie", "attributes": {"friendly_name": "Кино"}},
            {"entity_id": "light.bedroom", "state": "on", "attributes": {}},
        ]):
            result = _ha_list_scenes_impl(cfg)
            assert "Кино" in result
            assert "light.bedroom" not in result

    def test_list_scenes_empty(self):
        with _mock_request([]):
            result = _ha_list_scenes_impl(cfg)
            assert "не найдены" in result.lower()

    def test_activate_scene(self):
        with _mock_request(["ok"]):
            result = _ha_activate_scene_impl(cfg, "scene.movie")
            assert "активирована" in result.lower()

    def test_activate_scene_failure(self):
        with _mock_request(None):
            result = _ha_activate_scene_impl(cfg, "scene.movie")
            assert "Не удалось" in result


# ── Области / Комнаты ────────────────────────────────────────────────


class TestAreas:
    """Тесты управления по комнатам."""

    def test_list_areas(self):
        with _mock_request([{"id": "a1", "name": "Спальня"}, {"id": "a2", "name": "Кухня"}]):
            result = _ha_list_areas_impl(cfg)
            assert "Спальня" in result
            assert "Кухня" in result

    def test_list_areas_empty(self):
        with _mock_request([]):
            result = _ha_list_areas_impl(cfg)
            assert "не найдены" in result.lower()

    def test_area_control_success(self):
        call_count = [0]
        def _side_effect(config, method, endpoint, data=None):
            call_count[0] += 1
            if call_count[0] == 1:
                return [{"id": "a1", "name": "Спальня"}]
            elif call_count[0] == 2:
                return [{"id": "d1"}]
            elif call_count[0] == 3:
                return [{"entity_id": "light.bedroom"}]
            return ["ok"]
        with patch("jarvis.skills.homeassistant._ha_request", side_effect=_side_effect):
            result = _ha_area_control_impl(cfg, "Спальня")
            assert "переключены" in result.lower()

    def test_area_not_found(self):
        with _mock_request([{"id": "a1", "name": "Кухня"}]):
            result = _ha_area_control_impl(cfg, "Спальня")
            assert "не найдена" in result.lower()

    def test_area_control_with_domain_filter(self):
        call_count = [0]
        def _side_effect(config, method, endpoint, data=None):
            call_count[0] += 1
            if call_count[0] == 1:
                return [{"id": "a1", "name": "Гостиная"}]
            elif call_count[0] == 2:
                return [{"id": "d1"}]
            elif call_count[0] == 3:
                # light проходит, sensor фильтруется
                return [
                    {"entity_id": "light.sofa"},
                    {"entity_id": "sensor.temp"},
                ]
            return ["ok"]
        with patch("jarvis.skills.homeassistant._ha_request", side_effect=_side_effect):
            result = _ha_area_control_impl(cfg, "Гостиная", domain="light")
            assert "1 устройств" in result


# ── Медиаплеер ───────────────────────────────────────────────────────


class TestMedia:
    """Тесты медиаплеера."""

    def test_play(self):
        with _mock_request(["ok"]):
            result = _ha_media_control_impl(cfg, "media_player.tv", action="play")
            assert "Воспроизведение" in result

    def test_pause_russian(self):
        with _mock_request(["ok"]):
            result = _ha_media_control_impl(cfg, "media_player.tv", action="пауза")
            assert "Пауза" in result

    def test_set_volume(self):
        with _mock_request(["ok"]):
            result = _ha_media_control_impl(cfg, "media_player.tv", volume_level=50)
            assert "50%" in result

    def test_volume_clamped(self):
        with _mock_request(["ok"]) as m:
            _ha_media_control_impl(cfg, "media.player", volume_level=200)
            # Проверяем что volume_level был обрезан до 1.0
            call_args = m.call_args
            data = call_args[0][3] if len(call_args[0]) > 3 else call_args[1].get("data", {})
            vol = data.get("volume_level", 0)
            assert vol <= 1.0

    def test_play_media_url(self):
        with _mock_request(["ok"]):
            result = _ha_media_control_impl(cfg, "media_player.tv", media_content_id="http://radio.com/stream")
            assert "Воспроизвожу" in result

    def test_next_track(self):
        with _mock_request(["ok"]):
            result = _ha_media_control_impl(cfg, "media.player", action="next")
            assert "Следующий" in result

    def test_failure(self):
        with _mock_request(None):
            result = _ha_media_control_impl(cfg, "media.player", action="play")
            assert "Не удалось" in result


# ── Сенсоры ──────────────────────────────────────────────────────────


class TestSensors:
    """Тесты сенсорного дашборда."""

    def test_all_sensors(self):
        states = [
            {"entity_id": "sensor.temp", "state": "22.5", "attributes": {"friendly_name": "Температура", "unit_of_measurement": "°C"}},
            {"entity_id": "sensor.hum", "state": "45", "attributes": {"friendly_name": "Влажность", "unit_of_measurement": "%"}},
            {"entity_id": "sensor.bad", "state": "unavailable", "attributes": {"friendly_name": "Сломан"}},
            {"entity_id": "light.bedroom", "state": "on", "attributes": {}},
        ]
        with _mock_request(states):
            result = _ha_sensor_dashboard_impl(cfg)
            assert "Температура: 22.5°C" in result
            assert "Влажность: 45%" in result
            assert "Сломан" not in result  # unavailable отфильтрован

    def test_filter_temperature(self):
        states = [
            {"entity_id": "sensor.temperature_living", "state": "22", "attributes": {"friendly_name": "Температура гостиной", "unit_of_measurement": "°C"}},
            {"entity_id": "sensor.humidity_living", "state": "50", "attributes": {"friendly_name": "Влажность", "unit_of_measurement": "%"}},
        ]
        with _mock_request(states):
            result = _ha_sensor_dashboard_impl(cfg, sensor_type="температура")
            assert "Температура" in result
            assert "Влажность" not in result

    def test_empty(self):
        with _mock_request([]):
            result = _ha_sensor_dashboard_impl(cfg)
            assert "не найдены" in result.lower()

    def test_no_match_category(self):
        states = [
            {"entity_id": "sensor.humidity", "state": "50", "attributes": {"friendly_name": "Влажность"}},
        ]
        with _mock_request(states):
            result = _ha_sensor_dashboard_impl(cfg, sensor_type="энергия")
            assert "не найдены" in result.lower()


# ── Камеры ───────────────────────────────────────────────────────────


class TestCameras:
    """Тесты камер."""

    def test_list_cameras(self):
        with _mock_request([
            {"entity_id": "camera.front", "state": "idle", "attributes": {"friendly_name": "Входная дверь"}},
            {"entity_id": "light.bedroom", "state": "on", "attributes": {}},
        ]):
            result = _ha_list_cameras_impl(cfg)
            assert "Входная дверь" in result
            assert "light.bedroom" not in result

    def test_list_empty(self):
        with _mock_request([]):
            result = _ha_list_cameras_impl(cfg)
            assert "не найдены" in result.lower()

    def test_snapshot_success(self):
        with _mock_request(["ok"]):
            result = _ha_camera_snapshot_impl(cfg, "camera.front")
            assert "сохранён" in result.lower()

    def test_snapshot_failure(self):
        with _mock_request(None):
            result = _ha_camera_snapshot_impl(cfg, "camera.front")
            assert "Не удалось" in result


# ── История ──────────────────────────────────────────────────────────


class TestHistory:
    """Тесты истории."""

    def test_history_success(self):
        history_data = [[
            {"last_changed": "2025-01-15T10:00:00", "state": "on", "attributes": {"friendly_name": "Свет", "unit_of_measurement": ""}},
            {"last_changed": "2025-01-15T09:00:00", "state": "off", "attributes": {"friendly_name": "Свет", "unit_of_measurement": ""}},
        ]]
        with _mock_request(history_data):
            result = _ha_history_impl(cfg, "light.bedroom", hours=2)
            assert "История" in result
            assert "→ on" in result
            assert "→ off" in result

    def test_history_empty(self):
        with _mock_request([]):
            result = _ha_history_impl(cfg, "light.bedroom")
            assert "не найдена" in result.lower()

    def test_history_no_records(self):
        with _mock_request([[]]):  # пустой список состояний
            result = _ha_history_impl(cfg, "light.bedroom")
            assert "Нет записей" in result


# ── Поиск ────────────────────────────────────────────────────────────


class TestSearch:
    """Тесты поиска устройств."""

    def test_search_by_name(self):
        with _mock_request([
            {"entity_id": "light.bedroom", "state": "on", "attributes": {"friendly_name": "Свет спальни"}},
            {"entity_id": "sensor.temp", "state": "22", "attributes": {"friendly_name": "Температура"}},
        ]):
            result = _ha_entity_search_impl(cfg, "свет")
            assert "Свет спальни" in result
            assert "Температура" not in result

    def test_search_by_entity_id(self):
        with _mock_request([
            {"entity_id": "switch.kitchen_lamp", "state": "off", "attributes": {"friendly_name": "Лампа"}},
        ]):
            result = _ha_entity_search_impl(cfg, "kitchen")
            assert "kitchen" in result

    def test_search_no_match(self):
        with _mock_request([{"entity_id": "light.bedroom", "state": "on", "attributes": {"friendly_name": "Свет"}}]):
            result = _ha_entity_search_impl(cfg, "кошка")
            assert "ничего не найдено" in result.lower()

    def test_search_failure(self):
        with _mock_request(None):
            result = _ha_entity_search_impl(cfg, "test")
            assert "Не удалось" in result


# ── build_skills ─────────────────────────────────────────────────────


class TestBuildSkills:
    """Тесты регистрации навыков."""

    def test_skill_count(self):
        from jarvis.skills.homeassistant import build_skills
        skills = build_skills(cfg)
        names = {s.name for s in skills}
        assert len(skills) == 22
        # Проверяем наличие всех новых навыков
        for name in (
            "ha_toggle", "ha_turn_on", "ha_turn_off", "ha_state", "ha_list",
            "ha_call_service", "ha_list_devices", "ha_toggle_device", "ha_set_light",
            "ha_get_state", "ha_run_script",
            "ha_set_temperature", "ha_list_scenes", "ha_activate_scene",
            "ha_list_areas", "ha_area_control", "ha_media_control",
            "ha_sensor_dashboard", "ha_list_cameras", "ha_camera_snapshot",
            "ha_history", "ha_entity_search",
        ):
            assert name in names, f"Missing skill: {name}"

    def test_all_skills_have_descriptions(self):
        from jarvis.skills.homeassistant import build_skills
        skills = build_skills(cfg)
        for s in skills:
            assert s.description, f"Skill {s.name} has no description"
