"""Тесты системы голосовых профилей."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from jarvis.skills.personality import (
    Profile,
    ProfileManager,
    PROFILES,
    build_skills,
    get_current_profile,
    get_profile_greeting,
    get_profile_prompt,
    get_profile_tts_rate,
    get_profile_voice,
    list_profiles,
    set_profile,
)
from jarvis.skills.registry import Skill


# Сбрасываем глобальный синглтон и изолируем файл между тестами.
@pytest.fixture(autouse=True)
def _reset_manager(tmp_path, monkeypatch):
    import jarvis.skills.personality as mod
    monkeypatch.setattr(mod, "_PROFILES_FILE", tmp_path / "test_profile.json")
    mod._manager = None
    yield
    mod._manager = None


# ── PROFILES справочник ───────────────────────────────────────────────


class TestProfilesDict:
    def test_at_least_eight_profiles(self):
        assert len(PROFILES) >= 8

    def test_all_profiles_are_Profile_instances(self):
        for p in PROFILES.values():
            assert isinstance(p, Profile)

    def test_all_have_required_fields(self):
        for key, p in PROFILES.items():
            assert p.name, f"{key}: empty name"
            assert p.system_prompt, f"{key}: empty system_prompt"
            assert p.greeting, f"{key}: empty greeting"
            assert p.edge_voice.startswith("ru-RU-"), f"{key}: bad voice {p.edge_voice}"
            assert 50 <= p.tts_rate <= 400, f"{key}: bad rate {p.tts_rate}"

    def test_jarvis_is_default(self):
        assert "jarvis" in PROFILES
        assert PROFILES["jarvis"].address == "сэр"

    def test_friday_exists(self):
        assert "friday" in PROFILES
        assert "босс" in PROFILES["friday"].address

    def test_concise_no_address(self):
        assert PROFILES["concise"].address == ""

    def test_hacker_has_slang(self):
        assert "чувак" in PROFILES["hacker"].address

    def test_butler_is_polite(self):
        assert "господин" in PROFILES["butler"].address

    def test_friday_has_different_voice(self):
        assert PROFILES["friday"].edge_voice != PROFILES["jarvis"].edge_voice

    def test_all_have_unique_keys(self):
        assert len(PROFILES) == len(set(PROFILES))


# ── ProfileManager ───────────────────────────────────────────────────


class TestProfileManager:
    def test_default_is_jarvis(self):
        mgr = ProfileManager("jarvis")
        assert mgr.current_key == "jarvis"
        assert mgr.current.name == "Джарвис"

    def test_init_with_custom_profile(self):
        mgr = ProfileManager("pirate")
        assert mgr.current_key == "pirate"
        assert mgr.current.address == "капитан"

    def test_set_profile(self):
        mgr = ProfileManager("jarvis")
        p = mgr.set("friday")
        assert mgr.current_key == "friday"
        assert p.name == "Пятница"

    def test_set_profile_invalid_raises(self):
        mgr = ProfileManager("jarvis")
        with pytest.raises(ValueError, match="не найден"):
            mgr.set("nonexistent")

    def test_set_case_insensitive(self):
        mgr = ProfileManager("jarvis")
        mgr.set("FRIDAY")
        assert mgr.current_key == "friday"

    def test_set_trims_whitespace(self):
        mgr = ProfileManager("jarvis")
        mgr.set("  friday  ")
        assert mgr.current_key == "friday"


# ── Persist ───────────────────────────────────────────────────────────


class TestProfilePersist:
    def test_save_and_load(self):
        mgr1 = ProfileManager("jarvis")
        mgr1.set("hacker")
        # Новый менеджер должен прочитать сохранённый профиль
        import jarvis.skills.personality as mod
        mod._manager = None  # сбросить синглтон
        mgr2 = ProfileManager("jarvis")  # initial=jarvis, но загружает hacker
        assert mgr2.current_key == "hacker"

    def test_corrupted_file_uses_default(self, tmp_path):
        prof_file = tmp_path / "test_profile.json"
        prof_file.write_text("not json{{{", encoding="utf-8")
        mgr = ProfileManager("military")
        assert mgr.current_key == "military"  # stays default, no crash

    def test_missing_file_uses_default(self):
        mgr = ProfileManager("butler")
        assert mgr.current_key == "butler"


# ── Публичные функции ─────────────────────────────────────────────────


class TestPublicFunctions:
    def test_list_profiles_contains_all(self):
        result = list_profiles()
        for key in PROFILES:
            assert key in result

    def test_list_profiles_shows_active(self):
        from jarvis.skills.personality import get_manager
        get_manager("pirate")
        result = list_profiles()
        assert "(активен)" in result
        assert "pirate" in result

    def test_set_profile_success(self):
        from jarvis.skills.personality import get_manager
        get_manager("jarvis")
        result = set_profile("military")
        assert "Военный" in result

    def test_set_profile_failure(self):
        from jarvis.skills.personality import get_manager
        get_manager("jarvis")
        result = set_profile("nope")
        assert "не найден" in result

    def test_get_current_profile(self):
        from jarvis.skills.personality import get_manager
        get_manager("friday")
        result = get_current_profile()
        assert "Пятница" in result
        assert "friday" in result

    def test_get_profile_prompt(self):
        from jarvis.skills.personality import get_manager
        get_manager("pirate")
        prompt = get_profile_prompt()
        assert "пират" in prompt.lower() or "корабл" in prompt.lower()

    def test_get_profile_greeting(self):
        from jarvis.skills.personality import get_manager
        get_manager("concise")
        assert get_profile_greeting() == "Готов."

    def test_get_profile_voice(self):
        from jarvis.skills.personality import get_manager
        get_manager("friday")
        assert get_profile_voice() == PROFILES["friday"].edge_voice

    def test_get_profile_tts_rate(self):
        from jarvis.skills.personality import get_manager
        get_manager("hacker")
        assert get_profile_tts_rate() == PROFILES["hacker"].tts_rate


# ── build_skills ───────────────────────────────────────────────────────


class TestBuildSkills:
    def test_returns_three_skills(self):
        skills = build_skills()
        assert len(skills) == 3

    def test_skill_names(self):
        names = {s.name for s in build_skills()}
        assert names == {"list_profiles", "set_profile", "get_profile"}

    def test_set_profile_has_enum(self):
        skills = build_skills()
        sp = next(s for s in skills if s.name == "set_profile")
        enum_values = sp.parameters["properties"]["profile"]["enum"]
        assert set(enum_values) == set(PROFILES.keys())

    def test_all_handlers_callable(self):
        from jarvis.skills.personality import get_manager
        get_manager("jarvis")
        for skill in build_skills():
            if skill.name == "set_profile":
                result = skill.handler(profile="concise")
            else:
                result = skill.handler()
            assert isinstance(result, str)
            assert len(result) > 0
