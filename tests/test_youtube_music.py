"""Тесты YouTube Music навыков (MPV IPC)."""

from __future__ import annotations

import json
import os
import socket
from unittest.mock import MagicMock, patch

import pytest

from jarvis.skills.youtube_music import (
    _format_time,
    _get_status,
    _is_mpv_running,
    _mpv_command,
    build_skills,
    yt_music_pause,
    yt_music_resume,
    yt_music_seek,
    yt_music_status,
    yt_music_toggle,
    yt_music_volume,
)
from jarvis.skills.registry import Skill


# ── Форматирование времени ─────────────────────────────────────────────


class TestFormatTime:
    def test_zero(self):
        assert _format_time(0) == "0:00"

    def test_seconds_only(self):
        assert _format_time(45) == "0:45"

    def test_minutes_and_seconds(self):
        assert _format_time(125) == "2:05"

    def test_large_value(self):
        assert _format_time(3661) == "61:01"


# ── _is_mpv_running ────────────────────────────────────────────────────


class TestIsMpvRunning:
    @patch("jarvis.skills.youtube_music.os.path.exists", return_value=False)
    def test_no_ipc_file(self, mock_exists):
        assert _is_mpv_running() is False

    @patch("jarvis.skills.youtube_music.os.path.exists", return_value=True)
    @patch("jarvis.skills.youtube_music.shutil.which", return_value=None)
    def test_no_pgrep_no_tasklist(self, mock_which, mock_exists):
        assert _is_mpv_running() is False

    @patch("jarvis.skills.youtube_music.os.path.exists", return_value=True)
    @patch("jarvis.skills.youtube_music.shutil.which", return_value="/usr/bin/pgrep")
    @patch("jarvis.skills.youtube_music.subprocess.run")
    def test_pgrep_finds_mpv(self, mock_run, mock_which, mock_exists):
        mock_run.return_value = MagicMock(returncode=0)
        assert _is_mpv_running() is True

    @patch("jarvis.skills.youtube_music.os.path.exists", return_value=True)
    @patch("jarvis.skills.youtube_music.shutil.which", return_value="/usr/bin/pgrep")
    @patch("jarvis.skills.youtube_music.subprocess.run")
    def test_pgrep_no_mpv(self, mock_run, mock_which, mock_exists):
        mock_run.return_value = MagicMock(returncode=1)
        assert _is_mpv_running() is False

    @patch("jarvis.skills.youtube_music.os.path.exists", return_value=True)
    @patch("jarvis.skills.youtube_music.shutil.which", side_effect=lambda x: None if x == "pkill" else "tasklist")
    @patch("jarvis.skills.youtube_music.subprocess.run")
    def test_windows_tasklist_finds_mpv(self, mock_run, mock_which, mock_exists):
        mock_run.return_value = MagicMock(stdout="mpv.exe  1234", returncode=0)
        assert _is_mpv_running() is True


# ── _mpv_command ───────────────────────────────────────────────────────


class TestMpvCommand:
    @patch("jarvis.skills.youtube_music.os.path.exists", return_value=False)
    def test_no_ipc_returns_none(self, mock_exists):
        assert _mpv_command({"command": ["get_property", "pause"]}) is None

    def test_unix_socket_success(self):
        mock_sock = MagicMock()
        mock_sock.recv.return_value = json.dumps({"data": False}).encode() + b"\n"
        with patch("jarvis.skills.youtube_music.os.path.exists", return_value=True), \
             patch("jarvis.skills.youtube_music.os.name", "posix"), \
             patch("socket.socket", return_value=mock_sock):
            result = _mpv_command({"command": ["get_property", "pause"]})
            assert result == {"data": False}
            mock_sock.connect.assert_called_once()
            mock_sock.sendall.assert_called_once()
            mock_sock.close.assert_called_once()

    def test_unix_socket_error_returns_none(self):
        mock_sock = MagicMock()
        mock_sock.connect.side_effect = ConnectionRefusedError("refused")
        with patch("jarvis.skills.youtube_music.os.path.exists", return_value=True), \
             patch("jarvis.skills.youtube_music.os.name", "posix"), \
             patch("socket.socket", return_value=mock_sock):
            result = _mpv_command({"command": ["get_property", "pause"]})
            assert result is None


# ── Публичные функции (MPV не запущен) ────────────────────────────────


class TestPublicFunctionsNoMpv:
    @patch("jarvis.skills.youtube_music._is_mpv_running", return_value=False)
    def test_status_no_mpv(self, mock_running):
        assert "Ничего не воспроизводится" in yt_music_status()

    @patch("jarvis.skills.youtube_music._is_mpv_running", return_value=False)
    def test_pause_no_mpv(self, mock_running):
        assert "Нечего ставить на паузу" in yt_music_pause()

    @patch("jarvis.skills.youtube_music._is_mpv_running", return_value=False)
    def test_resume_no_mpv(self, mock_running):
        assert "Нечего воспроизводить" in yt_music_resume()

    @patch("jarvis.skills.youtube_music._is_mpv_running", return_value=False)
    def test_toggle_no_mpv(self, mock_running):
        assert "Ничего не играет" in yt_music_toggle()

    @patch("jarvis.skills.youtube_music._is_mpv_running", return_value=False)
    def test_seek_no_mpv(self, mock_running):
        assert "Ничего не воспроизводится" in yt_music_seek(30)

    @patch("jarvis.skills.youtube_music._is_mpv_running", return_value=False)
    def test_volume_no_mpv(self, mock_running):
        assert "MPV не запущен" in yt_music_volume(80)


# ── Публичные функции (MPV запущен) ───────────────────────────────────


class TestPublicFunctionsWithMpv:
    @patch("jarvis.skills.youtube_music._mpv_command")
    @patch("jarvis.skills.youtube_music._is_mpv_running", return_value=True)
    def test_pause_calls_mpv(self, mock_running, mock_cmd):
        assert "На паузе" in yt_music_pause()
        mock_cmd.assert_called_once_with({"command": ["set_property", "pause", True]})

    @patch("jarvis.skills.youtube_music._mpv_command")
    @patch("jarvis.skills.youtube_music._is_mpv_running", return_value=True)
    def test_resume_calls_mpv(self, mock_running, mock_cmd):
        assert "Воспроизвожу" in yt_music_resume()
        mock_cmd.assert_called_once_with({"command": ["set_property", "pause", False]})

    @patch("jarvis.skills.youtube_music._mpv_command")
    @patch("jarvis.skills.youtube_music._is_mpv_running", return_value=True)
    def test_toggle_calls_mpv(self, mock_running, mock_cmd):
        assert "Переключил" in yt_music_toggle()
        mock_cmd.assert_called_once_with({"command": ["cycle", "pause"]})

    @patch("jarvis.skills.youtube_music._mpv_command")
    @patch("jarvis.skills.youtube_music._is_mpv_running", return_value=True)
    def test_seek_forward(self, mock_running, mock_cmd):
        result = yt_music_seek(30)
        assert "вперёд" in result
        assert "30" in result
        mock_cmd.assert_called_once_with({"command": ["seek", 30]})

    @patch("jarvis.skills.youtube_music._mpv_command")
    @patch("jarvis.skills.youtube_music._is_mpv_running", return_value=True)
    def test_seek_backward(self, mock_running, mock_cmd):
        result = yt_music_seek(-10)
        assert "назад" in result
        mock_cmd.assert_called_once_with({"command": ["seek", -10]})

    @patch("jarvis.skills.youtube_music._mpv_command")
    @patch("jarvis.skills.youtube_music._is_mpv_running", return_value=True)
    def test_volume_clamps(self, mock_running, mock_cmd):
        yt_music_volume(300)
        called_cmd = mock_cmd.call_args[0][0]
        assert called_cmd["command"][2] == 200  # clamped to 200

    @patch("jarvis.skills.youtube_music._mpv_command")
    @patch("jarvis.skills.youtube_music._is_mpv_running", return_value=True)
    def test_volume_zero(self, mock_running, mock_cmd):
        yt_music_volume(-10)
        called_cmd = mock_cmd.call_args[0][0]
        assert called_cmd["command"][2] == 0  # clamped to 0


# ── _get_status ────────────────────────────────────────────────────────


class TestGetStatus:
    @patch("jarvis.skills.youtube_music._is_mpv_running", return_value=False)
    def test_no_mpv(self, mock_running):
        assert _get_status() == {"playing": False}

    @patch("jarvis.skills.youtube_music._mpv_command")
    @patch("jarvis.skills.youtube_music._is_mpv_running", return_value=True)
    def test_playing_status(self, mock_running, mock_cmd):
        def side_effect(cmd):
            prop = cmd["command"][1]
            if prop == "pause":
                return {"data": False}
            if prop == "time-pos":
                return {"data": 65.5}
            if prop == "duration":
                return {"data": 200.0}
            if prop == "media-title":
                return {"data": "Test Song"}
            return None

        mock_cmd.side_effect = side_effect
        st = _get_status()
        assert st["playing"] is True
        assert st["time-pos"] == 65.5
        assert st["media-title"] == "Test Song"

    @patch("jarvis.skills.youtube_music._mpv_command")
    @patch("jarvis.skills.youtube_music._is_mpv_running", return_value=True)
    def test_paused_status(self, mock_running, mock_cmd):
        def side_effect(cmd):
            prop = cmd["command"][1]
            if prop == "pause":
                return {"data": True}
            return None

        mock_cmd.side_effect = side_effect
        st = _get_status()
        assert st["playing"] is False


# ── yt_music_status с MPV ─────────────────────────────────────────────


class TestYtMusicStatusWithMpv:
    @patch("jarvis.skills.youtube_music._get_status", return_value={
        "playing": True,
        "time-pos": 90,
        "duration": 180,
        "media-title": "Bohemian Rhapsody",
    })
    @patch("jarvis.skills.youtube_music._is_mpv_running", return_value=True)
    def test_status_playing_with_time(self, mock_running, mock_status):
        result = yt_music_status()
        assert "воспроизведение" in result
        assert "Bohemian Rhapsody" in result
        assert "1:30/3:00" in result

    @patch("jarvis.skills.youtube_music._get_status", return_value={
        "playing": False,
        "media-title": "Song",
    })
    @patch("jarvis.skills.youtube_music._is_mpv_running", return_value=True)
    def test_status_paused_no_time(self, mock_running, mock_status):
        result = yt_music_status()
        assert "пауза" in result
        assert "Song" in result


# ── build_skills ───────────────────────────────────────────────────────


class TestBuildSkills:
    def test_returns_six_skills(self):
        skills = build_skills()
        assert len(skills) == 6

    def test_skill_names(self):
        names = {s.name for s in build_skills()}
        assert names == {
            "yt_music_status", "yt_music_pause", "yt_music_resume",
            "yt_music_toggle", "yt_music_seek", "yt_music_volume",
        }

    def test_all_skills_callable(self):
        for skill in build_skills():
            # Без MPV все возвращают graceful сообщение
            result = skill.handler() if skill.name != "yt_music_seek" else skill.handler(seconds=10)
            assert isinstance(result, str)
            assert len(result) > 0

    def test_tool_specs_valid(self):
        for skill in build_skills():
            spec = skill.to_openai_tool()
            assert spec["type"] == "function"
            assert spec["function"]["parameters"]["type"] == "object"
