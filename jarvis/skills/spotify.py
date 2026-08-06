"""Навыки Spotify: включить конкретный трек, плейлист или альбом голосом."""

from __future__ import annotations

import logging
import os
import time
from typing import TYPE_CHECKING, Any

from ..config import SkillsConfig, SpotifyConfig
from .apps import open_app
from .registry import Skill, object_schema

if TYPE_CHECKING:  # pragma: no cover - spotipy опционален
    from spotipy import Spotify

log = logging.getLogger(__name__)

SCOPE = "user-read-playback-state user-modify-playback-state user-read-currently-playing"
SEARCH_TYPES = ("track", "playlist", "album", "artist")
CONTEXT_TYPES = ("playlist", "album", "artist")
DEVICE_WAIT_S = 8.0
CONTROLS = ("pause", "resume", "next", "previous")


class SpotifyError(RuntimeError):
    """Причина, по которой Spotify недоступен, в понятном виде."""


def _credentials() -> tuple[str, str]:
    """Читает ключи приложения Spotify из окружения."""
    client_id = os.environ.get("SPOTIFY_CLIENT_ID", "")
    client_secret = os.environ.get("SPOTIFY_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        raise SpotifyError(
            "Нужны SPOTIFY_CLIENT_ID и SPOTIFY_CLIENT_SECRET из Spotify Developer "
            "Dashboard, сэр. Задайте их в переменных окружения."
        )
    return client_id, client_secret


class SpotifyPlayer:
    """Тонкая обёртка над spotipy: авторизация, поиск и управление плеером."""

    def __init__(self, config: SpotifyConfig, skills: SkillsConfig) -> None:
        self.config = config
        self._skills = skills
        self._client: Spotify | None = None

    def _api(self) -> Spotify:
        """Создаёт клиента при первом обращении (откроет браузер для входа)."""
        if self._client is not None:
            return self._client
        try:
            import spotipy
            from spotipy.oauth2 import SpotifyOAuth
        except ImportError as exc:
            raise SpotifyError(
                "Модуль spotipy не установлен, сэр. Выполните: pip install spotipy"
            ) from exc
        client_id, client_secret = _credentials()
        auth = SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=self.config.redirect_uri,
            scope=SCOPE,
            cache_path=self.config.cache_path,
            open_browser=True,
        )
        self._client = spotipy.Spotify(auth_manager=auth)
        return self._client

    def _device_id(self, api: Spotify) -> str:
        """Находит активное устройство, при необходимости запустив приложение."""
        for attempt in range(2):
            devices = api.devices().get("devices", [])
            active = next((item for item in devices if item.get("is_active")), None)
            chosen = active or (devices[0] if devices else None)
            if chosen is not None:
                return str(chosen["id"])
            if attempt or not self.config.launch_app:
                break
            open_app(self._skills, "spotify")
            time.sleep(DEVICE_WAIT_S)
        raise SpotifyError(
            "Нет активного устройства Spotify, сэр. Откройте Spotify и включите любой трек."
        )

    def play(self, query: str, kind: str = "track") -> str:
        """Ищет и запускает трек, плейлист, альбом или исполнителя."""
        if not self.config.enabled:
            return "Spotify отключён в конфигурации, сэр."
        kind = kind if kind in SEARCH_TYPES else "track"
        try:
            api = self._api()
            found = api.search(q=query, type=kind, limit=1)
            items = found.get(f"{kind}s", {}).get("items", [])
            if not items:
                return f"В Spotify нет ничего по запросу «{query}», сэр."
            item = items[0]
            device_id = self._device_id(api)
            if kind in CONTEXT_TYPES:
                api.start_playback(device_id=device_id, context_uri=item["uri"])
            else:
                api.start_playback(device_id=device_id, uris=[item["uri"]])
        except SpotifyError as exc:
            return str(exc)
        except Exception as exc:
            log.exception("Ошибка Spotify")
            return f"Spotify отказался выполнять команду: {exc}"
        return f"Включаю {_describe(item, kind)}, сэр."

    def control(self, action: str) -> str:
        """Пауза, продолжение и переключение треков."""
        if not self.config.enabled:
            return "Spotify отключён в конфигурации, сэр."
        if action not in CONTROLS:
            return f"Не знаю действие «{action}», сэр."
        try:
            api = self._api()
            device_id = self._device_id(api)
            if action == "pause":
                api.pause_playback(device_id=device_id)
            elif action == "resume":
                api.start_playback(device_id=device_id)
            elif action == "next":
                api.next_track(device_id=device_id)
            else:
                api.previous_track(device_id=device_id)
        except SpotifyError as exc:
            return str(exc)
        except Exception as exc:
            log.exception("Ошибка Spotify")
            return f"Spotify отказался выполнять команду: {exc}"
        return "Готово, сэр."

    def now_playing(self) -> str:
        """Сообщает, что играет прямо сейчас."""
        if not self.config.enabled:
            return "Spotify отключён в конфигурации, сэр."
        try:
            current = self._api().current_playback()
        except SpotifyError as exc:
            return str(exc)
        except Exception as exc:
            log.exception("Ошибка Spotify")
            return f"Spotify не ответил: {exc}"
        track = (current or {}).get("item")
        if not track:
            return "Сейчас ничего не играет, сэр."
        return f"Играет {_describe(track, 'track')}."


def _describe(item: dict[str, Any], kind: str) -> str:
    """Человеческое название найденного объекта."""
    name = item.get("name", "без названия")
    artists = ", ".join(artist.get("name", "") for artist in item.get("artists", []))
    if kind == "track" and artists:
        return f"{artists} — {name}"
    return name


def build_skills(config: SkillsConfig) -> list[Skill]:
    """Создаёт навыки Spotify, если они включены в конфиге."""
    if not config.spotify.enabled:
        return []
    player = SpotifyPlayer(config.spotify, config)
    return [
        Skill(
            name="spotify_play",
            description=(
                "Включить в Spotify конкретную музыку: трек, плейлист, альбом или исполнителя. "
                "Пример запроса: «Deep Purple Smoke on the Water»."
            ),
            parameters=object_schema(
                {
                    "query": {
                        "type": "string",
                        "description": "Что включить: исполнитель и название",
                    },
                    "kind": {
                        "type": "string",
                        "enum": list(SEARCH_TYPES),
                        "description": "Тип: track, playlist, album или artist",
                    },
                },
                required=["query"],
            ),
            handler=lambda query, kind="track": player.play(query, kind),
        ),
        Skill(
            name="spotify_control",
            description="Управление плеером Spotify: pause, resume, next, previous.",
            parameters=object_schema(
                {
                    "action": {
                        "type": "string",
                        "enum": list(CONTROLS),
                        "description": "Действие плеера",
                    }
                },
                required=["action"],
            ),
            handler=player.control,
        ),
        Skill(
            name="spotify_now_playing",
            description="Узнать, какой трек играет в Spotify сейчас.",
            parameters=object_schema({}),
            handler=player.now_playing,
        ),
    ]
