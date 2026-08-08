from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from jarvis.config import TelegramConfig
from jarvis.skills.telegram_bot import (
    _check_config,
    _parse_mode,
    _tg_request,
    tg_send_message,
    tg_send_document,
    tg_send_photo,
    tg_send_location,
    tg_send_buttons,
    tg_reply,
    tg_forward,
    tg_delete_message,
    tg_edit_message,
    tg_pin_message,
    tg_unpin_message,
    tg_get_chat_info,
    tg_set_commands,
    tg_get_updates,
    tg_me,
    build_skills,
)


def _cfg(**overrides) -> TelegramConfig:
    defaults = {"bot_token": "test_token", "chat_id": "12345"}
    defaults.update(overrides)
    return TelegramConfig(**defaults)


cfg = _cfg()


class TestCheckConfig:
    def test_ok(self):
        assert _check_config(cfg) is None

    def test_no_token(self):
        assert _check_config(_cfg(bot_token="")) is not None

    def test_no_chat_id(self):
        assert _check_config(_cfg(chat_id="")) is not None


class TestParseMode:
    def test_html(self):
        assert _parse_mode(_cfg(parse_mode="HTML")) == "HTML"

    def test_markdown(self):
        assert _parse_mode(_cfg(parse_mode="Markdown")) == "Markdown"

    def test_markdown_v2(self):
        assert _parse_mode(_cfg(parse_mode="MarkdownV2")) == "MarkdownV2"

    def test_invalid(self):
        assert _parse_mode(_cfg(parse_mode="BBCode")) == ""

    def test_empty(self):
        assert _parse_mode(_cfg(parse_mode="")) == ""


class TestTgRequest:
    def test_success(self):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"ok": True, "result": {"id": 1}}).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = lambda s, *a: False
        import jarvis.skills.telegram_bot as tb
        original = tb.urllib.request.urlopen
        tb.urllib.request.urlopen = lambda *a, **kw: mock_resp
        try:
            result = _tg_request(cfg, "getMe")
            assert result == {"id": 1}
        finally:
            tb.urllib.request.urlopen = original

    def test_api_error(self):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"ok": False, "description": "Bad Request"}).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = lambda s, *a: False
        import jarvis.skills.telegram_bot as tb
        original = tb.urllib.request.urlopen
        tb.urllib.request.urlopen = lambda *a, **kw: mock_resp
        try:
            assert _tg_request(cfg, "sendMessage") is None
        finally:
            tb.urllib.request.urlopen = original

    def test_no_token(self):
        assert _tg_request(_cfg(bot_token=""), "getMe") is None

    def test_network_error(self):
        import jarvis.skills.telegram_bot as tb
        original = tb.urllib.request.urlopen
        tb.urllib.request.urlopen = lambda *a, **kw: (_ for _ in ()).throw(OSError("net"))
        try:
            assert _tg_request(cfg, "getMe") is None
        finally:
            tb.urllib.request.urlopen = original


def _mock_api_ok(return_value):
    """Создаёт mock, возвращающий {"ok": True, "result": return_value}."""
    def _mock(req, *a, **kw):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"ok": True, "result": return_value}).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = lambda s, *a: False
        return mock_resp
    return _mock


def _mock_api_true():
    """Mock для API, возвращающих True."""
    def _mock(req, *a, **kw):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"ok": True, "result": True}).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = lambda s, *a: False
        return mock_resp
    return _mock


def _patch_urlopen(mock_fn):
    import jarvis.skills.telegram_bot as tb
    original = tb.urllib.request.urlopen
    tb.urllib.request.urlopen = mock_fn
    return original


# ── tg_send_message ────────────────────────────────────────────────


class TestSendMessage:
    def test_success(self):
        import jarvis.skills.telegram_bot as tb
        original = _patch_urlopen(_mock_api_ok({"message_id": 42}))
        try:
            result = tg_send_message(cfg, "Hello")
            assert "42" in result
        finally:
            tb.urllib.request.urlopen = original

    def test_no_config(self):
        assert "не настроен" in tg_send_message(_cfg(bot_token=""), "x").lower()

    def test_uses_parse_mode(self):
        import jarvis.skills.telegram_bot as tb
        call_data = {}
        def capture(req, *a, **kw):
            nonlocal call_data
            call_data = json.loads(req.data.decode())
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps({"ok": True, "result": {"message_id": 1}}).encode()
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = lambda s, *a: False
            return mock_resp
        original = _patch_urlopen(capture)
        try:
            tg_send_message(_cfg(parse_mode="Markdown"), "Hello")
            assert call_data.get("parse_mode") == "Markdown"
        finally:
            tb.urllib.request.urlopen = original


# ── tg_send_document ───────────────────────────────────────────────


class TestSendDocument:
    def test_success(self, tmp_path):
        f = tmp_path / "report.pdf"
        f.write_bytes(b"PDF content")
        import jarvis.skills.telegram_bot as tb
        original = _patch_urlopen(_mock_api_ok({"message_id": 1}))
        try:
            result = tg_send_document(cfg, str(f))
            assert "report.pdf" in result
        finally:
            tb.urllib.request.urlopen = original

    def test_file_not_found(self):
        assert "не найден" in tg_send_document(cfg, "/nonexistent/file.pdf").lower()

    def test_no_config(self):
        assert "не настроен" in tg_send_document(_cfg(bot_token=""), "/f").lower()


# ── tg_send_photo ───────────────────────────────────────────────────


class TestSendPhoto:
    def test_success(self, tmp_path):
        f = tmp_path / "img.png"
        f.write_bytes(b"PNG")
        import jarvis.skills.telegram_bot as tb
        original = _patch_urlopen(_mock_api_ok({"message_id": 1}))
        try:
            result = tg_send_photo(cfg, str(f))
            assert "отправлено" in result.lower()
        finally:
            tb.urllib.request.urlopen = original

    def test_file_not_found(self):
        assert "не найден" in tg_send_photo(cfg, "/no/img.png").lower()


# ── tg_send_location ────────────────────────────────────────────────


class TestSendLocation:
    def test_success(self):
        import jarvis.skills.telegram_bot as tb
        original = _patch_urlopen(_mock_api_ok({"message_id": 1}))
        try:
            result = tg_send_location(cfg, 55.0, 82.9)
            assert "55.0" in result
            assert "82.9" in result
        finally:
            tb.urllib.request.urlopen = original

    def test_no_config(self):
        assert "не настроен" in tg_send_location(_cfg(bot_token=""), 0, 0).lower()


class TestSendButtons:
    def test_success(self):
        import jarvis.skills.telegram_bot as tb
        original = _patch_urlopen(_mock_api_ok({"message_id": 1}))
        try:
            result = tg_send_buttons(cfg, "Вопрос?", "Да/Нет, Может быть")
            assert "3 кнопк" in result
        finally:
            tb.urllib.request.urlopen = original

    def test_no_buttons(self):
        assert "Укажите кнопки" in tg_send_buttons(cfg, "test", "")

    def test_single_row(self):
        import jarvis.skills.telegram_bot as tb
        original = _patch_urlopen(_mock_api_ok({"message_id": 1}))
        try:
            result = tg_send_buttons(cfg, "Pick one", "A,B,C")
            assert "3 кнопк" in result
        finally:
            tb.urllib.request.urlopen = original

    def test_no_config(self):
        assert "не настроен" in tg_send_buttons(_cfg(bot_token=""), "t", "a").lower()


class TestReply:
    def test_success(self):
        import jarvis.skills.telegram_bot as tb
        original = _patch_urlopen(_mock_api_ok({"message_id": 2}))
        try:
            result = tg_reply(cfg, 42, "ОК")
            assert "42" in result
        finally:
            tb.urllib.request.urlopen = original

    def test_no_config(self):
        assert "не настроен" in tg_reply(_cfg(bot_token=""), 1, "x").lower()


class TestForward:
    def test_success(self):
        import jarvis.skills.telegram_bot as tb
        original = _patch_urlopen(_mock_api_ok({"message_id": 3}))
        try:
            result = tg_forward(cfg, 10, "999")
            assert "999" in result
        finally:
            tb.urllib.request.urlopen = original

    def test_same_chat(self):
        import jarvis.skills.telegram_bot as tb
        original = _patch_urlopen(_mock_api_ok({"message_id": 3}))
        try:
            result = tg_forward(cfg, 10)
            assert "12345" in result
        finally:
            tb.urllib.request.urlopen = original


class TestDeleteMessage:
    def test_success(self):
        import jarvis.skills.telegram_bot as tb
        original = _patch_urlopen(_mock_api_true())
        try:
            result = tg_delete_message(cfg, 99)
            assert "99" in result
            assert "удалено" in result.lower()
        finally:
            tb.urllib.request.urlopen = original

    def test_failure(self):
        import jarvis.skills.telegram_bot as tb
        original = _patch_urlopen(_mock_api_ok(False))
        try:
            result = tg_delete_message(cfg, 99)
            assert "Не удалось" in result
        finally:
            tb.urllib.request.urlopen = original


class TestEditMessage:
    def test_success(self):
        import jarvis.skills.telegram_bot as tb
        original = _patch_urlopen(_mock_api_ok({"message_id": 5}))
        try:
            result = tg_edit_message(cfg, 5, "new text")
            assert "отредактировано" in result.lower()
        finally:
            tb.urllib.request.urlopen = original


class TestPinMessage:
    def test_success(self):
        import jarvis.skills.telegram_bot as tb
        original = _patch_urlopen(_mock_api_true())
        try:
            result = tg_pin_message(cfg, 50)
            assert "закреплено" in result.lower()
        finally:
            tb.urllib.request.urlopen = original


class TestUnpinMessage:
    def test_specific(self):
        import jarvis.skills.telegram_bot as tb
        original = _patch_urlopen(_mock_api_true())
        try:
            result = tg_unpin_message(cfg, 50)
            assert "50" in result
        finally:
            tb.urllib.request.urlopen = original

    def test_all(self):
        import jarvis.skills.telegram_bot as tb
        original = _patch_urlopen(_mock_api_true())
        try:
            result = tg_unpin_message(cfg)
            assert "Все" in result
        finally:
            tb.urllib.request.urlopen = original


class TestGetChatInfo:
    def test_success(self):
        import jarvis.skills.telegram_bot as tb
        chat_data = {
            "title": "Test Chat",
            "type": "group",
            "description": "A test group",
            "username": "testchat",
        }
        original = _patch_urlopen(_mock_api_ok(chat_data))
        try:
            result = tg_get_chat_info(cfg)
            assert "Test Chat" in result
            assert "group" in result
            assert "@testchat" in result
        finally:
            tb.urllib.request.urlopen = original

    def test_private(self):
        import jarvis.skills.telegram_bot as tb
        chat_data = {"title": "User", "type": "private"}
        original = _patch_urlopen(_mock_api_ok(chat_data))
        try:
            result = tg_get_chat_info(cfg)
            assert "private" in result
        finally:
            tb.urllib.request.urlopen = original


class TestSetCommands:
    def test_success(self):
        import jarvis.skills.telegram_bot as tb
        original = _patch_urlopen(_mock_api_true())
        try:
            result = tg_set_commands(cfg)
            assert "5 команд" in result
        finally:
            tb.urllib.request.urlopen = original


class TestGetUpdates:
    def test_success(self):
        updates = [{
            "message": {
                "message_id": 1, "text": "Hello",
                "from": {"first_name": "Ivan", "username": "ivan"},
                "date": 1700000000,
            }
        }]
        import jarvis.skills.telegram_bot as tb
        original = _patch_urlopen(_mock_api_ok(updates))
        try:
            result = tg_get_updates(cfg)
            assert "Hello" in result
            assert "@ivan" in result
            assert "#1" in result
        finally:
            tb.urllib.request.urlopen = original

    def test_empty(self):
        import jarvis.skills.telegram_bot as tb
        original = _patch_urlopen(_mock_api_ok([]))
        try:
            result = tg_get_updates(cfg)
            assert "Нет" in result
        finally:
            tb.urllib.request.urlopen = original


class TestTgMe:
    def test_success(self):
        import jarvis.skills.telegram_bot as tb
        original = _patch_urlopen(_mock_api_ok({"first_name": "Jarvis", "username": "jarvis_bot"}))
        try:
            result = tg_me(cfg)
            assert "Jarvis" in result
            assert "@jarvis_bot" in result
        finally:
            tb.urllib.request.urlopen = original

    def test_no_token(self):
        assert "не настроен" in tg_me(_cfg(bot_token="")).lower()


class TestBuildSkills:
    def test_count(self):
        skills = build_skills(cfg)
        assert len(skills) == 15

    def test_names(self):
        skills = build_skills(cfg)
        names = {s.name for s in skills}
        expected = {
            "tg_send_message", "tg_send_photo", "tg_send_document",
            "tg_send_location", "tg_send_buttons",
            "tg_reply", "tg_forward", "tg_delete_message", "tg_edit_message",
            "tg_pin_message", "tg_unpin_message", "tg_chat_info",
            "tg_set_commands", "tg_get_updates", "tg_me",
        }
        assert names == expected

    def test_all_have_descriptions(self):
        skills = build_skills(cfg)
        for s in skills:
            assert len(s.description) > 10

    def test_send_message_handler(self):
        skills = build_skills(cfg)
        sm = next(s for s in skills if s.name == "tg_send_message")
        assert "text" in sm.parameters.get("required", [])

    def test_delete_message_required(self):
        skills = build_skills(cfg)
        dm = next(s for s in skills if s.name == "tg_delete_message")
        assert "message_id" in dm.parameters.get("required", [])

    def test_disabled_config_returns_same_count(self):
        skills = build_skills(cfg)
        assert len(skills) == 15
