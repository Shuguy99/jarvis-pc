"""Генератор 20 новых навыков для Джарвиса."""

import os

SKILLS_DIR = os.path.join(os.path.dirname(__file__), "..", "jarvis", "skills")


# ────────────────────────────────────────────────────────────────────
# 1. volume.py — Управление громкостью
# ────────────────────────────────────────────────────────────────────
VOLUME = '''\
"""Управление громкостью системы."""

from __future__ import annotations

import logging
import platform
import shutil
import subprocess

from .registry import Skill, object_schema

log = logging.getLogger(__name__)

IS_WINDOWS = platform.system() == "Windows"
IS_MACOS = platform.system() == "Darwin"
IS_LINUX = platform.system() == "Linux"


def _get_volume() -> int:
    """Возвращает текущую громкость 0-100."""
    try:
        if IS_WINDOWS:
            try:
                from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
                devices = AudioUtilities.GetSpeakers()
                interface = devices.Activate(IAudioEndpointVolume._iid_, 0, None, None)
                return int(interface.GetMasterVolumeLevelScalar() * 100)
            except Exception:
                pass
            return 50
        if IS_MACOS:
            r = subprocess.run(["osascript", "-e", "output volume of (get volume settings)"],
                               capture_output=True, text=True, timeout=5)
            return int(r.stdout.strip()) if r.stdout.strip().isdigit() else 50
        # Linux: pactl
        if shutil.which("pactl"):
            r = subprocess.run(["pactl", "get-sink-volume", "@DEFAULT_SINK@"],
                               capture_output=True, text=True, timeout=5)
            for part in r.stdout.split():
                if part.endswith("%"):
                    return int(part.rstrip("%"))
        return 50
    except Exception:
        return 50


def _set_volume(level: int) -> str:
    """Устанавливает громкость 0-100."""
    level = max(0, min(100, level))
    try:
        if IS_WINDOWS:
            try:
                from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
                devices = AudioUtilities.GetSpeakers()
                interface = devices.Activate(IAudioEndpointVolume._iid_, 0, None, None)
                interface.SetMasterVolumeLevelScalar(level / 100, None)
            except Exception:
                subprocess.run(
                    ["powershell", "-NoProfile", "-Command",
                     f"(New-Object -ComObject WScript.Shell).SendKeys([char]174)"],
                    check=False, timeout=10)
                return f"Громкость примерно установлена, сэр."
        elif IS_MACOS:
            subprocess.run(["osascript", "-e", f"set volume output volume {level}"],
                           check=False, timeout=5)
        elif IS_LINUX:
            if shutil.which("pactl"):
                subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{level}%"],
                               check=False, timeout=5)
            elif shutil.which("amixer"):
                subprocess.run(["amixer", "set", "Master", f"{level}%"],
                               check=False, timeout=5)
            else:
                return "Нет pactl/amixer, сэр."
        return f"Громкость: {level}%, сэр."
    except Exception as exc:
        return f"Ошибка: {exc}, сэр."


def _mute() -> str:
    """Переключает mute."""
    try:
        if IS_WINDOWS:
            subprocess.run(["powershell", "-NoProfile", "-Command",
                           "(New-Object -ComObject WScript.Shell).SendKeys([char]173)"],
                           check=False, timeout=5)
        elif IS_MACOS:
            subprocess.run(["osascript", "-e", "set volume output muted not output muted"],
                           check=False, timeout=5)
        elif IS_LINUX:
            if shutil.which("pactl"):
                subprocess.run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"],
                               check=False, timeout=5)
            elif shutil.which("amixer"):
                subprocess.run(["amixer", "set", "Master", "toggle"],
                               check=False, timeout=5)
        return "Звук переключён, сэр."
    except Exception as exc:
        return f"Ошибка: {exc}, сэр."


def get_volume() -> str:
    vol = _get_volume()
    return f"Текущая громкость: {vol}%, сэр."


def set_volume(level: int = 50) -> str:
    return _set_volume(level)


def volume_up(step: int = 10) -> str:
    return _set_volume(_get_volume() + step)


def volume_down(step: int = 10) -> str:
    return _set_volume(_get_volume() - step)


def toggle_mute() -> str:
    return _mute()


def build_skills() -> list[Skill]:
    return [
        Skill(
            name="get_volume",
            description="Узнать текущую громкость системы (0-100%).",
            parameters=object_schema({}),
            handler=get_volume,
        ),
        Skill(
            name="set_volume",
            description="Установить громкость системы (0-100).",
            parameters=object_schema({
                "level": {"type": "integer", "description": "Громкость от 0 до 100"},
            }),
            handler=lambda level=50: set_volume(level),
        ),
        Skill(
            name="volume_up",
            description="Увеличить громкость на шаг.",
            parameters=object_schema({
                "step": {"type": "integer", "description": "Шаг (по умолчанию 10)"},
            }),
            handler=lambda step=10: volume_up(step),
        ),
        Skill(
            name="volume_down",
            description="Уменьшить громкость на шаг.",
            parameters=object_schema({
                "step": {"type": "integer", "description": "Шаг (по умолчанию 10)"},
            }),
            handler=lambda step=10: volume_down(step),
        ),
        Skill(
            name="toggle_mute",
            description="Переключить звук (mute/unmute).",
            parameters=object_schema({}),
            handler=toggle_mute,
        ),
    ]
'''


# ────────────────────────────────────────────────────────────────────
# 2. timer.py — Простой таймер
# ────────────────────────────────────────────────────────────────────
TIMER = '''\
"""Простой таймер: «таймер на 5 минут»."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

from .registry import Skill, object_schema

log = logging.getLogger(__name__)


class TimerService:
    """Служба таймеров и напоминаний."""

    def __init__(self, notify: Callable[[str], None]) -> None:
        self._notify = notify
        self._timers: dict[str, threading.Timer] = {}
        self._counter = 0

    def set_timer(self, seconds: int, label: str = "") -> str:
        """Запускает таймер на N секунд."""
        self._counter += 1
        tid = f"timer-{self._counter}"
        minutes, secs = divmod(seconds, 60)
        if minutes > 0:
            friendly = f"{minutes} мин {secs} сек" if secs else f"{minutes} мин"
        else:
            friendly = f"{secs} сек"
        text = f"Таймер на {friendly} запущен, сэр."
        if label:
            text = f"Таймер \u00ab{label}\u00bb на {friendly} запущен, сэр."

        def _fire() -> None:
            self._timers.pop(tid, None)
            msg = f"Время вышло, сэр!" if not label else f"\u00ab{label}\u00bb \u2014 время вышло, сэр!"
            self._notify(msg)
            log.info("Таймер %s сработал", label or tid)

        t = threading.Timer(seconds, _fire)
        t.daemon = True
        t.start()
        self._timers[tid] = t
        return text

    def list_timers(self) -> str:
        """Показывает активные таймеры."""
        active = len(self._timers)
        if active == 0:
            return "Нет активных таймеров, сэр."
        return f"Активных таймеров: {active}, сэр."

    def cancel_timer(self, timer_id: str = "") -> str:
        """Отменяет таймер по ID."""
        if not self._timers:
            return "Нет активных таймеров, сэр."
        if timer_id and timer_id in self._timers:
            self._timers[timer_id].cancel()
            del self._timers[timer_id]
            return "Таймер отменён, сэр."
        # Отменяем последний
        tid = list(self._timers.keys())[-1]
        self._timers[tid].cancel()
        del self._timers[tid]
        return "Последний таймер отменён, сэр."

    def shutdown(self) -> None:
        for t in self._timers.values():
            t.cancel()
        self._timers.clear()
'''


# ────────────────────────────────────────────────────────────────────
# 3. clipboard.py — Буфер обмена
# ────────────────────────────────────────────────────────────────────
CLIPBOARD = '''\
"""Работа с буфером обмена."""

from __future__ import annotations

import logging

from .registry import Skill, object_schema

log = logging.getLogger(__name__)


def _get_clipboard() -> str:
    try:
        import pyperclip
        return pyperclip.paste() or ""
    except Exception as exc:
        log.warning("pyperclip: %s", exc)
        return ""


def _set_clipboard(text: str) -> bool:
    try:
        import pyperclip
        pyperclip.copy(text)
        return True
    except Exception as exc:
        log.warning("pyperclip: %s", exc)
        return False


def get_clipboard() -> str:
    text = _get_clipboard()
    if not text:
        return "Буфер обмена пуст, сэр."
    preview = text[:500] if len(text) > 500 else text
    return f"В буфере: {preview}, сэр."


def set_clipboard(text: str) -> str:
    if _set_clipboard(text):
        return "Скопировано в буфер, сэр."
    return "Не удалось записать в буфер, сэр."


def clear_clipboard() -> str:
    if _set_clipboard(""):
        return "Буфер очищен, сэр."
    return "Не удалось очистить буфер, сэр."


def build_skills() -> list[Skill]:
    return [
        Skill(
            name="get_clipboard",
            description="Показать содержимое буфера обмена.",
            parameters=object_schema({}),
            handler=get_clipboard,
        ),
        Skill(
            name="set_clipboard",
            description="Скопировать текст в буфер обмена.",
            parameters=object_schema({
                "text": {"type": "string", "description": "Текст для копирования"},
            }, required=["text"]),
            handler=lambda text: set_clipboard(text),
        ),
        Skill(
            name="clear_clipboard",
            description="Очистить буфер обмена.",
            parameters=object_schema({}),
            handler=clear_clipboard,
        ),
    ]
'''


# ────────────────────────────────────────────────────────────────────
# 4. calculator.py — Калькулятор
# ────────────────────────────────────────────────────────────────────
CALCULATOR = '''\
"""Безопасный калькулятор для математических выражений."""

from __future__ import annotations

import logging
import math
import re

from .registry import Skill, object_schema

log = logging.getLogger(__name__)

# Разрешённые имена для eval
_SAFE_NAMES = {name: getattr(math, name) for name in dir(math) if not name.startswith("_")}
_SAFE_NAMES.update({
    "abs": abs, "round": round, "min": min, "max": max,
    "sum": sum, "pow": pow, "divmod": divmod,
    "int": int, "float": float,
})


def _safe_eval(expr: str) -> float:
    """Безопасно вычисляет математическое выражение."""
    # Убираем всё кроме цифр, операторов, скобок, точек, запятых и имён
    cleaned = expr.replace(",", ".")
    # Проверяем что в выражении только безопасные символы
    if not re.match(r"^[\\d+\\-*/.()\\s\\^%a-zA-Z_]+$", cleaned):
        raise ValueError("Недопустимые символы в выражении")
    return float(eval(cleaned, {"__builtins__": {}}, _SAFE_NAMES))  # noqa: S307


def calculate(expression: str) -> str:
    """Вычисляет математическое выражение."""
    try:
        # Попробуем сначала прямое вычисление
        result = _safe_eval(expression)
        # Если результат целый — покажем без точки
        if result == int(result):
            return f"Результат: {int(result)}, сэр."
        return f"Результат: {result:.6g}, сэр."
    except ZeroDivisionError:
        return "Деление на ноль, сэр."
    except (ValueError, SyntaxError) as exc:
        return f"Не удалось вычислить: {exc}, сэр."
    except Exception as exc:
        return f"Ошибка: {exc}, сэр."


def percentage(value: float, percent: float) -> str:
    """Вычисляет процент от числа."""
    try:
        result = value * percent / 100
        if result == int(result):
            return f"{percent}% от {value} = {int(result)}, сэр."
        return f"{percent}% от {value} = {result:.4g}, сэр."
    except Exception as exc:
        return f"Ошибка: {exc}, сэр."


def convert_temperature(value: float, from_unit: str = "C", to_unit: str = "F") -> str:
    """Конвертирует температуру."""
    try:
        fr = from_unit.upper()
        to = to_unit.upper()
        if fr == "C" and to == "F":
            result = value * 9 / 5 + 32
        elif fr == "F" and to == "C":
            result = (value - 32) * 5 / 9
        elif fr == "C" and to == "K":
            result = value + 273.15
        elif fr == "K" and to == "C":
            result = value - 273.15
        elif fr == to:
            return f"{value}{fr} = {value}{to}, сэр."
        else:
            return f"Конвертация {fr} → {to} не поддерживается, сэр."
        return f"{value}\u00b0{fr} = {result:.1f}\u00b0{to}, сэр."
    except Exception as exc:
        return f"Ошибка: {exc}, сэр."


def build_skills() -> list[Skill]:
    return [
        Skill(
            name="calculate",
            description="Вычислить математическое выражение (арифметика, тригонометрия, степени).",
            parameters=object_schema({
                "expression": {"type": "string", "description": "Математическое выражение, например '15% от 2400' или '(2+3)*4'"},
            }, required=["expression"]),
            handler=lambda expression: calculate(expression),
        ),
        Skill(
            name="percentage",
            description="Вычислить процент от числа.",
            parameters=object_schema({
                "value": {"type": "number", "description": "Число"},
                "percent": {"type": "number", "description": "Процент"},
            }, required=["value", "percent"]),
            handler=lambda value, percent: percentage(float(value), float(percent)),
        ),
        Skill(
            name="convert_temperature",
            description="Конвертировать температуру между Цельсием, Фаренгейтом и Кельвинами.",
            parameters=object_schema({
                "value": {"type": "number", "description": "Температура"},
                "from_unit": {"type": "string", "description": "Из какой единицы: C, F, K"},
                "to_unit": {"type": "string", "description": "В какую единицу: C, F, K"},
            }, required=["value", "from_unit", "to_unit"]),
            handler=lambda value, from_unit="C", to_unit="F": convert_temperature(float(value), from_unit, to_unit),
        ),
    ]
'''


# ────────────────────────────────────────────────────────────────────
# 5. battery.py — Состояние батареи
# ────────────────────────────────────────────────────────────────────
BATTERY = '''\
"""Статус батареи ноутбука."""

from __future__ import annotations

import logging

from .registry import Skill, object_schema

log = logging.getLogger(__name__)


def battery_status() -> str:
    """Возвращает статус батареи."""
    try:
        import psutil
        bat = psutil.sensors_battery()
        if bat is None:
            return "Батарея не обнаружена, сэр."
        percent = int(bat.percent)
        plugged = "заряжается" if bat.power_plugged else "от батареи"
        if bat.secsleft >= 0:
            h, m = divmod(bat.secsleft // 60, 60)
            time_left = f", осталось {h}ч {m}мин" if h else f", осталось {m} мин"
        else:
            time_left = ""
        return f"Батарея: {percent}% ({plugged}{time_left}), сэр."
    except Exception as exc:
        return f"Ошибка: {exc}, сэр."


def build_skills() -> list[Skill]:
    return [
        Skill(
            name="battery_status",
            description="Узнать уровень заряда батареи и статус (заряжается/разряжается).",
            parameters=object_schema({}),
            handler=battery_status,
        ),
    ]
'''


# ────────────────────────────────────────────────────────────────────
# 6. bluetooth.py — Управление Bluetooth
# ────────────────────────────────────────────────────────────────────
BLUETOOTH = '''\
"""Управление Bluetooth (Linux/macOS через bluetoothctl, Windows через子系统)."""

from __future__ import annotations

import logging
import platform
import shutil
import subprocess

from .registry import Skill, object_schema

log = logging.getLogger(__name__)

IS_LINUX = platform.system() == "Linux"
IS_WINDOWS = platform.system() == "Windows"
IS_MACOS = platform.system() == "Darwin"


def bt_status() -> str:
    """Проверяет статус Bluetooth."""
    try:
        if IS_LINUX and shutil.which("bluetoothctl"):
            r = subprocess.run(["bluetoothctl", "show"], capture_output=True, text=True, timeout=10)
            if "Powered: yes" in r.stdout:
                return "Bluetooth включён, сэр."
            return "Bluetooth выключен, сэр."
        if IS_MACOS:
            r = subprocess.run(["system_profiler", "SPBluetoothDataType"],
                               capture_output=True, text=True, timeout=10)
            if r.stdout.strip():
                return "Bluetooth доступен (macOS), сэр."
            return "Не удалось получить статус Bluetooth, сэр."
        if IS_WINDOWS:
            r = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "Get-Service bthserv | Select-Object -ExpandProperty Status"],
                capture_output=True, text=True, timeout=10,
            )
            status = r.stdout.strip()
            return f"Служба Bluetooth: {status}, сэр."
        return "Bluetooth не поддерживается на этой ОС, сэр."
    except Exception as exc:
        return f"Ошибка: {exc}, сэр."


def bt_toggle() -> str:
    """Переключает Bluetooth."""
    try:
        if IS_LINUX and shutil.which("bluetoothctl"):
            subprocess.run(["bluetoothctl", "power", "toggle"], check=False, timeout=10)
            return "Bluetooth переключён, сэр."
        if IS_MACOS:
            subprocess.run(["blueutil", "--power", "toggle"], check=False, timeout=10)
            return "Bluetooth переключён, сэр."
        if IS_WINDOWS:
            subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "Toggle-Bluetooth -Enable:(Get-Service bthserv).Status -ne 'Running'"],
                check=False, timeout=10,
            )
            return "Bluetooth переключён, сэр."
        return "Bluetooth не поддерживается на этой ОС, сэр."
    except Exception as exc:
        return f"Ошибка: {exc}, сэр."


def bt_scan() -> str:
    """Сканирует Bluetooth-устройства."""
    try:
        if IS_LINUX and shutil.which("bluetoothctl"):
            subprocess.run(["bluetoothctl", "scan", "on"],
                           capture_output=True, text=True, timeout=5)
            import time
            time.sleep(3)
            subprocess.run(["bluetoothctl", "devices"],
                           capture_output=True, text=True, timeout=5)
            r = subprocess.run(["bluetoothctl", "devices"],
                               capture_output=True, text=True, timeout=10)
            lines = [l for l in r.stdout.strip().split("\n") if l.strip()]
            if not lines:
                return "Устройства не найдены, сэр."
            return "Найденные устройства:\n" + "\n".join(f"  {l}" for l in lines[:10]) + ", сэр."
        return "Сканирование Bluetooth доступно только на Linux, сэр."
    except Exception as exc:
        return f"Ошибка: {exc}, сэр."


def build_skills() -> list[Skill]:
    return [
        Skill(
            name="bt_status",
            description="Проверить статус Bluetooth (включён/выключен).",
            parameters=object_schema({}),
            handler=bt_status,
        ),
        Skill(
            name="bt_toggle",
            description="Включить или выключить Bluetooth.",
            parameters=object_schema({}),
            handler=bt_toggle,
        ),
        Skill(
            name="bt_scan",
            description="Сканировать Bluetooth-устройства рядом.",
            parameters=object_schema({}),
            handler=bt_scan,
        ),
    ]
'''


# ────────────────────────────────────────────────────────────────────
# 7. brightness.py — Яркость монитора
# ────────────────────────────────────────────────────────────────────
BRIGHTNESS = '''\
"""Управление яркостью монитора."""

from __future__ import annotations

import logging
import platform
import shutil
import subprocess

from .registry import Skill, object_schema

log = logging.getLogger(__name__)

IS_LINUX = platform.system() == "Linux"
IS_WINDOWS = platform.system() == "Windows"
IS_MACOS = platform.system() == "Darwin"


def _get_brightness_linux() -> int:
    """Получает яркость на Linux через xrandr или brightnessctl."""
    if shutil.which("brightnessctl"):
        r = subprocess.run(["brightnessctl", "info"], capture_output=True, text=True, timeout=5)
        for part in r.stdout.split():
            if "%" in part:
                return int(part.strip("(%),"))
    if shutil.which("xrandr"):
        r = subprocess.run(["xrandr", "--verbose"], capture_output=True, text=True, timeout=5)
        import re
        m = re.search(r"Brightness:\s*([\d.]+)", r.stdout)
        if m:
            return int(float(m.group(1)) * 100)
    return -1


def _set_brightness_linux(level: int) -> bool:
    """Устанавливает яркость на Linux."""
    level = max(0, min(100, level))
    if shutil.which("brightnessctl"):
        subprocess.run(["brightnessctl", "set", f"{level}%"], check=False, timeout=5)
        return True
    if shutil.which("xrandr"):
        r = subprocess.run(["xrandr", "--current"], capture_output=True, text=True, timeout=5)
        import re
        displays = re.findall(r"^(\S+) connected", r.stdout, re.MULTILINE)
        if displays:
            subprocess.run(["xrandr", "--output", displays[0], "--brightness", str(level / 100)],
                           check=False, timeout=5)
            return True
    return False


def get_brightness() -> str:
    """Показать текущую яркость."""
    try:
        if IS_LINUX:
            val = _get_brightness_linux()
            if val >= 0:
                return f"Яркость: {val}%, сэр."
            return "Не удалось определить яркость (нужен brightnessctl или xrandr), сэр."
        if IS_MACOS:
            r = subprocess.run(["brightness", "-l"], capture_output=True, text=True, timeout=5)
            import re
            m = re.search(r"brightness\s+([\d.]+)", r.stdout)
            if m:
                return f"Яркость: {int(float(m.group(1)) * 100)}%, сэр."
        if IS_WINDOWS:
            r = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightness).CurrentBrightness"],
                capture_output=True, text=True, timeout=10,
            )
            if r.stdout.strip():
                return f"Яркость: {r.stdout.strip()}%, сэр."
        return "Яркость: управление не поддерживается на этой ОС, сэр."
    except Exception as exc:
        return f"Ошибка: {exc}, сэр."


def set_brightness(level: int = 50) -> str:
    """Установить яркость 0-100."""
    try:
        if IS_LINUX:
            if _set_brightness_linux(level):
                return f"Яркость: {level}%, сэр."
            return "Не удалось изменить яркость (нужен brightnessctl или xrandr), сэр."
        if IS_MACOS:
            subprocess.run(["brightness", "-l", str(level / 100)], check=False, timeout=5)
            return f"Яркость: {level}%, сэр."
        if IS_WINDOWS:
            subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 f"(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods)