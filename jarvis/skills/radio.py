"""Интернет-радио через MPV."""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

from .registry import Skill, object_schema

log = logging.getLogger(__name__)

_STATIONS: dict[str, dict[str, str]] = {
    "record": {
        "name": "Record Online",
        "url": "https://radiorecord.host/recording128.mp3",
    },
    "record_dance": {
        "name": "Record Dance",
        "url": "https://radiorecord.host/dance128.mp3",
    },
    "record_chill": {
        "name": "Record Chill-Out",
        "url": "https://radiorecord.host/chillout128.mp3",
    },
    "europa_plus": {
        "name": "Европа Плюс",
        "url": "https://ep128.hostingradio.ru:8030/ep128",
    },
    "maximum": {
        "name": "Maximum",
        "url": "http://maximum.hostingradio.ru:8010/maximum128.mp3",
    },
    "lighthouse": {
        "name": "Маяк",
        "url": "https://lighthouse.hostingradio.ru:8025/lighthouse128.mp3",
    },
    "rocks": {
        "name": "Rock FM",
        "url": "http://rfm.hostingradio.ru:8034/rfm128.mp3",
    },
}

_PLAYER: str | None = None


def _stop_player() -> None:
    """Останавливает MPV плеер."""
    global _PLAYER
    if _PLAYER:
        try:
            subprocess.run(["pkill", "-f", "mpv.*radio"], check=False, timeout=5)
        except Exception:
            log.debug("radio: не критичная ошибка при subprocess.run(['pkill', '-f', 'mpv.*radio'], chec")
        _PLAYER = None


def play(station: str = "") -> str:
    """Включает радиостанцию."""
    global _PLAYER
    if not shutil.which("mpv"):
        return "mpv не установлен. Установите: sudo apt install mpv, сэр."
    _stop_player()
    key = station.strip().lower()
    if not key:
        key = "record"
    # Поиск по имени
    matched = None
    for k, v in _STATIONS.items():
        if key in k or key in v["name"].lower():
            matched = (k, v)
            break
    if not matched:
        # Возможно это URL
        if key.startswith("http"):
            url = key
            name = "кастомная"
        else:
            available = ", ".join(f"{v['name']} ({k})" for k, v in _STATIONS.items())
            return f"Станция '{station}' не найдена. Доступные: {available}, сэр."
    else:
        name = matched[1]["name"]
        url = matched[1]["url"]
    try:
        subprocess.Popen(
            ["mpv", "--no-video", "--title", f"Jarvis Radio — {name}", url],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        _PLAYER = url
        return f"Радио '{name}' включено, сэр."
    except Exception as exc:
        return f"Не удалось включить: {exc}, сэр."


def stop() -> str:
    """Выключает радио."""
    if _PLAYER:
        _stop_player()
        return "Радио выключено, сэр."
    return "Радио не играет, сэр."


def list_stations() -> str:
    """Показывает доступные станции."""
    lines = ["Радиостанции:"]
    for key, station in _STATIONS.items():
        lines.append(f"  {station['name']} ({key})")
    return "\n".join(lines)


def build_skills() -> list[Skill]:
    return [
        Skill(
            name="radio_play",
            description="Включить радиостанцию.",
            parameters=object_schema(
                {"station": {"type": "string", "description": "Название станции или URL"}},
            ),
            handler=lambda station="": play(station),
        ),
        Skill(
            name="radio_stop",
            description="Выключить радио.",
            parameters=object_schema({}),
            handler=stop,
        ),
        Skill(
            name="radio_list",
            description="Показать доступные радиостанции.",
            parameters=object_schema({}),
            handler=list_stations,
        ),
    ]
