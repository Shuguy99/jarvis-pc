"""Тесты навыков Home Assistant."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from jarvis.config import HomeAssistantConfig
from jarvis.skills.homeassistant import (
    _ha_get_state_impl,
    _ha_list_devices_impl,
    _ha_run_script_impl,
    _ha_set_light_impl,
    _ha_toggle_device_impl,
    _ha_request,
    build_skills,
    ha_call_service,
    ha_list,
    ha_state,
    ha_toggle,
    ha_turn_off,
    ha_turn_on,
)


CFG = HomeAssistantConfig(url="http://localhost:8123", token="test-token")


# ── _ha_request ────────────────────────────────────────────────────────


class TestHaRequest:
    @patch("jarvis.skills.homeassistant.urllib.request.urlopen")
    def test_get_success(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"state": "on"}).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp
        result = _ha_request(CFG, "GET", "/states/light.bedroom")
        assert result == {"state": "on"}

    @patch("jarvis.skills.homeassistant.urllib.request.urlopen")
    def test_post_success(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"[]"
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp
        result = _ha_request(CFG, "POST", "/services/light/turn_on", {"entity_id": "light.x"})
        assert result == []

    @patch("jarvis.skills.homeassistant.urllib.request.urlopen")
    def test_http_error_returns_none(self, mock_urlopen):
        from urllib.error import HTTPError
        mock_urlopen.side_effect = HTTPError(
            url="http://x", code=401, msg="Unauthorized", hdrs=None, fp=None
        )
        result = _ha_request(CFG, "GET", "/states/x")
        assert result is None

    @patch("jarvis.skills.homeassistant.urllib.request.urlopen")
    def test_timeout_returns_none(self, mock_urlopen):
        import urllib.error
        mock_urlopen.side_effect = TimeoutError("timeout")
        result = _ha_request(CFG, "GET", "/states/x")
        assert result is None

    def test_url_construction(self):
        """URL собирается правильно из конфига."""
        with patch("jarvis.skills.homeassistant.urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = b"{}"
            mock_resp.__enter__ = MagicMock(return_value=mock_resp)
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_resp
            _ha_request(CFG, "GET", "/api/states")
            call_args = mock_urlopen.call_args[0][0]
            assert "localhost:8123" in call_args.full_url
            assert "Bearer test-token" in call_args.headers["Authorization"]


# ── ha_toggle / ha_turn_on / ha_turn_off ────────────────────────────────


class TestHaToggleOnOff:
    @patch("jarvis.skills.homeassistant._ha_request", return_value=[{}])
    def test_toggle_success(self, mock_req):
        result = ha_toggle(CFG, "light.bedroom")
        assert "Переключил" in result

    @patch("jarvis.skills.homeassistant._ha_request", return_value=None)
    def test_toggle_failure(self, mock_req):
        result = ha_toggle(CFG, "light.bedroom")
        assert "Не удалось" in result

    @patch("jarvis.skills.homeassistant._ha_request", return_value=[{}])
    def test_turn_on_success(self, mock_req):
        result = ha_turn_on(CFG, "light.bedroom")
        assert "Включил" in result

    @patch("jarvis.skills.homeassistant._ha_request", return_value=None)
    def test_turn_on_failure(self, mock_req):
        result = ha_turn_on(CFG, "light.bedroom")
        assert "Не удалось включить" in result

    @patch("jarvis.skills.homeassistant._ha_request", return_value=[{}])
    def test_turn_off_success(self, mock_req):
        result = ha_turn_off(CFG, "light.bedroom")
        assert "Выключил" in result


# ── ha_state ────────────────────────────────────────────────────────────


class TestHaState:
    @patch("jarvis.skills.homeassistant._ha_request")
    def test_state_with_attributes(self, mock_req):
        mock_req.return_value = {
            "state": "on",
            "attributes": {
                "friendly_name": "Спальня",
                "brightness": 128,
                "color_temp": 400,
            },
        }
        result = ha_state(CFG, "light.bedroom")
        assert "Спальня" in result
        assert "on" in result
        assert "brightness: 128" in result

    @patch("jarvis.skills.homeassistant._ha_request")
    def test_state_simple(self, mock_req):
        mock_req.return_value = {"state": "off", "attributes": {"friendly_name": "Lamp"}}
        result = ha_state(CFG, "switch.lamp")
        assert "Lamp" in result
        assert "off" in result

    @patch("jarvis.skills.homeassistant._ha_request", return_value=None)
    def test_state_failure(self, mock_req):
        result = ha_state(CFG, "light.x")
        assert "Не удалось" in result


# ── ha_list ─────────────────────────────────────────────────────────────


class TestHaList:
    @patch("jarvis.skills.homeassistant._ha_request")
    def test_list_all(self, mock_req):
        mock_req.return_value = [
            {"entity_id": "light.bedroom", "state": "on", "attributes": {"friendly_name": "Спальня"}},
            {"entity_id": "switch.kitchen", "state": "off", "attributes": {"friendly_name": "Кухня"}},
        ]
        result = ha_list(CFG)
        assert "Спальня" in result
        assert "Кухня" in result

    @patch("jarvis.skills.homeassistant._ha_request")
    def test_list_filtered_by_domain(self, mock_req):
        mock_req.return_value = [
            {"entity_id": "light.a", "state": "on", "attributes": {"friendly_name": "A"}},
            {"entity_id": "switch.b", "state": "off", "attributes": {"friendly_name": "B"}},
        ]
        result = ha_list(CFG, domain="light")
        assert "A" in result
        assert "B" not in result

    @patch("jarvis.skills.homeassistant._ha_request")
    def test_list_empty(self, mock_req):
        mock_req.return_value = []
        result = ha_list(CFG)
        assert "не найдены" in result

    @patch("jarvis.skills.homeassistant._ha_request", return_value=None)
    def test_list_failure(self, mock_req):
        result = ha_list(CFG)
        assert "Не удалось" in result

    @patch("jarvis.skills.homeassistant._ha_request")
    def test_list_truncates_at_30(self, mock_req):
        mock_req.return_value = [
            {"entity_id": f"sensor.{i}", "state": "ok", "attributes": {"friendly_name": f"S{i}"}}
            for i in range(50)
        ]
        result = ha_list(CFG)
        assert "показано 30 из 50" in result


# ── ha_call_service ─────────────────────────────────────────────────────


class TestHaCallService:
    @patch("jarvis.skills.homeassistant._ha_request", return_value=[{}])
    def test_success(self, mock_req):
        result = ha_call_service(CFG, "climate", "set_temperature", entity_id="climate.room", temperature=22)
        assert "вызван" in result

    @patch("jarvis.skills.homeassistant._ha_request", return_value=None)
    def test_failure(self, mock_req):
        result = ha_call_service(CFG, "light", "turn_on")
        assert "Не удалось" in result


# ── _ha_toggle_device_impl ─────────────────────────────────────────────


class TestHaToggleDevice:
    @patch("jarvis.skills.homeassistant._ha_request", return_value=[{}])
    def test_uses_domain_toggle(self, mock_req):
        result = _ha_toggle_device_impl(CFG, "light.bedroom")
        assert "переключено" in result
        mock_req.assert_called_once()
        call_args = mock_req.call_args
        assert "light/toggle" in call_args[0][2]

    @patch("jarvis.skills.homeassistant._ha_request")
    def test_fallback_to_homeassistant_toggle(self, mock_req):
        mock_req.side_effect = [None, [{}]]  # first fails, second succeeds
        result = _ha_toggle_device_impl(CFG, "light.bedroom")
        assert "переключено" in result
        assert mock_req.call_count == 2

    @patch("jarvis.skills.homeassistant._ha_request", return_value=None)
    def test_both_fail(self, mock_req):
        mock_req.side_effect = [None, None]
        result = _ha_toggle_device_impl(CFG, "light.bedroom")
        assert "Не удалось" in result


# ── _ha_set_light_impl ─────────────────────────────────────────────────


class TestHaSetLight:
    @patch("jarvis.skills.homeassistant._ha_request", return_value=[{}])
    def test_brightness_only(self, mock_req):
        result = _ha_set_light_impl(CFG, "light.bedroom", brightness=75)
        assert "яркость 75%" in result
        call_data = mock_req.call_args[0][3]
        assert call_data["brightness_pct"] == 75

    @patch("jarvis.skills.homeassistant._ha_request", return_value=[{}])
    def test_rgb_color(self, mock_req):
        result = _ha_set_light_impl(CFG, "light.bedroom", rgb_color=[255, 0, 0])
        assert "RGB [255, 0, 0]" in result
        call_data = mock_req.call_args[0][3]
        assert call_data["rgb_color"] == [255, 0, 0]

    @patch("jarvis.skills.homeassistant._ha_request", return_value=[{}])
    def test_color_name_russian(self, mock_req):
        result = _ha_set_light_impl(CFG, "light.bedroom", color_name="красный")
        assert "красный" in result
        call_data = mock_req.call_args[0][3]
        assert call_data["rgb_color"] == [255, 0, 0]

    @patch("jarvis.skills.homeassistant._ha_request", return_value=[{}])
    def test_color_name_english(self, mock_req):
        result = _ha_set_light_impl(CFG, "light.bedroom", color_name="blue")
        call_data = mock_req.call_args[0][3]
        assert call_data["rgb_color"] == [0, 0, 255]

    @patch("jarvis.skills.homeassistant._ha_request", return_value=[{}])
    def test_brightness_clamp(self, mock_req):
        _ha_set_light_impl(CFG, "light.x", brightness=150)
        call_data = mock_req.call_args[0][3]
        assert call_data["brightness_pct"] == 100

    @patch("jarvis.skills.homeassistant._ha_request", return_value=[{}])
    def test_color_temp(self, mock_req):
        result = _ha_set_light_impl(CFG, "light.x", color_temp=400)
        assert "400" in result


# ── _ha_get_state_impl (полный дамп) ────────────────────────────────────


class TestHaGetStateFull:
    @patch("jarvis.skills.homeassistant._ha_request")
    def test_full_state_dump(self, mock_req):
        mock_req.return_value = {
            "state": "on",
            "attributes": {"friendly_name": "Light", "brightness": 200},
            "context": {"id": "ctx-1", "parent_id": None},
            "last_changed": "2025-01-01T00:00:00",
            "last_updated": "2025-01-01T00:00:00",
        }
        result = _ha_get_state_impl(CFG, "light.bedroom")
        assert "Полное состояние" in result
        assert "Light" in result
        assert "ctx-1" in result
        assert "brightness: 200" in result

    @patch("jarvis.skills.homeassistant._ha_request", return_value=None)
    def test_full_state_failure(self, mock_req):
        result = _ha_get_state_impl(CFG, "light.x")
        assert "Не удалось" in result

    @patch("jarvis.skills.homeassistant._ha_request")
    def test_truncates_long_dict_attrs(self, mock_req):
        big_val = {"k": "x" * 300}
        mock_req.return_value = {
            "state": "on",
            "attributes": {"big": big_val, "friendly_name": "X"},
            "context": {},
            "last_changed": "", "last_updated": "",
        }
        result = _ha_get_state_impl(CFG, "light.x")
        assert "..." in result  # truncated


# ── _ha_run_script_impl ────────────────────────────────────────────────


class TestHaRunScript:
    @patch("jarvis.skills.homeassistant._ha_request", return_value=[{}])
    def test_script_entity(self, mock_req):
        result = _ha_run_script_impl(CFG, "script.goodnight")
        assert "Скрипт" in result
        mock_req.assert_called_once()
        assert "script/turn_on" in mock_req.call_args[0][2]

    @patch("jarvis.skills.homeassistant._ha_request", return_value=[{}])
    def test_automation_entity(self, mock_req):
        result = _ha_run_script_impl(CFG, "automation.welcome_home")
        assert "Автоматизацию" in result
        mock_req.assert_called_once()
        assert "automation/trigger" in mock_req.call_args[0][2]

    @patch("jarvis.skills.homeassistant._ha_request", return_value=[{}])
    def test_unknown_domain_fallback(self, mock_req):
        result = _ha_run_script_impl(CFG, "scene.movie")
        assert "запущен" in result
        assert "homeassistant/turn_on" in mock_req.call_args[0][2]

    @patch("jarvis.skills.homeassistant._ha_request", return_value=None)
    def test_failure(self, mock_req):
        result = _ha_run_script_impl(CFG, "script.x")
        assert "Не удалось" in result


# ── _ha_list_devices_impl ──────────────────────────────────────────────


class TestHaListDevices:
    @patch("jarvis.skills.homeassistant._ha_request", return_value=None)
    def test_failure(self, mock_req):
        result = _ha_list_devices_impl(CFG)
        assert "Не удалось" in result

    @patch("jarvis.skills.homeassistant._ha_request", return_value=[])
    def test_empty(self, mock_req):
        result = _ha_list_devices_impl(CFG)
        assert "не найдены" in result

    @patch("jarvis.skills.homeassistant._ha_request")
    def test_lists_devices(self, mock_req):
        mock_req.return_value = [
            {"id": "dev1", "name": "Lamp", "area_id": "bedroom", "model": "XYZ", "manufacturer": "Philips", "type": "light"},
            {"id": "dev2", "name": "Sensor", "area_id": "", "model": "", "manufacturer": "", "type": "sensor"},
        ]
        result = _ha_list_devices_impl(CFG)
        assert "Lamp" in result
        assert "Philips" in result
        assert "Sensor" in result
        assert "bedroom" in result

    @patch("jarvis.skills.homeassistant._ha_request")
    def test_truncates_at_50(self, mock_req):
        mock_req.return_value = [
            {"id": f"d{i}", "name": f"Device {i}", "area_id": "", "model": "", "manufacturer": "", "type": "sensor"}
            for i in range(80)
        ]
        result = _ha_list_devices_impl(CFG)
        assert "показано 50 из 80" in result


# ── build_skills ───────────────────────────────────────────────────────


class TestBuildSkills:
    def test_returns_eleven_skills(self):
        skills = build_skills(CFG)
        assert len(skills) == 11

    def test_expected_names(self):
        names = {s.name for s in build_skills(CFG)}
        assert "ha_toggle" in names
        assert "ha_turn_on" in names
        assert "ha_turn_off" in names
        assert "ha_state" in names
        assert "ha_list" in names
        assert "ha_call_service" in names
        assert "ha_list_devices" in names
        assert "ha_toggle_device" in names
        assert "ha_set_light" in names
        assert "ha_get_state" in names
        assert "ha_run_script" in names

    def test_all_tool_specs_valid(self):
        for skill in build_skills(CFG):
            spec = skill.to_openai_tool()
            assert spec["type"] == "function"
            params = spec["function"]["parameters"]
            assert params["type"] == "object"
            for req in params.get("required", []):
                assert req in params["properties"]
