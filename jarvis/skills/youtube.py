"""YouTube / Music: поиск и воспроизведение через yt-dlp + MPV."""

from __future__ import annotations

import logging
import shutil
import subprocess

from ..config import YouTubeConfig
from .registry import Skill, object_schema

log = logging.getLogger(__name__)


def _is_available(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def _search_youtube(query: str) -> str:
    """Ищет на YouTube и возвращает URL первого результата."""
    cmd = [
        "yt-dlp", "--get-url", "--get-id",
        "--default-search", "ytsearch1",
        "--no-playlist",
        "-f", "bestaudio/best",
        query,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=True)
        lines = result.stdout.strip().split("\n")
        if len(lines) >= 2:
            video_id = lines[1]
            return f"https://www.youtube.com/watch?v={video_id}"
        if lines:
            return lines[0]
    except subprocess.TimeoutExpired:
        log.warning("yt-dlp поиск превысил таймаут")
    except Exception as exc:
        log.warning("yt-dlp поиск не удался: %s", exc)
    return ""


def play_youtube(config: YouTubeConfig, query: str) -> str:
    """Ищет и воспроизводит видео/музыку с YouTube через MPV."""
    if not _is_available("mpv"):
        return "MPV плеер не установлен. Установите: apt install mpv или скачайте с mpv.io, сэр."
    if not _is_available("yt-dlp"):
        return "yt-dlp не установлен. Установите: pip install yt-dlp, сэр."
    query = query.strip()
    if not query:
        return "Укажите что воспроизвести, сэр."
    is_url = query.startswith(("http://", "https://", "www."))
    if is_url:
        url = query if query.startswith("http") else "https://" + query
    else:
        url = _search_youtube(query)
        if not url:
            return f"Не нашёл '{query}' на YouTube, сэр."
    cmd = ["mpv"]
    if config.audio_only:
        cmd.append("--no-video")
    cmd.append(f"--volume={config.volume}")
    cmd.append(url)
    try:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        what = "Музыку" if config.audio_only else "Видео"
        return f"{what} воспроизвожу, сэр."
    except Exception as exc:
        return f"Ошибка воспроизведения: {exc}, сэр."


def stop_music() -> str:
    """Останавливает MPV плеер."""
    if not _is_available("pkill"):
        return "Не могу остановить: pkill недоступен, сэр."
    try:
        subprocess.run(["pkill", "-f", "mpv"], check=False, timeout=5)
        return "Воспроизведение остановлено, сэр."
    except Exception as exc:
        return f"Ошибка остановки: {exc}, сэр."


def build_skills(config: YouTubeConfig) -> list[Skill]:
    """Создаёт навыки YouTube / Music."""
    return [
        Skill(
            name="play_music",
            description=(
                "Воспроизвести музыку с YouTube. Можно передать URL или поисковый запрос. "
                "Воспроизводится через MPV плеер (только аудио)."
            ),
            parameters=object_schema(
                {
                    "query": {
                        "type": "string",
                        "description": "URL видео или поисковый запрос (название трека/артиста)",
                    },
                },
                required=["query"],
            ),
            handler=lambda query: play_youtube(config, query),
        ),
        Skill(
            name="stop_music",
            description="Остановить воспроизведение MPV.",
            parameters=object_schema({}),
            handler=stop_music,
        ),
    ]
