"""Тесты для второго раунда фиксов: safety, validation, offline brain."""

import re
from unittest.mock import MagicMock, patch

import pytest

from jarvis.brain.offline_brain import OfflineBrain
from jarvis.config import (
    BrainConfig,
    Config,
    MicConfig,
    SkillsConfig,
    _sanitize,
    load_config,
)
from jarvis.skills.apps import _SAFE_CMD_RE, _resolve, open_app
from jarvis.skills.registry import SkillRegistry


class TestOpenAppSafety:
    """Защита от command injection в open_app."""

    def test_safe_names_pass(self):
        for name in ("notepad", "google-chrome", "vs code", "Блокнот", "C:\\Program Files\\app\\app.exe"):
            assert _SAFE_CMD_RE.match(name), f"{name!r} should be safe"

    def test_shell_metacharacters_blocked(self):
        for evil in (
            "notepad & rm -rf /",
            "calc; curl evil.com",
            "$(whoami)",
            "`id`",
            "x && echo pwned",
            "a | cat /etc/passwd",
            "a; b",
        ):
            assert not _SAFE_CMD_RE.match(evil), f"{evil!r} should be blocked"

    @patch("jarvis.skills.apps.subprocess.Popen")
    @patch("jarvis.skills.apps.shutil.which", return_value="/usr/bin/evil")
    def test_open_app_rejects_injection(self, mock_which, mock_popen):
        config = SkillsConfig()
        # "unknown_app & rm -rf /" не найден в Built-in, поэтому
        # command = сырая строка, которая не пройдёт regex.
        result = open_app(config, "unknown_app & rm -rf /")
        mock_popen.assert_not_called()
        assert "хитрое" in result.lower()


class TestConfigSanitize:
    """_sanitize реально исправляет значения, а не просто логирует."""

    def test_out_of_range_clamped(self):
        data = {"mic": {"sample_rate": 1, "vad_aggressiveness": 9}}
        out = _sanitize(Config, data)
        assert out["mic"]["sample_rate"] == 8000  # clamped to min
        assert out["mic"]["vad_aggressiveness"] == 3  # clamped to max

    def test_wrong_type_gets_default(self):
        data = {"mic": {"frame_ms": "abc"}}
        out = _sanitize(Config, data)
        assert out["mic"]["frame_ms"] == 30  # default value

    def test_valid_values_untouched(self):
        data = {"mic": {"sample_rate": 16000, "frame_ms": 30}}
        out = _sanitize(Config, data)
        assert out["mic"]["sample_rate"] == 16000
        assert out["mic"]["frame_ms"] == 30

    def test_unknown_keys_preserved(self):
        data = {"mic": {"sample_rate": 16000, "future_option": 42}}
        out = _sanitize(Config, data)
        assert out["mic"]["future_option"] == 42


class TestOfflineBrainHistory:
    """OfflineBrain.ask() сохраняет историю и сессию."""

    def _make_brain(self):
        config = BrainConfig(backend="offline")
        registry = SkillRegistry()
        return OfflineBrain(config, registry)

    def test_history_grows_on_ask(self):
        brain = self._make_brain()
        brain.ask("какое сейчас время")
        assert len(brain.history) >= 2  # user + assistant

    def test_session_saved(self):
        brain = self._make_brain()
        with patch.object(brain, "save_session") as mock:
            brain.ask("погода")
            mock.assert_called_once()

    def test_trim_limits_history(self):
        brain = self._make_brain()
        brain.config.max_history = 4
        for _ in range(10):
            brain.ask("который час")
        assert len(brain.history) <= brain.config.max_history + 1


class TestMonitorShutdown:
    """monitor.shutdown() ждёт поток."""

    def test_shutdown_joins_thread(self):
        from jarvis.monitor import SystemMonitor

        config = MagicMock()
        config.enabled = True
        config.interval_s = 1.0
        monitor = SystemMonitor(config, lambda t: None)
        monitor.start()
        import time

        time.sleep(0.1)
        monitor.shutdown()
        # После shutdown поток должен быть None.
        assert monitor._thread is None
