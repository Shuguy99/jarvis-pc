"""Тесты Spotify без обращения к настоящему API."""

from __future__ import annotations

from typing import Any

import pytest

from jarvis.config import SkillsConfig, SpotifyConfig
from jarvis.skills.spotify import SpotifyError, SpotifyPlayer, _credentials


class FakeSpotify:
    """Клиент Spotify с записанными вызовами и управляемыми устройствами."""

    def __init__(self, devices: list[dict[str, Any]] | None = None) -> None:
        self._devices = devices if devices is not None else [{"id": "dev1", "is_active": True}]
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def devices(self) -> dict[str, Any]:
        return {"devices": self._devices}

    def search(self, q: str, type: str, limit: int) -> dict[str, Any]:
        item = {
            "uri": f"spotify:{type}:1",
            "name": "Smoke on the Water",
            "artists": [{"name": "Deep Purple"}],
        }
        return {f"{type}s": {"items": [item]}}

    def start_playback(self, **kwargs: Any) -> None:
        self.calls.append(("start_playback", kwargs))

    def pause_playback(self, **kwargs: Any) -> None:
        self.calls.append(("pause_playback", kwargs))

    def current_playback(self) -> dict[str, Any]:
        return {"item": {"name": "Iron Man", "artists": [{"name": "Black Sabbath"}]}}


def _player(client: FakeSpotify | None, enabled: bool = True) -> SpotifyPlayer:
    """Плеер с подменённым клиентом spotipy."""
    player = SpotifyPlayer(SpotifyConfig(enabled=enabled), SkillsConfig())
    if client is not None:
        player._client = client  # type: ignore[assignment]
    return player


def test_play_track_uses_active_device() -> None:
    """Найденный трек запускается на активном устройстве."""
    client = FakeSpotify()
    assert "Deep Purple — Smoke on the Water" in _player(client).play("smoke on the water")
    assert client.calls == [("start_playback", {"device_id": "dev1", "uris": ["spotify:track:1"]})]


def test_play_playlist_uses_context_uri() -> None:
    """Плейлист запускается через context_uri, а не список треков."""
    client = FakeSpotify()
    _player(client).play("работа", "playlist")
    assert client.calls[0][1]["context_uri"] == "spotify:playlist:1"


def test_no_device_reports_clearly() -> None:
    """Без устройств Spotify ассистент объясняет, что делать."""
    player = _player(FakeSpotify(devices=[]))
    player.config.launch_app = False
    assert "Нет активного устройства" in player.play("что угодно")


def test_disabled_spotify_does_nothing() -> None:
    """Выключенный в конфиге Spotify не трогает API."""
    assert "отключён" in _player(None, enabled=False).play("что угодно")


def test_now_playing() -> None:
    """Текущий трек озвучивается с исполнителем."""
    assert "Black Sabbath — Iron Man" in _player(FakeSpotify()).now_playing()


def test_unknown_control_is_rejected() -> None:
    """Неизвестное действие плеера не отправляется в API."""
    client = FakeSpotify()
    assert "Не знаю действие" in _player(client).control("teleport")
    assert client.calls == []


def test_missing_credentials_raise(monkeypatch: Any) -> None:
    """Без ключей приложения авторизация невозможна."""
    monkeypatch.delenv("SPOTIFY_CLIENT_ID", raising=False)
    monkeypatch.delenv("SPOTIFY_CLIENT_SECRET", raising=False)
    with pytest.raises(SpotifyError, match="SPOTIFY_CLIENT_ID"):
        _credentials()
