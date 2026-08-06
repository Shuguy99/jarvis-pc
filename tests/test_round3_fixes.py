"""Тесты для третьего раунда: assistant resilience, web errors, openai timeout."""

from unittest.mock import MagicMock, patch

import pytest

from jarvis.assistant import Assistant, State
from jarvis.config import Config


class TestAssistantResilience:
    """handle_text и _handle_utterance не умирают от исключений."""

    def _make_assistant(self):
        config = Config()
        # Mock all heavy dependencies.
        with (
            patch("jarvis.assistant.build_registry", return_value=(MagicMock(), MagicMock())),
            patch("jarvis.assistant.build_brain") as build_brain_mock,
            patch("jarvis.assistant.SpeechToText"),
            patch("jarvis.assistant.WakeWordDetector"),
            patch("jarvis.assistant.SpeechRecorder"),
            patch("jarvis.assistant.Microphone"),
            patch("jarvis.assistant.SystemMonitor"),
            patch("jarvis.assistant.Speaker"),
            patch("jarvis.assistant.HotkeyListener"),
        ):
            brain_mock = MagicMock()
            brain_mock.load_session = MagicMock()
            brain_mock.ask.side_effect = RuntimeError("GPU out of memory")
            build_brain_mock.return_value = brain_mock

            events = []
            assistant = Assistant(config, events.append)
            assistant.brain.ask.side_effect = RuntimeError("GPU out of memory")
            return assistant, events

    def test_brain_crash_returns_fallback(self):
        assistant, _ = self._make_assistant()
        reply = assistant.handle_text("привет")
        assert "нейронной" in reply.lower() or "проблем" in reply.lower()

    def test_brain_crash_emits_idle(self):
        assistant, events = self._make_assistant()
        assistant.handle_text("привет")
        states = [e.state for e in events]
        # Должен завершиться в IDLE.
        assert State.IDLE in states


class TestWebErrorHandling:
    """get_weather (wttr.in fallback) и fetch_summary не падают от сетевых ошибок."""

    def test_weather_empty_location(self):
        from jarvis.skills.weather import get_weather
        from jarvis.config import WeatherConfig
        config = WeatherConfig()
        result = get_weather(config, "")
        assert "город" in result.lower()

    def test_wttr_network_error(self):
        from jarvis.skills.weather import _wttr_request
        with patch("jarvis.skills.weather.urllib.request.urlopen", side_effect=TimeoutError("no net")):
            result = _wttr_request("Москва", "%C+%t")
        assert result == ""

    def test_fetch_summary_timeout(self):
        from jarvis.skills.web import fetch_summary
        import requests
        with patch.object(requests, "get", side_effect=requests.Timeout("timeout")):
            result = fetch_summary("Python")
        assert "не ответил" in result.lower()


class TestOpenAITimeout:
    """OpenAIBrain передаёт timeout в клиент."""

    def test_timeout_configured(self):
        from jarvis.brain.openai_brain import OpenAIBrain
        assert OpenAIBrain._TIMEOUT_S == 120

    def test_client_receives_timeout(self):
        from jarvis.brain.openai_brain import OpenAIBrain
        from jarvis.config import BrainConfig
        from jarvis.skills.registry import SkillRegistry
        import sys
        mock_module = MagicMock()
        sys.modules.setdefault("openai", mock_module)
        try:
            OpenAIBrain(BrainConfig(), SkillRegistry(), "sk-test")
            kwargs = mock_module.OpenAI.call_args[1]
            assert kwargs["timeout"] == 120
        finally:
            sys.modules.pop("openai", None)
