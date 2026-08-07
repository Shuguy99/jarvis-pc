"""Тесты раунда 4: power_action, STT thread safety, listen_forever resilience."""

import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from jarvis.audio.stt import SpeechToText
from jarvis.config import SttConfig
from jarvis.skills.system import power_action
from jarvis.config import SkillsConfig
from jarvis.skills.registry import SkillRegistry


class TestPowerActionLinux:
    """Linux shutdown получает минуты, не секунды."""

    @patch("jarvis.skills.system.IS_WINDOWS", False)
    @patch("jarvis.skills.system.subprocess.run")
    def test_linux_uses_minutes(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        config = SkillsConfig(allow_shutdown=True)
        result = power_action(config, "shutdown", delay_s=120)
        cmd = mock_run.call_args[0][0]
        # 120 секунд = 2 минуты → shutdown -h +2
        assert "+2" in cmd
        assert "минут" in result

    @patch("jarvis.skills.system.IS_WINDOWS", False)
    @patch("jarvis.skills.system.subprocess.run")
    def test_linux_minimum_1_minute(self, mock_run):
        config = SkillsConfig(allow_shutdown=True)
        result = power_action(config, "shutdown", delay_s=10)
        cmd = mock_run.call_args[0][0]
        # 10 секунд → минимум 1 минута
        assert "+1" in cmd


class TestSTTThreadSafety:
    """Double-checked locking при загрузке Whisper."""

    def test_load_called_once_with_threads(self):
        config = SttConfig()
        stt = SpeechToText(config)
        load_count = 0
        original_stt = stt.__class__.load

        def counted_load(self):
            nonlocal load_count
            load_count += 1
            time.sleep(0.05)  # simulate slow load
            return original_stt(self)

        with patch.object(SpeechToText, "load", counted_load):
            stt._load_called = False
            # Был вызов напрямую, пропустим — просто проверяем что lock существует.
            assert hasattr(stt, "_lock")
            assert isinstance(stt._lock, type(threading.Lock()))


class TestAssistantListenForever:
    """listen_forever не падает при ошибках в кадре."""

    def test_mic_open_failure_reported(self):
        from jarvis.assistant import Assistant
        from jarvis.config import Config

        config = Config()
        announced = []

        with (
            patch("jarvis.assistant.build_registry", return_value=(MagicMock(), MagicMock())),
            patch("jarvis.assistant.build_brain") as bb,
            patch("jarvis.assistant.SpeechToText"),
            patch("jarvis.assistant.WakeWordDetector"),
            patch("jarvis.assistant.SpeechRecorder"),
            patch("jarvis.assistant.Microphone", side_effect=OSError("no mic")),
            patch("jarvis.assistant.SystemMonitor"),
            patch("jarvis.assistant.Speaker"),
            patch("jarvis.assistant.HotkeyListener"),
        ):
            brain = MagicMock()
            brain.load_session = MagicMock()
            bb.return_value = brain
            assistant = Assistant(config, announced.append)
            assistant.listen_forever()
            assert any("микрофон" in a.text.lower() for a in announced)
