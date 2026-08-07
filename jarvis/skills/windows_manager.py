"""Менеджер окон: разделение экрана, перемещение между мониторами."""

from __future__ import annotations

import logging
import platform
import shutil
import subprocess

from .registry import Skill, object_schema

log = logging.getLogger(__name__)

IS_LINUX = platform.system() == "Linux"
IS_WINDOWS = platform.system() == "Windows"


def _get_active_window_id() -> str | None:
    """Получает ID активного окна (Linux, xdotool)."""
    if not shutil.which("xdotool"):
        return None
    try:
        result = subprocess.run(
            ["xdotool", "getactivewindow"],
            capture_output=True, text=True, check=False, timeout=3,
        )
        return result.stdout.strip() or None
    except Exception:
        return None


def _get_screen_resolution() -> tuple[int, int]:
    """Получает разрешение экрана."""
    if IS_WINDOWS:
        try:
            import ctypes
            user32 = ctypes.windll.user32
            return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
        except Exception:
            return 1920, 1080
    if IS_LINUX and shutil.which("xdpyinfo"):
        try:
            result = subprocess.run(
                ["xdpyinfo"], capture_output=True, text=True, check=False, timeout=5,
            )
            import re
            m = re.search(r"dimensions:\s+(\d+)x(\d+)", result.stdout)
            if m:
                return int(m.group(1)), int(m.group(2))
        except Exception:
            pass
    return 1920, 1080


def _move_window_linux(x: int, y: int, w: int, h: int) -> str:
    """Перемещает и ресайзит окно через xdotool + wmctrl."""
    win_id = _get_active_window_id()
    if not win_id:
        return "Не удалось определить активное окно, сэр."
    try:
        subprocess.run(
            ["xdotool", "windowmove", "--sync", win_id, str(x), str(y)],
            check=False, timeout=3,
        )
        subprocess.run(
            ["xdotool", "windowsize", "--sync", win_id, str(w), str(h)],
            check=False, timeout=3,
        )
        return f"Окно перемещено в ({x}, {y}) размером {w}x{h}, сэр."
    except Exception as exc:
        return f"Ошибка: {exc}, сэр."


def snap_left() -> str:
    """Разделить экран: окно на левую половину."""
    if IS_LINUX:
        w, h = _get_screen_resolution()
        return _move_window_linux(0, 0, w // 2, h)
    if IS_WINDOWS:
        try:
            import ctypes
            user32 = ctypes.windll.user32
            user32.keybd_event(0x5B, 0, 0, 0)  # Win
            user32.keybd_event(0x25, 0, 0, 0)  # Left
            user32.keybd_event(0x5B, 0, 2, 0)
            user32.keybd_event(0x25, 0, 2, 0)
            return "Окно на левой половине, сэр."
        except Exception:
            pass
    return "Не поддерживается на этой ОС, сэр."


def snap_right() -> str:
    """Разделить экран: окно на правую половину."""
    if IS_LINUX:
        w, h = _get_screen_resolution()
        return _move_window_linux(w // 2, 0, w // 2, h)
    if IS_WINDOWS:
        try:
            import ctypes
            user32 = ctypes.windll.user32
            user32.keybd_event(0x5B, 0, 0, 0)
            user32.keybd_event(0x27, 0, 0, 0)  # Right
            user32.keybd_event(0x5B, 0, 2, 0)
            user32.keybd_event(0x27, 0, 2, 0)
            return "Окно на правой половине, сэр."
        except Exception:
            pass
    return "Не поддерживается, сэр."


def maximize() -> str:
    """Развернуть окно на весь экран."""
    if IS_LINUX and shutil.which("xdotool"):
        subprocess.run(["xdotool", "getactivewindow", "windowactivate", "--sync"], check=False, timeout=3)
        subprocess.run(["xdotool", "key", "super+Up"], check=False, timeout=3)
        # Fallback через wmctrl
        if shutil.which("wmctrl"):
            subprocess.run(["wmctrl", "-r", ":ACTIVE:", "-b", "add,maximized_vert,maximized_horz"], check=False, timeout=3)
        return "Окно развёрнуто, сэр."
    if IS_WINDOWS:
        try:
            import ctypes
            user32 = ctypes.windll.user32
            user32.keybd_event(0x5B, 0, 0, 0)
            user32.keybd_event(0x26, 0, 0, 0)  # Up
            user32.keybd_event(0x5B, 0, 2, 0)
            user32.keybd_event(0x26, 0, 2, 0)
            return "Окно развёрнуто, сэр."
        except Exception:
            pass
    return "Не поддерживается, сэр."


def minimize() -> str:
    """Свернуть окно."""
    if IS_LINUX and shutil.which("xdotool"):
        subprocess.run(["xdotool", "getactivewindow", "windowminimize"], check=False, timeout=3)
        return "Окно свёрнуто, сэр."
    if IS_WINDOWS:
        try:
            import ctypes
            user32 = ctypes.windll.user32
            user32.keybd_event(0x5B, 0, 0, 0)
            user32.keybd_event(0x28, 0, 0, 0)  # Down
            user32.keybd_event(0x5B, 0, 2, 0)
            user32.keybd_event(0x28, 0, 2, 0)
            return "Окно свёрнуто, сэр."
        except Exception:
            pass
    return "Не поддерживается, сэр."


def list_monitors() -> str:
    """Показать информацию о мониторах."""
    if IS_LINUX:
        if shutil.which("xrandr"):
            result = subprocess.run(
                ["xrandr", "--query"], capture_output=True, text=True, check=False, timeout=5,
            )
            lines = ["Мониторы:"]
            for line in result.stdout.split("\n"):
                line = line.strip()
                if " connected" in line and "*" in line:
                    lines.append(f"  {line.split(' connected')[0]}: {line.split('*')[-1].strip().split()[0]}")
            return "\n".join(lines) if len(lines) > 1 else "Не удалось определить мониторы, сэр."
    if IS_WINDOWS:
        w, h = _get_screen_resolution()
        return f"Экран: {w}x{h} (детальная информация недоступна), сэр."
    return "Не поддерживается, сэр."


def build_skills() -> list[Skill]:
    return [
        Skill(
            name="snap_left",
            description="Разместить активное окно на левой половине экрана.",
            parameters=object_schema({}),
            handler=snap_left,
        ),
        Skill(
            name="snap_right",
            description="Разместить активное окно на правой половине экрана.",
            parameters=object_schema({}),
            handler=snap_right,
        ),
        Skill(
            name="maximize_window",
            description="Развернуть активное окно на весь экран.",
            parameters=object_schema({}),
            handler=maximize,
        ),
        Skill(
            name="minimize_window",
            description="Свернуть активное окно.",
            parameters=object_schema({}),
            handler=minimize,
        ),
        Skill(
            name="list_monitors",
            description="Показать информацию о мониторах.",
            parameters=object_schema({}),
            handler=list_monitors,
        ),
    ]
