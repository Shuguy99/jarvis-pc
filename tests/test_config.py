"""Тесты конфигурации."""

import os
from pathlib import Path
import pytest
import yaml
from jarvis.config import Config, load_config, _sanitize, _expand_env


def test_default_config():
    c = Config()
    assert c.hotkey == "ctrl+alt+j"
    assert c.brain.backend == "ollama"
    assert c.stt.model == "small"
    assert c.tts.engine == "sapi5"


def test_expand_env_var():
    os.environ["_JARVIS_TEST"] = "hello42"
    assert _expand_env("${_JARVIS_TEST}") == "hello42"
    assert _expand_env("prefix-${_JARVIS_TEST}-suffix") == "prefix-hello42-suffix"
    assert _expand_env("${NONEXISTENT_VAR}") == "${NONEXISTENT_VAR}"
    del os.environ["_JARVIS_TEST"]


def test_load_config_missing_file():
    c = load_config("/nonexistent/path/config.yaml")
    assert isinstance(c, Config)
    # Should return defaults


def test_sanitize_clamps_values(tmp_path):
    data = {
        "mic": {"sample_rate": 1},  # too low
        "tts": {"volume": 5.0},    # too high
    }
    result = _sanitize(Config, data)
    assert result["mic"]["sample_rate"] == 8000
    assert result["tts"]["volume"] == 1.0


def test_load_config_from_yaml(tmp_path):
    cfg = {"hotkey": "ctrl+shift+j", "brain": {"backend": "openai"}}
    p = tmp_path / "config.yaml"
    p.write_text(yaml.dump(cfg), encoding="utf-8")
    c = load_config(str(p))
    assert c.hotkey == "ctrl+shift+j"
    assert c.brain.backend == "openai"


def test_path_expansion_in_config(tmp_path):
    cfg = {"skills": {"notes_db": "~/test/notes.json"}}
    p = tmp_path / "config.yaml"
    p.write_text(yaml.dump(cfg), encoding="utf-8")
    c = load_config(str(p))
    assert c.skills.notes.notes_db.startswith(str(Path.home()))
