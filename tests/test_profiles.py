"""Тесты системы голосовых профилей."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from jarvis.profiles import BUILTIN_PROFILES, ProfileManager, VoiceProfile, PROFILE_STATE_PATH


# ── VoiceProfile ───────────────────────────────────────────────────────


class TestVoiceProfile:
    """Тесты создания профиля из словаря."""

    def test_from_dict_minimal(self):
        """Минимальный словарь — остальные поля по умолчанию."""
        p = VoiceProfile.from_dict("test", {
            "system_prompt": "Тестовый промпт",
        })
        assert p.id == "test"
        assert p.name == "test"  # name не задан — берём id
        assert p.system_prompt == "Тестовый промпт"
        assert p.engine == "edge"
        assert p.rate == 190
        assert p.volume == 1.0
        assert p.greeting == ""
        assert p.address == "сэр"

    def test_from_dict_full(self):
        """Полный словарь — все поля."""
        data = {
            "name": "Тест Джарвис",
            "description": "Описание",
            "system_prompt": "Промпт",
            "greeting": "Привет!",
            "address": "босс",
            "tts": {
                "engine": "sapi5",
                "voice": "Irina",
                "edge_voice": "ru-RU-SvetlanaNeural",
                "rate": 220,
                "volume": 0.8,
            },
        }
        p = VoiceProfile.from_dict("full", data)
        assert p.id == "full"
        assert p.name == "Тест Джарвис"
        assert p.description == "Описание"
        assert p.greeting == "Привет!"
        assert p.address == "босс"
        assert p.engine == "sapi5"
        assert p.voice == "Irina"
        assert p.edge_voice == "ru-RU-SvetlanaNeural"
        assert p.rate == 220
        assert p.volume == 0.8

    def test_from_dict_empty_tts(self):
        """Пустой tts-словарь — дефолтные значения."""
        p = VoiceProfile.from_dict("t", {"system_prompt": "x", "tts": {}})
        assert p.engine == "edge"
        assert p.rate == 190


# ── ProfileManager ─────────────────────────────────────────────────────


class TestProfileManager:
    """Тесты менеджера профилей."""

    def test_builtin_profiles_loaded(self):
        """Все встроенные профили доступны."""
        # Отключаем загрузку состояния из файла
        with patch.object(ProfileManager, "_load_state", return_value=None):
            mgr = ProfileManager()
        for pid in BUILTIN_PROFILES:
            assert pid in [p.id for p in mgr.list_profiles()]

    def test_default_profile_active(self):
        """По умолчанию активен профиль 'default'."""
        with patch.object(ProfileManager, "_load_state", return_value=None):
            mgr = ProfileManager()
        assert mgr.current_id == "default"
        assert mgr.current.name == "Джарвис"

    def test_current_returns_profile(self):
        """current возвращает VoiceProfile."""
        with patch.object(ProfileManager, "_load_state", return_value=None):
            mgr = ProfileManager()
        assert isinstance(mgr.current, VoiceProfile)

    def test_get_existing(self):
        """get() возвращает профиль по ID."""
        with patch.object(ProfileManager, "_load_state", return_value=None):
            mgr = ProfileManager()
        p = mgr.get("casual")
        assert p is not None
        assert p.id == "casual"

    def test_get_missing(self):
        """get() возвращает None для несуществующего."""
        with patch.object(ProfileManager, "_load_state", return_value=None):
            mgr = ProfileManager()
        assert mgr.get("nonexistent") is None

    def test_switch_success(self):
        """Успешное переключение профиля."""
        with patch.object(ProfileManager, "_load_state", return_value=None):
            mgr = ProfileManager()
        ok, msg = mgr.switch("strict")
        assert ok is True
        assert mgr.current_id == "strict"

    def test_switch_unknown(self):
        """Переключение на несуществующий профиль."""
        with patch.object(ProfileManager, "_load_state", return_value=None):
            mgr = ProfileManager()
        ok, msg = mgr.switch("nonexistent")
        assert ok is False
        assert mgr.current_id == "default"  # не поменялось

    def test_switch_multiple(self):
        """Последовательные переключения."""
        with patch.object(ProfileManager, "_load_state", return_value=None):
            mgr = ProfileManager()
        mgr.switch("pirate")
        assert mgr.current_id == "pirate"
        mgr.switch("casual")
        assert mgr.current_id == "casual"
        mgr.switch("default")
        assert mgr.current_id == "default"

    def test_list_profiles_all(self):
        """list_profiles возвращает все профили."""
        with patch.object(ProfileManager, "_load_state", return_value=None):
            mgr = ProfileManager()
        profiles = mgr.list_profiles()
        assert len(profiles) >= len(BUILTIN_PROFILES)

    def test_custom_profiles(self):
        """Пользовательские профили добавляются к встроенным."""
        custom = {
            "custom_one": {
                "name": "Мой",
                "description": "Кастомный",
                "system_prompt": "Промпт",
                "greeting": "Привет",
                "address": "друг",
            }
        }
        with patch.object(ProfileManager, "_load_state", return_value=None):
            mgr = ProfileManager(custom_profiles=custom)
        assert mgr.get("custom_one") is not None
        assert mgr.get("default") is not None

    def test_custom_overrides_builtin(self):
        """Кастомный профиль может переопределить встроенный."""
        custom = {
            "default": {
                "name": "Модифицированный Джарвис",
                "description": "Переопределённый",
                "system_prompt": "Новый промпт",
                "greeting": "Салют!",
                "address": "товарищ",
            }
        }
        with patch.object(ProfileManager, "_load_state", return_value=None):
            mgr = ProfileManager(custom_profiles=custom)
        p = mgr.get("default")
        assert p.name == "Модифицированный Джарвис"
        assert p.system_prompt == "Новый промпт"

    def test_disabled_profiles_no_custom(self):
        """Если custom_profiles=None — только встроенные."""
        with patch.object(ProfileManager, "_load_state", return_value=None):
            mgr = ProfileManager(custom_profiles=None)
        assert len(mgr.list_profiles()) == len(BUILTIN_PROFILES)

    def test_invalid_saved_profile_fallback(self):
        """Если сохранённый профиль не существует — откат на default."""
        with patch.object(ProfileManager, "_load_state", return_value="ghost_profile"):
            mgr = ProfileManager()
            assert mgr.current_id == "default"

    def test_load_state_from_file(self, tmp_path):
        """Загрузка сохранённого профиля из файла."""
        state_file = tmp_path / "profile.json"
        state_file.write_text('{"profile": "casual"}', encoding="utf-8")
        with patch("jarvis.profiles.PROFILE_STATE_PATH", state_file):
            result = ProfileManager._load_state()
        assert result == "casual"

    def test_load_state_no_file(self, tmp_path):
        """Нет файла — None."""
        state_file = tmp_path / "nonexistent.json"
        with patch("jarvis.profiles.PROFILE_STATE_PATH", state_file):
            assert ProfileManager._load_state() is None

    def test_load_state_corrupt_file(self, tmp_path):
        """Повреждённый файл — None."""
        state_file = tmp_path / "profile.json"
        state_file.write_text('bad json', encoding="utf-8")
        with patch("jarvis.profiles.PROFILE_STATE_PATH", state_file):
            assert ProfileManager._load_state() is None

    def test_save_and_load_roundtrip(self, tmp_path):
        """Сохранение и загрузка — полный цикл."""
        state_file = tmp_path / "profile.json"
        with patch("jarvis.profiles.PROFILE_STATE_PATH", state_file):
            mgr = ProfileManager()
            mgr.switch("pirate")
            # Новый менеджер должен прочитать сохранённый
            mgr2 = ProfileManager()
            assert mgr2.current_id == "pirate"

    def test_builtin_profile_structure(self):
        """Все встроенные профили имеют корректную структуру."""
        for pid, pdata in BUILTIN_PROFILES.items():
            assert "system_prompt" in pdata, f"{pid}: нет system_prompt"
            assert "greeting" in pdata, f"{pid}: нет greeting"
            assert "name" in pdata, f"{pid}: нет name"
            assert "description" in pdata, f"{pid}: нет description"
            assert "address" in pdata, f"{pid}: нет address"
            assert "tts" in pdata, f"{pid}: нет tts"
            assert "engine" in pdata["tts"], f"{pid}: нет tts.engine"
            assert "edge_voice" in pdata["tts"], f"{pid}: нет tts.edge_voice"
            assert "rate" in pdata["tts"], f"{pid}: нет tts.rate"


# ── Навыки профилей ────────────────────────────────────────────────────


class TestProfileSkills:
    """Тесты навыков управления профилями."""

    def _make_registry(self, mgr: ProfileManager):
        from jarvis.skills.profiles import _build_skills
        from jarvis.skills.registry import SkillRegistry
        registry = SkillRegistry()
        registry.extend(_build_skills(mgr))
        return registry

    def test_switch_profile_skill(self):
        """Навык switch_profile переключает профиль."""
        with patch.object(ProfileManager, "_load_state", return_value=None):
            mgr = ProfileManager()
        registry = self._make_registry(mgr)
        result = registry.call("switch_profile", {"profile_id": "casual"})
        assert mgr.current_id == "casual"

    def test_switch_profile_unknown(self):
        """Навык switch_profile с несуществующим ID."""
        with patch.object(ProfileManager, "_load_state", return_value=None):
            mgr = ProfileManager()
        registry = self._make_registry(mgr)
        result = registry.call("switch_profile", {"profile_id": "xyz"})
        assert mgr.current_id == "default"

    def test_list_profiles_skill(self):
        """Навык list_profiles показывает все профили."""
        with patch.object(ProfileManager, "_load_state", return_value=None):
            mgr = ProfileManager()
        registry = self._make_registry(mgr)
        result = registry.call("list_profiles")
        assert "default" in result
        assert "casual" in result
        assert "strict" in result
        assert "pirate" in result

    def test_current_profile_skill(self):
        """Навык current_profile показывает текущий профиль."""
        with patch.object(ProfileManager, "_load_state", return_value=None):
            mgr = ProfileManager()
        registry = self._make_registry(mgr)
        result = registry.call("current_profile")
        assert "default" in result.lower()

    def test_all_skills_registered(self):
        """Все 3 навыка зарегистрированы."""
        with patch.object(ProfileManager, "_load_state", return_value=None):
            mgr = ProfileManager()
        registry = self._make_registry(mgr)
        assert "switch_profile" in registry
        assert "list_profiles" in registry
        assert "current_profile" in registry
