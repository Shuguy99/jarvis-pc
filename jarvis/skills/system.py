"""Навыки управления системой: громкость, медиа, скриншоты, состояние ПК."""

from __future__ import annotations

import ctypes
import datetime as dt
import logging
import platform
import shutil
import subprocess
from pathlib import Path

from ..config import SkillsConfig
from .registry import Skill, _confirm_handler, object_schema

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


def _set_volume_linux(level: int) -> str | None:
    """Устанавливает громкость через PulseAudio/PipeWire (pactl) или ALSA (amixer)."""
    level_pct = max(0, min(100, int(level)))
    # PulseAudio / PipeWire через pactl.
    if shutil.which("pactl"):
        try:
            # Получаем индекс_sink для sink #0 (по умолчанию).
            subprocess.run(
                ["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{level_pct}%"],
                check=True,
                timeout=5,
            )
            return f"Громкость установлена на {level_pct} процентов."
        except (subprocess.CalledProcessError, FileNotFoundError, OSError) as exc:
            log.warning("pactl не смог установить громкость: %s", exc)
    # ALSA через amixer.
    if shutil.which("amixer"):
        try:
            subprocess.run(
                ["amixer", "-q", "sset", "Master", f"{level_pct}%"],
                check=True,
                timeout=5,
            )
            return f"Громкость установлена на {level_pct} процентов."
        except (subprocess.CalledProcessError, FileNotFoundError, OSError) as exc:
            log.warning("amixer не смог установить громкость: %s", exc)
    return None


def _change_volume_linux(delta: int) -> str | None:
    """Меняет громкость на Linux через pactl, amixer или xdotool."""
    # Получаем текущую громкость через pactl.
    if shutil.which("pactl"):
        try:
            result = subprocess.run(
                ["pactl", "get-sink-volume", "@DEFAULT_SINK@"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            # Парсим формат «Volume: front-left: 32768 /  50% / -18,06 dB ...»
            for part in result.stdout.split():
                if part.endswith("%"):
                    current = int(part.rstrip("%"))
                    new_level = max(0, min(100, current + int(delta)))
                    return _set_volume_linux(new_level)
        except (subprocess.CalledProcessError, ValueError, OSError) as exc:
            log.warning("Не удалось получить текущую громкость через pactl: %s", exc)
    # ALSA через amixer: относительное изменение.
    if shutil.which("amixer"):
        try:
            subprocess.run(
                ["amixer", "-q", "sset", "Master", f"{int(delta):+d}%"],
                check=True,
                timeout=5,
            )
            direction = "увеличена" if delta > 0 else "уменьшена"
            return f"Громкость {direction} на {abs(int(delta))} процентов."
        except (subprocess.CalledProcessError, FileNotFoundError, OSError) as exc:
            log.warning("amixer не смог изменить громкость: %s", exc)
    # Fallback: xdotool для мультимедийных клавиш.
    if shutil.which("xdotool"):
        key = "XF86AudioRaiseVolume" if delta > 0 else "XF86AudioLowerVolume"
        steps = max(1, round(abs(int(delta)) / 5))
        subprocess.run(["xdotool", "key", "--repeat", str(steps), key], check=False, timeout=5)
        direction = "увеличена" if delta > 0 else "уменьшена"
        return f"Громкость {direction} примерно на {abs(int(delta))} процентов."
    return None


def set_volume(level: int) -> str:
    """Устанавливает общую громкость системы в процентах."""
    level = max(0, min(100, int(level)))
    if IS_WINDOWS:
        if _set_volume_pycaw(level):
            return f"Громкость установлена на {level} процентов."
        # Без pycaw доступен только грубый шаг клавишами (2% на нажатие).
        _tap_key(VK_VOLUME_DOWN, 50)
        _tap_key(VK_VOLUME_UP, round(level / 2))
        return f"Громкость примерно {level} процентов."
    # Linux / macOS.
    result = _set_volume_linux(level)
    if result:
        return result
    return "Управление громкостью недоступно. Установите pactl (PulseAudio) или amixer (ALSA)."


def change_volume(delta: int) -> str:
    """Меняет громкость на указанное число процентов."""
    if IS_WINDOWS:
        steps = max(1, round(abs(int(delta)) / 2))
        _tap_key(VK_VOLUME_UP if delta > 0 else VK_VOLUME_DOWN, steps)
        direction = "увеличена" if delta > 0 else "уменьшена"
        return f"Громкость {direction} на {abs(int(delta))} процентов."
    result = _change_volume_linux(delta)
    if result:
        return result
    return "Управление громкостью недоступно, сэр."


def media_control(action: str) -> str:
    """Управляет воспроизведением мультимедиа."""
    action_lower = action.lower()
    if IS_WINDOWS:
        key = MEDIA_KEYS.get(action_lower)
        if key is None:
            return f"Не знаю команду «{action}», сэр."
        _tap_key(key)
        return f"Готово: {action}."
    # Linux: xdotool для мультимедийных клавиш.
    if shutil.which("xdotool"):
        x11_keys = {
            "play": "XF86AudioPlay",
            "pause": "XF86AudioPlay",
            "next": "XF86AudioNext",
            "previous": "XF86AudioPrev",
            "mute": "XF86AudioMute",
        }
        x11_key = x11_keys.get(action_lower)
        if x11_key:
            subprocess.run(["xdotool", "key", x11_key], check=False, timeout=5)
            return f"Готово: {action}."
        return f"Не знаю команду «{action}», сэр."
    # macOS: applescript.
    if platform.system() == "Darwin":
        if action_lower in ("play", "pause"):
            subprocess.run(["osascript", "-e", "tell application \"System Events\" to key code 16"], check=False, timeout=5)
            return f"Готово: {action}."
        return f"Мультимедиа на macOS пока ограничено, сэр."
    return "Мультимедийные клавиши недоступны. Установите xdotool."


def lock_workstation() -> str:
    """Блокирует рабочую станцию."""
    if IS_WINDOWS:
        ctypes.windll.user32.LockWorkStation()  # type: ignore[attr-defined]
        return "Рабочая станция заблокирована, сэр."
    if platform.system() == "Darwin":
        subprocess.run([r"/System/Library/CoreServices/Menu Extras/User.menu/Contents/Resources/CGSession", "-suspend"], check=False, timeout=5)
        return "Рабочая станция заблокирована, сэр."
    # Linux: loginctl, gnome-screensaver, xdg-screensaver.
    if shutil.which("loginctl"):
        subprocess.run(["loginctl", "lock-session"], check=False, timeout=5)
        return "Рабочая станция заблокирована, сэр."
    if shutil.which("xdg-screensaver"):
        subprocess.run(["xdg-screensaver", "lock"], check=False, timeout=5)
        return "Рабочая станция заблокирована, сэр."
    return "Блокировка экрана не поддерживается на этой системе, сэр."


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


def power_action(config: SkillsConfig, action: str, delay_s: int = 20) -> str:
    """Выключает, перезагружает ПК или отменяет запланированное действие."""
    action = action.lower()
    if action != "cancel" and not config.allow_shutdown:
        return "Выключение отключено в конфигурации. Включите skills.allow_shutdown, сэр."
    # Linux shutdown принимает время в минутах, Windows — в секундах.
    delay_min = max(1, round(delay_s / 60))
    commands: dict[str, list[str]] = {}
    if IS_WINDOWS:
        commands = {
            "shutdown": ["shutdown", "/s", "/t", str(max(0, delay_s))],
            "restart": ["shutdown", "/r", "/t", str(max(0, delay_s))],
            "cancel": ["shutdown", "/a"],
        }
    else:
        commands = {
            "shutdown": ["shutdown", "-h", f"+{delay_min}"],
            "restart": ["shutdown", "-r", f"+{delay_min}"],
            "cancel": ["shutdown", "-c"],
        }
    command = commands.get(action)
    if command is None:
        return f"Неизвестное действие питания: {action}."
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        err = result.stderr.strip()[:100] if result.stderr else ""
        return f"Не удалось выполнить {action}: {err or 'недостаточно прав'}, сэр."
    if action == "cancel":
        return "Запланированное выключение отменено."
    if IS_WINDOWS:
        return f"Принято. {action} через {delay_s} секунд, сэр."
    return f"Принято. {action} через {delay_min} мину{'ту' if delay_min == 1 else 'ты' if 1 < delay_min < 5 else 'т'}, сэр."


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
            handler=_confirm_handler(
                lambda action, delay_s=20: power_action(config, action, delay_s),
                'Выполнить {action} компьютера?',
            ),
        ),
    ]
