"""Навыки управления системой: громкость, медиа, скриншоты, состояние ПК."""

from __future__ import annotations

import ctypes
import datetime as dt
import logging
import platform
import subprocess
from pathlib import Path

from ..config import SkillsConfig
from .registry import Skill, object_schema

log = logging.getLogger(__name__)

IS_WINDOWS = platform.system() == "Windows"

# Виртуальные коды мультимедийных клавиш Windows.
VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_PLAY_PAUSE = 0xB3

MEDIA_KEYS = {
    "play": VK_MEDIA_PLAY_PAUSE,
    "pause": VK_MEDIA_PLAY_PAUSE,
    "next": VK_MEDIA_NEXT_TRACK,
    "previous": VK_MEDIA_PREV_TRACK,
    "mute": VK_VOLUME_MUTE,
}


def _tap_key(vk_code: int, times: int = 1) -> None:
    """Нажимает системную клавишу указанное число раз."""
    if not IS_WINDOWS:
        raise RuntimeError("Управление клавишами доступно только в Windows.")
    user32 = ctypes.windll.user32  # type: ignore[attr-defined]
    for _ in range(times):
        user32.keybd_event(vk_code, 0, 0, 0)
        user32.keybd_event(vk_code, 0, 2, 0)


def _set_volume_pycaw(level: int) -> bool:
    """Пытается выставить громкость через pycaw. Возвращает успех."""
    try:
        from comtypes import CLSCTX_ALL  # type: ignore[import-not-found]
        from pycaw.pycaw import (  # type: ignore[import-not-found]
            AudioUtilities,
            IAudioEndpointVolume,
        )
    except ImportError:
        return False
    devices = AudioUtilities.GetSpeakers()
    interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    volume = interface.QueryInterface(IAudioEndpointVolume)
    volume.SetMasterVolumeLevelScalar(level / 100, None)
    return True


def set_volume(level: int) -> str:
    """Устанавливает общую громкость системы в процентах."""
    level = max(0, min(100, int(level)))
    if not IS_WINDOWS:
        return "Управление громкостью поддерживается только в Windows, сэр."
    if _set_volume_pycaw(level):
        return f"Громкость установлена на {level} процентов."
    # Без pycaw доступен только грубый шаг клавишами (2% на нажатие).
    _tap_key(VK_VOLUME_DOWN, 50)
    _tap_key(VK_VOLUME_UP, round(level / 2))
    return f"Громкость примерно {level} процентов."


def change_volume(delta: int) -> str:
    """Меняет громкость на указанное число процентов."""
    if not IS_WINDOWS:
        return "Управление громкостью поддерживается только в Windows, сэр."
    steps = max(1, round(abs(int(delta)) / 2))
    _tap_key(VK_VOLUME_UP if delta > 0 else VK_VOLUME_DOWN, steps)
    direction = "увеличена" if delta > 0 else "уменьшена"
    return f"Громкость {direction} на {abs(int(delta))} процентов."


def media_control(action: str) -> str:
    """Управляет воспроизведением мультимедиа."""
    key = MEDIA_KEYS.get(action.lower())
    if key is None:
        return f"Не знаю команду «{action}», сэр."
    if not IS_WINDOWS:
        return "Мультимедийные клавиши доступны только в Windows, сэр."
    _tap_key(key)
    return f"Готово: {action}."


def take_screenshot(config: SkillsConfig, name: str = "") -> str:
    """Делает снимок экрана и сохраняет его в каталог скриншотов."""
    try:
        import mss  # type: ignore[import-not-found]
    except ImportError:
        return "Модуль mss не установлен, сэр."
    target_dir = Path(config.screenshot_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    safe_name = "".join(ch for ch in name if ch.isalnum() or ch in "-_ ").strip()
    filename = f"{safe_name or 'screen'}-{stamp}.png"
    path = target_dir / filename
    with mss.mss() as sct:
        sct.shot(mon=-1, output=str(path))
    return f"Снимок экрана сохранён: {path}"


def system_status() -> str:
    """Сообщает загрузку процессора, памяти, диска и заряд батареи."""
    try:
        import psutil  # type: ignore[import-not-found]
    except ImportError:
        return "Модуль psutil не установлен, сэр."
    cpu = psutil.cpu_percent(interval=0.5)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage(str(Path.home().anchor or "/"))
    parts = [
        f"Процессор загружен на {cpu:.0f} процентов",
        f"память на {memory.percent:.0f} процентов",
        f"диск заполнен на {disk.percent:.0f} процентов",
    ]
    battery = getattr(psutil, "sensors_battery", lambda: None)()
    if battery is not None:
        state = "заряжается" if battery.power_plugged else "от батареи"
        parts.append(f"батарея {battery.percent:.0f} процентов, {state}")
    return ", ".join(parts) + "."


def lock_workstation() -> str:
    """Блокирует рабочую станцию."""
    if not IS_WINDOWS:
        return "Блокировка поддерживается только в Windows, сэр."
    ctypes.windll.user32.LockWorkStation()  # type: ignore[attr-defined]
    return "Рабочая станция заблокирована, сэр."


def power_action(config: SkillsConfig, action: str, delay_s: int = 20) -> str:
    """Выключает, перезагружает ПК или отменяет запланированное действие."""
    action = action.lower()
    if action != "cancel" and not config.allow_shutdown:
        return "Выключение отключено в конфигурации. Включите skills.allow_shutdown, сэр."
    if not IS_WINDOWS:
        return "Управление питанием реализовано только для Windows, сэр."
    commands = {
        "shutdown": ["shutdown", "/s", "/t", str(max(0, delay_s))],
        "restart": ["shutdown", "/r", "/t", str(max(0, delay_s))],
        "cancel": ["shutdown", "/a"],
    }
    command = commands.get(action)
    if command is None:
        return f"Неизвестное действие питания: {action}."
    subprocess.run(command, check=False)
    if action == "cancel":
        return "Запланированное выключение отменено."
    return f"Принято. {action} через {delay_s} секунд, сэр."


def build_skills(config: SkillsConfig) -> list[Skill]:
    """Создаёт системные навыки, привязанные к конфигурации."""
    return [
        Skill(
            name="set_volume",
            description="Установить громкость системы в процентах (0-100).",
            parameters=object_schema(
                {"level": {"type": "integer", "description": "Уровень 0-100"}},
                required=["level"],
            ),
            handler=set_volume,
        ),
        Skill(
            name="change_volume",
            description="Изменить громкость на дельту в процентах, например -10 или 15.",
            parameters=object_schema(
                {"delta": {"type": "integer", "description": "Дельта в процентах"}},
                required=["delta"],
            ),
            handler=change_volume,
        ),
        Skill(
            name="media_control",
            description="Управление плеером: play, pause, next, previous, mute.",
            parameters=object_schema(
                {
                    "action": {
                        "type": "string",
                        "enum": sorted(MEDIA_KEYS),
                        "description": "Действие плеера",
                    }
                },
                required=["action"],
            ),
            handler=media_control,
        ),
        Skill(
            name="take_screenshot",
            description="Сделать снимок экрана и сохранить его в файл.",
            parameters=object_schema(
                {"name": {"type": "string", "description": "Имя файла без расширения"}}
            ),
            handler=lambda name="": take_screenshot(config, name),
        ),
        Skill(
            name="system_status",
            description="Показать загрузку процессора, памяти, диска и заряд батареи.",
            parameters=object_schema({}),
            handler=system_status,
        ),
        Skill(
            name="lock_workstation",
            description="Заблокировать компьютер.",
            parameters=object_schema({}),
            handler=lock_workstation,
        ),
        Skill(
            name="power_action",
            description=(
                "Выключить (shutdown), перезагрузить (restart) компьютер "
                "или отменить (cancel) запланированное действие."
            ),
            parameters=object_schema(
                {
                    "action": {
                        "type": "string",
                        "enum": ["shutdown", "restart", "cancel"],
                        "description": "Действие питания",
                    },
                    "delay_s": {
                        "type": "integer",
                        "description": "Задержка в секундах",
                    },
                },
                required=["action"],
            ),
            handler=lambda action, delay_s=20: power_action(config, action, delay_s),
        ),
    ]
