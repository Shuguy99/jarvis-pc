from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from jarvis.skills.web import (
    _fetch_ddg_results,
    _parse_ddg_html,
    _strip_tags,
    _extract_ddg_url,
    _format_results,
    open_in_browser,
    web_search,
    _last_search_url,
)
from jarvis.config import SkillsConfig
from jarvis.assistant import Event, State


# ── HTML-парсер DuckDuckGo ─────────────────────────────────────────────


@pytest.fixture
def ddg_html() -> str:
    """Минимальный HTML-ответ DuckDuckGo Lite с двумя результатами."""
    return """
    <table><tr>
    <td></td>
    <td>
    <a class="result-link" href="/l/?uddg=https%3A%2F%2Fexample.com&amp;rut=abc">
    Example Site Title</a>
    </td>
    </tr><tr>
    <td class="result-snippet">
    This is a test snippet for the first result.
    </td></tr>
    <tr>
    <td></td>
    <td>
    <a class="result-link" href="https://direct-link.org/page">
    Direct Link Title</a>
    </td>
    </tr><tr>
    <td class="result-snippet">
    Second result snippet here.
    </td></tr></table>
    """


class TestDDGParser:
    """Парсинг HTML DuckDuckGo Lite."""

    def test_parse_two_results(self, ddg_html):
        results = _parse_ddg_html(ddg_html)
        assert len(results) == 2
        assert results[0]["title"] == "Example Site Title"
        assert results[0]["url"] == "https://example.com"
        assert "test snippet" in results[0]["snippet"]

    def test_parse_empty_html(self):
        assert _parse_ddg_html("") == []

    def test_parse_no_results(self):
        assert _parse_ddg_html("<html><body>no results</body></html>") == []

    def test_direct_link_unmodified(self, ddg_html):
        """Ссылки без DDG-редиректа остаются как есть."""
        results = _parse_ddg_html(ddg_html)
        assert results[1]["url"] == "https://direct-link.org/page"


class TestDDGUrlExtraction:
    """Извлечение реального URL из DDG-редиректа."""

    def test_uddg_param(self):
        raw = "/l/?uddg=https%3A%2F%2Fexample.com%2Fpath%3Fq%3D1&amp;rut=abc"
        assert _extract_ddg_url(raw) == "https://example.com/path?q=1"

    def test_no_uddg(self):
        raw = "https://direct.example.com"
        assert _extract_ddg_url(raw) == "https://direct.example.com"


class TestStripTags:
    """Удаление HTML-тегов."""

    def test_basic(self):
        assert _strip_tags("<b>bold</b> text") == "bold text"

    def test_entities(self):
        assert _strip_tags("&amp;&lt;&gt;") == "&<>"

    def test_nested(self):
        assert _strip_tags("<div><a>link</a></div>") == "link"


class TestFormatResults:
    """Форматирование результатов."""

    def test_empty(self):
        assert "Ничего не нашёл" in _format_results("test", [])

    def test_with_results(self):
        results = [
            {"title": "T1", "snippet": "S1", "url": "u1"},
            {"title": "T2", "snippet": "S2", "url": "u2"},
        ]
        text = _format_results("q", results)
        assert "1. T1" in text
        assert "2. T2" in text

    def test_long_snippet_truncated(self):
        results = [{"title": "T", "snippet": "x" * 300, "url": "u"}]
        text = _format_results("q", results)
        assert len(text.split("\n")[1]) < 210


# ── web_search skill ────────────────────────────────────────────────────


class TestWebSearchSkill:
    """web_search фетчит результаты, а не открывает браузер."""

    @patch("jarvis.skills.web.webbrowser")
    @patch("jarvis.skills.web._fetch_ddg_results", return_value=[
        {"title": "Test", "snippet": "Result", "url": "https://test.com"},
    ])
    def test_search_returns_results_not_browser(self, mock_fetch, mock_wb):
        config = SkillsConfig()
        result = web_search(config, "test query")
        assert "Test" in result
        assert "Result" in result
        mock_wb.open.assert_not_called()

    @patch("jarvis.skills.web.webbrowser")
    @patch("jarvis.skills.web._fetch_ddg_results", return_value=[])
    def test_search_fallback_to_browser(self, mock_fetch, mock_wb):
        config = SkillsConfig()
        result = web_search(config, "test query")
        assert "браузере" in result.lower()
        mock_wb.open.assert_called_once()

    @patch("jarvis.skills.web.webbrowser")
    def test_empty_query(self, mock_wb):
        config = SkillsConfig()
        result = web_search(config, "")
        assert "Что искать" in result

    def test_search_stores_url(self):
        """web_search сохраняет URL для open_in_browser."""
        import jarvis.skills.web as web_mod
        old = web_mod._last_search_url
        try:
            with patch("jarvis.skills.web._fetch_ddg_results", return_value=[
                {"title": "T", "snippet": "S", "url": "u"},
            ]):
                config = SkillsConfig()
                web_search(config, "test")
            assert "duckduckgo" in web_mod._last_search_url.lower()
        finally:
            web_mod._last_search_url = old


# ── open_in_browser skill ────────────────────────────────────────────────


class TestOpenInBrowser:
    """open_in_browser открывает последний поиск."""

    @patch("jarvis.skills.web.webbrowser")
    def test_no_previous_search(self, mock_wb):
        import jarvis.skills.web as web_mod
        old = web_mod._last_search_url
        web_mod._last_search_url = ""
        try:
            result = open_in_browser()
            assert "не искали" in result.lower()
            mock_wb.open.assert_not_called()
        finally:
            web_mod._last_search_url = old

    @patch("jarvis.skills.web.webbrowser")
    def test_opens_stored_url(self, mock_wb):
        import jarvis.skills.web as web_mod
        old = web_mod._last_search_url
        web_mod._last_search_url = "https://example.com/search?q=test"
        try:
            result = open_in_browser()
            assert "браузере" in result.lower()
            mock_wb.open.assert_called_once_with("https://example.com/search?q=test")
        finally:
            web_mod._last_search_url = old


# ── on_tool_result callback ─────────────────────────────────────────────


class TestOnToolResultCallback:
    """Brain вызывает on_tool_result после каждого tool call."""

    def test_callback_fired_on_tool_call(self):
        from jarvis.brain.base import Brain, Message, ToolCall
        from jarvis.config import BrainConfig
        from jarvis.skills.registry import SkillRegistry

        calls = []
        cb = lambda name, result: calls.append((name, result))

        class TestBrain(Brain):
            def _chat(self, messages):
                return Message("assistant", "", tool_calls=[
                    ToolCall("t1", "test_skill", {}),
                ])

        registry = SkillRegistry()
        registry.register(type("S", (), {"handler": lambda: "ok", "name": "s"})())
        # Регистрируем навык через Skill.
        from jarvis.skills.registry import Skill
        skill = Skill(name="test_skill", description="t", parameters={}, handler=lambda: "skill_result")
        registry.register(skill)

        brain = TestBrain(BrainConfig(max_tool_iterations=1), registry, on_tool_result=cb)
        brain.ask("test")
        assert len(calls) == 1
        assert calls[0] == ("test_skill", "skill_result")


# ── Event preview_url ────────────────────────────────────────────────────


class TestEventPreviewUrl:
    """Event dataclass поддерживает preview_url."""

    def test_default_empty(self):
        e = Event(State.IDLE)
        assert e.preview_url == ""

    def test_with_preview(self):
        e = Event(State.SPEAKING, "results text", "jarvis", preview_url="https://test.com")
        assert e.preview_url == "https://test.com"
        assert e.text == "results text"


# ── offline_brain rule for open_in_browser ──────────────────────────────


class TestOfflineOpenInBrowser:
    """OfflineBrain понимает 'открой в браузере'."""

    def test_phrase_opens_browser(self):
        from jarvis.brain.offline_brain import match_rule
        result = match_rule("открой в браузере")
        assert result is not None
        assert result[0] == "open_in_browser"

    def test_phrase_show_fully(self):
        from jarvis.brain.offline_brain import match_rule
        result = match_rule("покажи полностью")
        assert result is not None
        assert result[0] == "open_in_browser"

    def test_phrase_open_results(self):
        from jarvis.brain.offline_brain import match_rule
        result = match_rule("открой результаты в браузере")
        assert result is not None
        assert result[0] == "open_in_browser"
