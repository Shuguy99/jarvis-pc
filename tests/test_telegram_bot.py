from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from jarvis.config import TelegramConfig
from jarvis.skills.telegram_bot import (
    _build_multipart,
    _check_config,
    _parse_duration,
    _parse_mode,
    _send_media,
    _tg_request,
    tg_answer_callback_query,
    tg_ban_user,
    tg_copy_message,
    tg_delete_message,
    tg_delete_webhook,
    tg_demote_user,
    tg_edit_message,
    tg_export_chat_invite,
    tg_forward,
    tg_get_chat_info,
    tg_get_member_count,
    tg_get_updates,
    tg_get_webhook_info,
    tg_leave_chat,
    tg_me,
    tg_mute_user,
    tg_promote_user,
    tg_reply,
    tg_revoke_chat_invite,
    tg_send_animation,
    tg_send_audio,
    tg_send_buttons,
    tg_send_chat_action,
    tg_send_document,
    tg_send_location,
    tg_send_message,
    tg_send_photo,
    tg_send_poll,
    tg_send_sticker,
    tg_send_video,
    tg_send_video_note,
    tg_send_voice,
    tg_set_chat_description,
    tg_set_chat_title,
    tg_set_commands,
    tg_stop_poll,
    tg_unban_user,
    tg_unmute_user,
    tg_unpin_message,
    tg_pin_message,
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


# ══════════════════════════════════════════════════════════════════
# НОВЫЕ ТЕСТЫ — усиление Telegram-бота
# ══════════════════════════════════════════════════════════════════


# ── Хелперы ────────────────────────────────────────────────────────


class TestBuildMultipart:
    def test_text_fields(self):
        body, ct = _build_multipart({"chat_id": "123"}, {})
        assert b"chat_id" in body
        assert b"123" in body
        assert "multipart/form-data" in ct

    def test_file_fields(self):
        body, ct = _build_multipart({}, {"photo": ("img.png", b"\x89PNG", "image/png")})
        assert b"img.png" in body
        assert b"\x89PNG" in body
        assert b"image/png" in body

    def test_mixed_fields(self):
        body, ct = _build_multipart(
            {"chat_id": "123"},
            {"document": ("f.txt", b"hello", "text/plain")},
        )
        assert b"chat_id" in body
        assert b"f.txt" in body

    def test_boundary_format(self):
        body, ct = _build_multipart({}, {})
        assert b"----JarvisBoundary7394--" in body


class TestParseDuration:
    def test_seconds(self):
        assert _parse_duration("30s") == 30

    def test_minutes(self):
        assert _parse_duration("5m") == 300

    def test_hours(self):
        assert _parse_duration("1h") == 3600

    def test_days(self):
        assert _parse_duration("7d") == 604800

    def test_plain_number(self):
        assert _parse_duration("120") == 120

    def test_empty(self):
        assert _parse_duration("") is None

    def test_invalid(self):
        assert _parse_duration("abc") is None

    def test_whitespace(self):
        assert _parse_duration("  5m  ") == 300

    def test_uppercase(self):
        assert _parse_duration("1H") == 3600


# ── tg_send_voice ──────────────────────────────────────────────────


class TestSendVoice:
    def test_success(self, tmp_path):
        f = tmp_path / "voice.ogg"
        f.write_bytes(b"OGG audio")
        import jarvis.skills.telegram_bot as tb
        original = _patch_urlopen(_mock_api_ok({"message_id": 1}))
        try:
            result = tg_send_voice(cfg, str(f))
            assert "голосов" in result.lower()
        finally:
            tb.urllib.request.urlopen = original

    def test_not_found(self):
        assert "не найден" in tg_send_voice(cfg, "/no/voice.ogg").lower()

    def test_no_config(self):
        assert "не настроен" in tg_send_voice(_cfg(bot_token=""), "/f").lower()


# ── tg_send_video ──────────────────────────────────────────────────


class TestSendVideo:
    def test_success(self, tmp_path):
        f = tmp_path / "video.mp4"
        f.write_bytes(b"MP4")
        import jarvis.skills.telegram_bot as tb
        original = _patch_urlopen(_mock_api_ok({"message_id": 1}))
        try:
            result = tg_send_video(cfg, str(f))
            assert "видео" in result.lower()
        finally:
            tb.urllib.request.urlopen = original

    def test_not_found(self):
        assert "не найден" in tg_send_video(cfg, "/no/v.mp4").lower()


# ── tg_send_audio ──────────────────────────────────────────────────


class TestSendAudio:
    def test_success(self, tmp_path):
        f = tmp_path / "song.mp3"
        f.write_bytes(b"ID3")
        import jarvis.skills.telegram_bot as tb
        original = _patch_urlopen(_mock_api_ok({"message_id": 1}))
        try:
            result = tg_send_audio(cfg, str(f))
            assert "аудио" in result.lower()
        finally:
            tb.urllib.request.urlopen = original

    def test_not_found(self):
        assert "не найден" in tg_send_audio(cfg, "/no/a.mp3").lower()


# ── tg_send_sticker ────────────────────────────────────────────────


class TestSendSticker:
    def test_by_file_id(self):
        import jarvis.skills.telegram_bot as tb
        original = _patch_urlopen(_mock_api_ok({"message_id": 1}))
        try:
            result = tg_send_sticker(cfg, file_id="CAACAgIAAxkBAAI...")
            assert "отправлен" in result.lower()
        finally:
            tb.urllib.request.urlopen = original

    def test_by_file_path(self, tmp_path):
        f = tmp_path / "sticker.webp"
        f.write_bytes(b"WEBP")
        import jarvis.skills.telegram_bot as tb
        original = _patch_urlopen(_mock_api_ok({"message_id": 1}))
        try:
            result = tg_send_sticker(cfg, file_path=str(f))
            assert "отправлен" in result.lower()
        finally:
            tb.urllib.request.urlopen = original

    def test_no_params(self):
        result = tg_send_sticker(cfg)
        assert "Укажите" in result

    def test_no_config(self):
        assert "не настроен" in tg_send_sticker(_cfg(bot_token="")).lower()


# ── tg_send_animation ──────────────────────────────────────────────


class TestSendAnimation:
    def test_success(self, tmp_path):
        f = tmp_path / "anim.gif"
        f.write_bytes(b"GIF89a")
        import jarvis.skills.telegram_bot as tb
        original = _patch_urlopen(_mock_api_ok({"message_id": 1}))
        try:
            result = tg_send_animation(cfg, str(f))
            assert "анимаци" in result.lower()
        finally:
            tb.urllib.request.urlopen = original

    def test_not_found(self):
        assert "не найден" in tg_send_animation(cfg, "/no/a.gif").lower()


# ── tg_send_video_note ─────────────────────────────────────────────


class TestSendVideoNote:
    def test_success(self, tmp_path):
        f = tmp_path / "note.mp4"
        f.write_bytes(b"MP4")
        import jarvis.skills.telegram_bot as tb
        original = _patch_urlopen(_mock_api_ok({"message_id": 1}))
        try:
            result = tg_send_video_note(cfg, str(f))
            assert "видеосообщ" in result.lower()
        finally:
            tb.urllib.request.urlopen = original

    def test_not_found(self):
        assert "не найден" in tg_send_video_note(cfg, "/no/n.mp4").lower()


# ── tg_send_poll ───────────────────────────────────────────────────


class TestSendPoll:
    def test_success(self):
        import jarvis.skills.telegram_bot as tb
        original = _patch_urlopen(_mock_api_ok({"message_id": 1}))
        try:
            result = tg_send_poll(cfg, "Кто лучший?", "Джарвис, Тони, Брюс")
            assert "опрос" in result.lower()
            assert "3 вариант" in result
        finally:
            tb.urllib.request.urlopen = original

    def test_quiz(self):
        import jarvis.skills.telegram_bot as tb
        original = _patch_urlopen(_mock_api_ok({"message_id": 1}))
        try:
            result = tg_send_poll(cfg, "2+2?", "3, 4, 5", is_quiz=True)
            assert "викторин" in result.lower()
        finally:
            tb.urllib.request.urlopen = original

    def test_too_few_options(self):
        result = tg_send_poll(cfg, "Q?", "Один")
        assert "минимум 2" in result.lower()

    def test_too_many_options(self):
        opts = ",".join(str(i) for i in range(12))
        result = tg_send_poll(cfg, "Q?", opts)
        assert "максимум 10" in result.lower()

    def test_no_config(self):
        assert "не настроен" in tg_send_poll(_cfg(bot_token=""), "Q?", "A,B").lower()


class TestStopPoll:
    def test_success(self):
        import jarvis.skills.telegram_bot as tb
        original = _patch_urlopen(_mock_api_ok({"id": "poll1"}))
        try:
            result = tg_stop_poll(cfg, 42)
            assert "42" in result
            assert "остановлен" in result.lower()
        finally:
            tb.urllib.request.urlopen = original

    def test_failure(self):
        import jarvis.skills.telegram_bot as tb
        original = _patch_urlopen(_mock_api_ok(None))
        try:
            result = tg_stop_poll(cfg, 42)
            assert "Не удалось" in result
        finally:
            tb.urllib.request.urlopen = original


# ── tg_answer_callback_query ───────────────────────────────────────


class TestAnswerCallbackQuery:
    def test_success(self):
        import jarvis.skills.telegram_bot as tb
        original = _patch_urlopen(_mock_api_true())
        try:
            result = tg_answer_callback_query(cfg, "cb123", "Принято!")
            assert "callback" in result.lower()
        finally:
            tb.urllib.request.urlopen = original

    def test_no_token(self):
        assert "не настроен" in tg_answer_callback_query(_cfg(bot_token=""), "x").lower()


# ── tg_send_chat_action ────────────────────────────────────────────


class TestSendChatAction:
    def test_typing(self):
        import jarvis.skills.telegram_bot as tb
        original = _patch_urlopen(_mock_api_true())
        try:
            result = tg_send_chat_action(cfg, "typing")
            assert "печатает" in result.lower()
        finally:
            tb.urllib.request.urlopen = original

    def test_upload_photo(self):
        import jarvis.skills.telegram_bot as tb
        original = _patch_urlopen(_mock_api_true())
        try:
            result = tg_send_chat_action(cfg, "upload_photo")
            assert "отправляет фото" in result.lower()
        finally:
            tb.urllib.request.urlopen = original

    def test_invalid_action(self):
        result = tg_send_chat_action(cfg, "fly")
        assert "Неизвестное" in result

    def test_no_config(self):
        assert "не настроен" in tg_send_chat_action(_cfg(bot_token=""), "typing").lower()


# ── tg_ban_user ────────────────────────────────────────────────────


class TestBanUser:
    def test_permanent(self):
        import jarvis.skills.telegram_bot as tb
        original = _patch_urlopen(_mock_api_true())
        try:
            result = tg_ban_user(cfg, 123456)
            assert "123456" in result
            assert "навсегда" in result.lower()
        finally:
            tb.urllib.request.urlopen = original

    def test_temporary(self):
        import jarvis.skills.telegram_bot as tb
        original = _patch_urlopen(_mock_api_true())
        try:
            result = tg_ban_user(cfg, 123456, "1h")
            assert "123456" in result
            assert "1h" in result
        finally:
            tb.urllib.request.urlopen = original

    def test_no_config(self):
        assert "не настроен" in tg_ban_user(_cfg(bot_token=""), 1).lower()


class TestUnbanUser:
    def test_success(self):
        import jarvis.skills.telegram_bot as tb
        original = _patch_urlopen(_mock_api_true())
        try:
            result = tg_unban_user(cfg, 123456)
            assert "разбанен" in result.lower()
        finally:
            tb.urllib.request.urlopen = original

    def test_no_config(self):
        assert "не настроен" in tg_unban_user(_cfg(bot_token=""), 1).lower()


# ── tg_mute_user ───────────────────────────────────────────────────


class TestMuteUser:
    def test_permanent(self):
        import jarvis.skills.telegram_bot as tb
        original = _patch_urlopen(_mock_api_true())
        try:
            result = tg_mute_user(cfg, 123456)
            assert "замьючен" in result.lower()
            assert "навсегда" in result.lower()
        finally:
            tb.urllib.request.urlopen = original

    def test_temporary(self):
        import jarvis.skills.telegram_bot as tb
        original = _patch_urlopen(_mock_api_true())
        try:
            result = tg_mute_user(cfg, 123456, "30m")
            assert "30m" in result
        finally:
            tb.urllib.request.urlopen = original

    def test_no_config(self):
        assert "не настроен" in tg_mute_user(_cfg(bot_token=""), 1).lower()


class TestUnmuteUser:
    def test_success(self):
        import jarvis.skills.telegram_bot as tb
        original = _patch_urlopen(_mock_api_true())
        try:
            result = tg_unmute_user(cfg, 123456)
            assert "размьючен" in result.lower()
        finally:
            tb.urllib.request.urlopen = original

    def test_no_config(self):
        assert "не настроен" in tg_unmute_user(_cfg(bot_token=""), 1).lower()


# ── tg_promote_user / tg_demote_user ────────────────────────────────


class TestPromoteUser:
    def test_success(self):
        import jarvis.skills.telegram_bot as tb
        original = _patch_urlopen(_mock_api_true())
        try:
            result = tg_promote_user(cfg, 123456)
            assert "повышен" in result.lower()
            assert "администратор" in result.lower()
        finally:
            tb.urllib.request.urlopen = original

    def test_no_config(self):
        assert "не настроен" in tg_promote_user(_cfg(bot_token=""), 1).lower()


class TestDemoteUser:
    def test_success(self):
        import jarvis.skills.telegram_bot as tb
        original = _patch_urlopen(_mock_api_true())
        try:
            result = tg_demote_user(cfg, 123456)
            assert "снят" in result.lower()
        finally:
            tb.urllib.request.urlopen = original

    def test_no_config(self):
        assert "не настроен" in tg_demote_user(_cfg(bot_token=""), 1).lower()


# ── tg_set_chat_title / tg_set_chat_description ────────────────────


class TestSetChatTitle:
    def test_success(self):
        import jarvis.skills.telegram_bot as tb
        original = _patch_urlopen(_mock_api_true())
        try:
            result = tg_set_chat_title(cfg, "New Title")
            assert "New Title" in result
            assert "изменено" in result.lower()
        finally:
            tb.urllib.request.urlopen = original

    def test_empty_title(self):
        result = tg_set_chat_title(cfg, "")
        assert "Укажите" in result

    def test_no_config(self):
        assert "не настроен" in tg_set_chat_title(_cfg(bot_token=""), "X").lower()


class TestSetChatDescription:
    def test_success(self):
        import jarvis.skills.telegram_bot as tb
        original = _patch_urlopen(_mock_api_true())
        try:
            result = tg_set_chat_description(cfg, "A cool chat")
            assert "обновлено" in result.lower()
        finally:
            tb.urllib.request.urlopen = original

    def test_no_config(self):
        assert "не настроен" in tg_set_chat_description(_cfg(bot_token=""), "X").lower()


# ── tg_leave_chat ──────────────────────────────────────────────────


class TestLeaveChat:
    def test_success(self):
        import jarvis.skills.telegram_bot as tb
        original = _patch_urlopen(_mock_api_true())
        try:
            result = tg_leave_chat(cfg)
            assert "покинул" in result.lower()
        finally:
            tb.urllib.request.urlopen = original

    def test_no_config(self):
        assert "не настроен" in tg_leave_chat(_cfg(bot_token="")).lower()


# ── tg_copy_message ────────────────────────────────────────────────


class TestCopyMessage:
    def test_success(self):
        import jarvis.skills.telegram_bot as tb
        original = _patch_urlopen(_mock_api_ok({"message_id": 77}))
        try:
            result = tg_copy_message(cfg, 50, "999")
            assert "77" in result
            assert "999" in result
        finally:
            tb.urllib.request.urlopen = original

    def test_same_chat(self):
        import jarvis.skills.telegram_bot as tb
        original = _patch_urlopen(_mock_api_ok({"message_id": 77}))
        try:
            result = tg_copy_message(cfg, 50)
            assert "12345" in result
        finally:
            tb.urllib.request.urlopen = original

    def test_no_config(self):
        assert "не настроен" in tg_copy_message(_cfg(bot_token=""), 1).lower()


# ── tg_get_member_count ────────────────────────────────────────────


class TestGetMemberCount:
    def test_success(self):
        import jarvis.skills.telegram_bot as tb
        original = _patch_urlopen(_mock_api_ok(42))
        try:
            result = tg_get_member_count(cfg)
            assert "42" in result
            assert "участник" in result.lower()
        finally:
            tb.urllib.request.urlopen = original

    def test_failure(self):
        import jarvis.skills.telegram_bot as tb
        original = _patch_urlopen(_mock_api_ok(None))
        try:
            result = tg_get_member_count(cfg)
            assert "Не удалось" in result
        finally:
            tb.urllib.request.urlopen = original

    def test_no_config(self):
        assert "не настроен" in tg_get_member_count(_cfg(bot_token="")).lower()


# ── tg_delete_webhook ──────────────────────────────────────────────


class TestDeleteWebhook:
    def test_success(self):
        import jarvis.skills.telegram_bot as tb
        original = _patch_urlopen(_mock_api_true())
        try:
            result = tg_delete_webhook(cfg)
            assert "вебхук" in result.lower()
            assert "удалён" in result.lower()
        finally:
            tb.urllib.request.urlopen = original

    def test_no_token(self):
        assert "не настроен" in tg_delete_webhook(_cfg(bot_token="")).lower()


# ── tg_get_webhook_info ────────────────────────────────────────────


class TestGetWebhookInfo:
    def test_no_webhook(self):
        import jarvis.skills.telegram_bot as tb
        original = _patch_urlopen(_mock_api_ok({"url": "", "has_custom_certificate": False, "pending_update_count": 0}))
        try:
            result = tg_get_webhook_info(cfg)
            assert "не установлен" in result.lower()
        finally:
            tb.urllib.request.urlopen = original

    def test_with_webhook(self):
        import jarvis.skills.telegram_bot as tb
        info = {"url": "https://example.com/webhook", "has_custom_certificate": True, "pending_update_count": 3}
        original = _patch_urlopen(_mock_api_ok(info))
        try:
            result = tg_get_webhook_info(cfg)
            assert "https://example.com/webhook" in result
            assert "3" in result
        finally:
            tb.urllib.request.urlopen = original

    def test_no_token(self):
        assert "не настроен" in tg_get_webhook_info(_cfg(bot_token="")).lower()


# ── tg_export_chat_invite ──────────────────────────────────────────


class TestExportChatInvite:
    def test_success(self):
        import jarvis.skills.telegram_bot as tb
        original = _patch_urlopen(_mock_api_ok("https://t.me/joinchat/abc123"))
        try:
            result = tg_export_chat_invite(cfg)
            assert "https://t.me" in result
        finally:
            tb.urllib.request.urlopen = original

    def test_no_config(self):
        assert "не настроен" in tg_export_chat_invite(_cfg(bot_token="")).lower()


class TestRevokeChatInvite:
    def test_success(self):
        import jarvis.skills.telegram_bot as tb
        original = _patch_urlopen(_mock_api_ok({"invite_link": "https://t.me/joinchat/abc123"}))
        try:
            result = tg_revoke_chat_invite(cfg, "https://t.me/joinchat/abc123")
            assert "отозвана" in result.lower()
        finally:
            tb.urllib.request.urlopen = original

    def test_no_config(self):
        assert "не настроен" in tg_revoke_chat_invite(_cfg(bot_token=""), "x").lower()


# ── _send_media хелпер ─────────────────────────────────────────────


class TestSendMedia:
    def test_success(self, tmp_path):
        f = tmp_path / "test.mp3"
        f.write_bytes(b"ID3")
        import jarvis.skills.telegram_bot as tb
        original = _patch_urlopen(_mock_api_ok({"message_id": 1}))
        try:
            result = _send_media(cfg, "sendAudio", "audio", str(f))
            assert "test.mp3" in result
        finally:
            tb.urllib.request.urlopen = original

    def test_not_found(self):
        assert "не найден" in _send_media(cfg, "sendAudio", "audio", "/no/file").lower()

    def test_no_config(self):
        assert "не настроен" in _send_media(_cfg(bot_token=""), "sendAudio", "audio", "/f").lower()


# ── build_skills ───────────────────────────────────────────────────


class TestBuildSkills:
    def test_count(self):
        skills = build_skills(cfg)
        assert len(skills) == 40

    def test_names(self):
        skills = build_skills(cfg)
        names = {s.name for s in skills}
        expected_original = {
            "tg_send_message", "tg_send_photo", "tg_send_document",
            "tg_send_location", "tg_send_buttons",
            "tg_reply", "tg_forward", "tg_delete_message", "tg_edit_message",
            "tg_pin_message", "tg_unpin_message", "tg_chat_info",
            "tg_set_commands", "tg_get_updates", "tg_me",
        }
        expected_new = {
            "tg_send_voice", "tg_send_video", "tg_send_audio",
            "tg_send_sticker", "tg_send_animation", "tg_send_video_note",
            "tg_send_poll", "tg_stop_poll",
            "tg_answer_callback_query", "tg_send_chat_action",
            "tg_copy_message",
            "tg_set_chat_title", "tg_set_chat_description", "tg_leave_chat",
            "tg_ban_user", "tg_unban_user", "tg_mute_user", "tg_unmute_user",
            "tg_promote_user", "tg_demote_user",
            "tg_get_member_count",
            "tg_delete_webhook", "tg_get_webhook_info",
            "tg_export_chat_invite", "tg_revoke_chat_invite",
        }
        assert expected_original.issubset(names)
        assert expected_new.issubset(names)

    def test_all_have_descriptions(self):
        skills = build_skills(cfg)
        for s in skills:
            assert len(s.description) > 10, f"{s.name} description too short"

    def test_send_message_handler(self):
        skills = build_skills(cfg)
        sm = next(s for s in skills if s.name == "tg_send_message")
        assert "text" in sm.parameters.get("required", [])

    def test_delete_message_required(self):
        skills = build_skills(cfg)
        dm = next(s for s in skills if s.name == "tg_delete_message")
        assert "message_id" in dm.parameters.get("required", [])

    def test_poll_required(self):
        skills = build_skills(cfg)
        p = next(s for s in skills if s.name == "tg_send_poll")
        req = p.parameters.get("required", [])
        assert "question" in req
        assert "options" in req

    def test_ban_user_required(self):
        skills = build_skills(cfg)
        b = next(s for s in skills if s.name == "tg_ban_user")
        assert "user_id" in b.parameters.get("required", [])

    def test_copy_message_required(self):
        skills = build_skills(cfg)
        c = next(s for s in skills if s.name == "tg_copy_message")
        assert "message_id" in c.parameters.get("required", [])

    def test_chat_action_required(self):
        skills = build_skills(cfg)
        a = next(s for s in skills if s.name == "tg_send_chat_action")
        assert "action" in a.parameters.get("required", [])

    def test_sticker_params(self):
        skills = build_skills(cfg)
        st = next(s for s in skills if s.name == "tg_send_sticker")
        props = st.parameters.get("properties", st.parameters)
        assert "file_id" in props
        assert "file_path" in props
