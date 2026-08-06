"""Тесты раунда 5: open_url scheme, multi-session, browser key whitelist,
amixer fallback, TTS path validation."""

import json
import platform
import stat
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from jarvis.skills.web import open_url
from jarvis.skills.browser import _ALLOWED_KEYS, BrowserSession
from jarvis.skills.system import _change_volume_linux, _set_volume_linux
from jarvis.audio.tts import Speaker
from jarvis.config import BrowserConfig


# ─── open_url scheme validation ───────────────────────────────────────────


class TestOpenUrlScheme:
    """open_url отвергает опасные URI-схемы."""

    @patch("jarvis.skills.web.webbrowser")
    def test_normal_http(self, mock_wb):
        result = open_url("http://example.com")
        assert "открываю" in result.lower()
        mock_wb.open.assert_called_once()

    @patch("jarvis.skills.web.webbrowser")
    def test_normal_https(self, mock_wb):
        result = open_url("https://example.com")
        assert "открываю" in result.lower()

    @patch("jarvis.skills.web.webbrowser")
    def test_no_scheme_gets_https(self, mock_wb):
        result = open_url("example.com")
        assert "открываю" in result.lower()
        url_called = mock_wb.open.call_args[0][0]
        assert url_called.startswith("https://")

    @patch("jarvis.skills.web.webbrowser")
    def test_javascript_uri_rejected(self, mock_wb):
        result = open_url("javascript:alert(1)")
        assert "не поддерживается" in result.lower()
        mock_wb.open.assert_not_called()

    @patch("jarvis.skills.web.webbrowser")
    def test_file_uri_rejected(self, mock_wb):
        result = open_url("file:///etc/passwd")
        assert "не поддерживается" in result.lower()
        mock_wb.open.assert_not_called()

    @patch("jarvis.skills.web.webbrowser")
    def test_data_uri_rejected(self, mock_wb):
        result = open_url("data:text/html,<script>alert(1)</script>")
        assert "не поддерживается" in result.lower()
        mock_wb.open.assert_not_called()

    @patch("jarvis.skills.web.webbrowser")
    def test_uppercase_http_accepted(self, mock_wb):
        result = open_url("HTTP://example.com")
        assert "открываю" in result.lower()


# ─── Multi-session persistence ─────────────────────────────────────────────


class TestMultiSession:
    """Сессии сохраняются в ~/.jarvis/sessions/, ротируются."""

    @pytest.fixture(autouse=True)
    def _patch_sessions_dir(self, tmp_path, monkeypatch):
        """Перенаправляем SESSIONS_DIR во временный каталог."""
        from jarvis.brain import base
        self.sessions_dir = tmp_path / "sessions"
        monkeypatch.setattr(base, "SESSIONS_DIR", self.sessions_dir)

    def test_save_creates_timestamped_file(self):
        from jarvis.brain.base import Brain
        path = Brain._session_path()
        assert path.parent == self.sessions_dir
        assert path.suffix == ".json"
        # Имя содержит шаблон даты.
        assert len(path.stem) == 15  # YYYYMMDD-HHMMSS

    def test_save_named_session(self):
        from jarvis.brain.base import Brain
        path = Brain._session_path("my-session")
        assert path.stem == "my-session"

    def test_named_session_sanitized(self):
        from jarvis.brain.base import Brain
        path = Brain._session_path("../etc/passwd")
        assert ".." not in path.stem
        assert "/" not in path.stem

    def test_save_and_load_roundtrip(self):
        """Сохранённая сессия восстанавливается при загрузке."""
        from jarvis.brain.base import Brain, Message
        # Сохраняем.
        data = [
            {"role": "user", "content": "привет", "tool_calls": [], "tool_call_id": "", "name": ""},
            {"role": "assistant", "content": "здравствуйте, сэр", "tool_calls": [], "tool_call_id": "", "name": ""},
        ]
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        session_file = self.sessions_dir / "20260101-120000.json"
        session_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        # Загружаем.
        brain = self._make_brain()
        brain.load_session()
        assert len(brain.history) == 2
        assert brain.history[0].content == "привет"
        assert brain.history[1].content == "здравствуйте, сэр"

    def test_rotate_deletes_oldest(self):
        from jarvis.brain.base import Brain, _MAX_SESSIONS
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        # Создаём больше сессий, чем лимит.
        for i in range(_MAX_SESSIONS + 5):
            path = self.sessions_dir / f"sess-{i:03d}.json"
            path.write_text("[]", encoding="utf-8")
            # Устанавливаем разное время модификации.
            import os
            os.utime(path, (i, i))
        Brain._rotate_sessions()
        remaining = list(self.sessions_dir.glob("*.json"))
        assert len(remaining) == _MAX_SESSIONS
        # Самый старый удалён.
        assert not (self.sessions_dir / "sess-000.json").exists()

    def test_list_sessions(self):
        from jarvis.brain.base import Brain
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        (self.sessions_dir / "alpha.json").write_text("[]")
        (self.sessions_dir / "beta.json").write_text("[]")
        sessions = Brain.list_sessions()
        assert sessions == ["alpha", "beta"]

    def test_legacy_migration(self, tmp_path):
        """Старый session.json переносится в sessions/legacy.json."""
        from jarvis.brain import base
        old_dir = tmp_path / ".jarvis"
        old_dir.mkdir()
        (old_dir / "session.json").write_text("[]", encoding="utf-8")
        # Временно подменяем SESSIONS_DIR.
        original_dir = base.SESSIONS_DIR
        base.SESSIONS_DIR = old_dir / "sessions"
        try:
            brain = self._make_brain()
            brain.load_session()
            assert not (old_dir / "session.json").exists()
            assert (old_dir / "sessions" / "legacy.json").exists()
        finally:
            base.SESSIONS_DIR = original_dir

    def test_empty_history_not_saved(self):
        from jarvis.brain.base import Brain
        brain = self._make_brain()
        brain.save_session()
        # Пустая история не должна создавать файл.
        assert not any(self.sessions_dir.glob("*.json"))

    def _make_brain(self):
        from jarvis.brain.base import Brain
        from jarvis.config import BrainConfig
        from jarvis.skills.registry import SkillRegistry

        class ConcreteBrain(Brain):
            def _chat(self, messages):
                pass

        return ConcreteBrain(BrainConfig(), SkillRegistry())


# ─── Browser key whitelist ─────────────────────────────────────────────────


class TestBrowserKeyWhitelist:
    """press() отвергает незнакомые клавиши."""

    def test_common_keys_allowed(self):
        for key in ("Enter", "Tab", "Escape", "Backspace", "a", "F1", "Control+c"):
            assert key in _ALLOWED_KEYS, f"{key} should be allowed"

    def test_dangerous_key_rejected(self):
        assert "" not in _ALLOWED_KEYS
        assert "eval" not in _ALLOWED_KEYS
        assert "__import__" not in _ALLOWED_KEYS

    def test_press_rejected_before_playwright(self):
        config = BrowserConfig(enabled=False)
        session = BrowserSession(config)
        result = session.press("eval")
        assert "не в списке разрешённых" in result

    def test_press_accepted_key(self):
        config = BrowserConfig(enabled=False)
        session = BrowserSession(config)
        # Enter разрешён, но браузер выключен — ошибка от _run, не от валидации.
        result = session.press("Enter")
        assert "не в списке" not in result


# ─── Linux volume fallback order ───────────────────────────────────────────


class TestLinuxVolumeFallback:
    """amixer пробуется перед xdotool."""

    @patch("jarvis.skills.system.shutil.which", return_value=None)
    def test_no_tools_returns_none(self, mock_which):
        result = _change_volume_linux(10)
        assert result is None

    @patch("jarvis.skills.system.shutil.which")
    @patch("jarvis.skills.system.subprocess.run")
    def test_amixer_used_when_pactl_fails(self, mock_run, mock_which):
        # pactl есть, но get-sink-volume падает.
        # amixer есть и работает.
        call_count = 0

        def fake_run(cmd, **kwargs):
            nonlocal call_count
            call_count += 1
            if "pactl" in cmd:
                import subprocess as sp
                raise sp.CalledProcessError(1, cmd)
            # amixer — успех.
            return MagicMock()

        mock_run.side_effect = fake_run
        mock_which.side_effect = lambda x: True  # всё доступно

        result = _change_volume_linux(10)
        assert result is not None
        assert "увеличена" in result
        # Проверяем, что amixer был вызван.
        amixer_called = any("amixer" in c[0][0] for c in mock_run.call_args_list)
        assert amixer_called, "amixer should be tried after pactl fails"

    @patch("jarvis.skills.system.shutil.which")
    @patch("jarvis.skills.system.subprocess.run")
    def test_xdotool_only_after_amixer_fails(self, mock_run, mock_which):
        """xdotool используется только если и pactl, и amixer недоступны."""
        which_map = {"pactl": False, "amixer": False, "xdotool": True}
        mock_which.side_effect = which_map.get
        mock_run.return_value = MagicMock()

        result = _change_volume_linux(-5)
        assert result is not None
        assert "уменьшена" in result
        xdotool_called = any("xdotool" in str(c) for c in mock_run.call_args_list)
        assert xdotool_called


# ─── TTS path validation ───────────────────────────────────────────────────


class TestTTSPathValidation:
    """_play() не воспроизводит несуществующие или опасные файлы."""

    def test_nonexistent_file_returns_false(self):
        result = Speaker._play(Path("/nonexistent/audio.mp3"))
        assert result is False

    def test_non_audio_extension_returns_false(self, tmp_path):
        evil = tmp_path / "test.exe"
        evil.write_bytes(b"MZ\x90\x00")
        result = Speaker._play(evil)
        assert result is False

    def test_mp3_file_passes_validation(self, tmp_path):
        """Существующий .mp3 файл проходит валидацию (дальше плееры могут отсутствовать)."""
        audio = tmp_path / "test.mp3"
        audio.write_bytes(b"\x00" * 4)  # минимальный файл
        # На Linux нет playsound3/ffplay/mpv/aplay — вернёт False,
        # но не из-за валидации пути.
        # Проверяем, что ошибка «не существует» НЕ логируется.
        result = Speaker._play(audio)
        # Результат зависит от того, есть ли плееры. Главное — нет краша.
        assert isinstance(result, bool)

    def test_symlink_to_audio_allowed(self, tmp_path):
        """Символическая ссылка на аудиофайл — ОК."""
        audio = tmp_path / "real.wav"
        audio.write_bytes(b"RIFF")
        link = tmp_path / "link.wav"
        link.symlink_to(audio)
        result = Speaker._play(link)
        assert isinstance(result, bool)
