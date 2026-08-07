"""Тесты ядра ассистента (assistant.py)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from jarvis.assistant import Assistant, Event, State
from jarvis.config import Config


# ── Event ──────────────────────────────────────────────────────────────


class TestEvent:
    def test_event_fields(self):
        e = Event(State.LISTENING, "привет", "user")
        assert e.state == State.LISTENING
        assert e.text == "привет"
        assert e.speaker == "user"

    def test_event_defaults(self):
        e = Event(State.IDLE)
        assert e.text == ""
        assert e.speaker == ""
        assert e.preview_url == ""

    def test_state_values(self):
        assert State.IDLE == "idle"
        assert State.LISTENING == "listening"
        assert State.THINKING == "thinking"
        assert State.SPEAKING == "speaking"


# ── Assistant (с моками) ───────────────────────────────────────────────


@pytest.fixture
def mock_assistant():
    """Создаёт Assistant со всеми зависимостями замоканными."""
    announced = []

    with (
        patch("jarvis.assistant.build_registry") as mock_reg,
        patch("jarvis.assistant.build_brain") as mock_brain,
        patch("jarvis.assistant.SpeechToText"),
        patch("jarvis.assistant.WakeWordDetector"),
        patch("jarvis.assistant.SpeechRecorder"),
        patch("jarvis.assistant.Microphone"),
        patch("jarvis.assistant.SystemMonitor"),
        patch("jarvis.assistant.Speaker"),
        patch("jarvis.assistant.HotkeyListener"),
    ):
        registry_mock = MagicMock()
        registry_mock.names = []
        registry_mock.__len__ = MagicMock(return_value=0)
        services_mock = MagicMock()
        mock_reg.return_value = (registry_mock, services_mock)

        brain_mock = MagicMock()
        brain_mock.load_session = MagicMock()
        brain_mock.ask = MagicMock(return_value="Готово, сэр.")
        mock_brain.return_value = brain_mock

        config = Config()
        assistant = Assistant(config, announced.append)
        assistant._stop.set()  # prevent any background loops
        yield assistant, announced, brain_mock


class TestAssistantInit:
    def test_brain_loaded(self, mock_assistant):
        assistant, _, brain_mock = mock_assistant
        brain_mock.load_session.assert_called_once()

    def test_sink_receives_events(self, mock_assistant):
        assistant, announced, _ = mock_assistant
        assistant._emit(State.IDLE, "test")
        assert len(announced) == 1
        assert announced[0].state == State.IDLE


class TestHandleText:
    def test_empty_returns_empty(self, mock_assistant):
        assistant, _, _ = mock_assistant
        result = assistant.handle_text("")
        assert result == ""

    def test_normal_command(self, mock_assistant):
        assistant, _, brain_mock = mock_assistant
        result = assistant.handle_text("Какая погода?")
        assert result == "Готово, сэр."
        brain_mock.ask.assert_called_once_with("Какая погода?")

    def test_whitespace_trimmed(self, mock_assistant):
        assistant, _, brain_mock = mock_assistant
        assistant.handle_text("   привет   ")
        brain_mock.ask.assert_called_once_with("привет")

    def test_alias_expansion(self, mock_assistant):
        assistant, _, brain_mock = mock_assistant
        assistant.config.aliases = {"привет": "привет, Джарвис"}
        assistant.handle_text("привет")
        brain_mock.ask.assert_called_once_with("привет, Джарвис")

    def test_brain_error_returns_fallback(self, mock_assistant):
        assistant, _, brain_mock = mock_assistant
        brain_mock.ask.side_effect = RuntimeError("модель упала")
        result = assistant.handle_text("тест")
        assert "нейронной" in result

    def test_emits_thinking_and_speaking(self, mock_assistant):
        assistant, announced, _ = mock_assistant
        assistant.handle_text("тест")
        states = [e.state for e in announced]
        assert State.THINKING in states
        assert State.SPEAKING in states
        assert State.IDLE in states


class TestAnnounce:
    def test_announce_emits_and_speaks(self, mock_assistant):
        assistant, announced, _ = mock_assistant
        assistant._announce("Таймер сработал")
        assert any("Таймер сработал" in e.text for e in announced)
        assistant.speaker.say.assert_called_once_with("Таймер сработал")

    def test_announce_emits_idle_after(self, mock_assistant):
        assistant, announced, _ = mock_assistant
        assistant._announce("test")
        assert announced[-1].state == State.IDLE


class TestOnToolResult:
    def test_web_search_shows_preview(self, mock_assistant):
        assistant, announced, _ = mock_assistant
        with patch("jarvis.skills.web._last_search_url", "https://example.com"):
            assistant._on_tool_result("web_search", "Found results")
        assert any(e.preview_url == "https://example.com" for e in announced)

    def test_non_web_search_ignored(self, mock_assistant):
        assistant, announced, _ = mock_assistant
        assistant._on_tool_result("calculator", "42")
        assert not any(e.preview_url for e in announced)

    def test_browser_fallback_no_preview(self, mock_assistant):
        assistant, announced, _ = mock_assistant
        with patch("jarvis.skills.web._last_search_url", "https://example.com"):
            assistant._on_tool_result("web_search", "открыл в браузере")
        assert not any(e.preview_url for e in announced)


class TestStopAndShutdown:
    def test_stop_sets_event(self, mock_assistant):
        assistant, _, _ = mock_assistant
        assistant._stop.clear()
        assistant.stop()
        assert assistant._stop.is_set()

    def test_shutdown_calls_sub_shutdowns(self, mock_assistant):
        assistant, _, _ = mock_assistant
        assistant.shutdown()
        assistant.monitor.shutdown.assert_called_once()
        assistant.services.shutdown.assert_called_once()
