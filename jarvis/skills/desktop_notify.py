"""Desktop-уведомления: системные toast/notify для событий, таймеров и Telegram."""

from __future__ import annotations

import logging
import platform
import subprocess
from pathlib import Path

from .registry import Skill, object_schema

log = logging.getLogger(__name__)

IS_WINDOWS = platform.system() == "Windows"
IS_MACOS = platform.system() == "Darwin"
IS_LINUX = platform.system() == "Linux"


def _notify_plyer(title: str, message: str) -> bool:
    """Пытается отправить уведомление через plyer."""
    try:
        from plyer import notification  # type: ignore[import-not-found]
        notification.notify(title=title, message=message, timeout=10, app_name="Jarvis")
        return True
    except ImportError:
        return False
    except Exception as exc:
        log.warning("plyer уведомление не удалось: %s", exc)
        return False


def _notify_windows(title: str, message: str) -> bool:
    """Windows toast через PowerShell (Windows 10+)."""
    if not IS_WINDOWS:
        return False
    safe_title = title.replace("'", "''").replace(")", "")
    safe_msg = message.replace("'", "''").replace(")", "")
    ps_script = (
        "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, "
        "ContentType = WindowsRuntime] > $null; "
        "[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, "
        "ContentType = WindowsRuntime] > $null; "
        "$template = @'"
        "<toast><visual><binding template='ToastGeneric'>"
        "<text>$title</text><text>$message</text>"
        "</binding></visual></toast>"
        "'@; "
        "$xml = New-Object Windows.Data.Xml.Dom.XmlDocument; "
        "$xml.LoadXml($template.Replace('$title', '"
        + safe_title + "').Replace('$message', '" + safe_msg + "')); "
        "$toast = [Windows.UI.Notifications.ToastNotification]::new($xml); "
        "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('Jarvis').Show($toast);"
    )
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            check=False, timeout=10, capture_output=True,
        )
        return True
    except Exception as exc:
        log.warning("Windows toast не удался: %s", exc)
        return False


def _notify_linux(title: str, message: str) -> bool:
    """Linux уведомление через notify-send."""
    if not IS_LINUX:
        return False
    import shutil
    if not shutil.which("notify-send"):
        return False
    try:
        subprocess.run(
            ["notify-send", "-t", "10000", title, message],
            check=False, timeout=10,
        )
        return True
    except Exception as exc:
        log.warning("notify-send не удался: %s", exc)
        return False


def _notify_macos(title: str, message: str) -> bool:
    """macOS уведомление через osascript."""
    if not IS_MACOS:
        return False
    safe_title = title.replace('\\', '\\\\').replace('"', '\\"')
    safe_msg = message.replace('\\', '\\\\').replace('"', '\\"')
    try:
        subprocess.run(
            ["osascript", "-e", f'display notification "{safe_msg}" with title "{safe_title}"'],
            check=False, timeout=10,
        )
        return True
    except Exception as exc:
        log.warning("macOS уведомление не удалось: %s", exc)
        return False


def notify(title: str, message: str) -> str:
    """Показать desktop-уведомление.

    Пробует plyler, затем нативные методы ОС.
    """
    if not title and not message:
        return "Укажите заголовок или текст уведомления, сэр."
    if _notify_plyer(title, message):
        return f"Уведомление отправлено: {title}."
    if _notify_windows(title, message):
        return f"Уведомление отправлено: {title}."
    if _notify_linux(title, message):
        return f"Уведомление отправлено: {title}."
    if _notify_macos(title, message):
        return f"Уведомление отправлено: {title}."
    return "Не удалось отправить уведомление. Установите plyer (pip install plyer), сэр."


def build_skills() -> list[Skill]:
    """Создаёт навык уведомлений."""
    return [
        Skill(
            name="show_notification",
            description=(
                "Показать desktop-уведомление (toast). "
                "Полезно для напоминаний и важных сообщений."
            ),
            parameters=object_schema(
                {
                    "title": {
                        "type": "string",
                        "description": "Заголовок уведомления",
                    },
                    "message": {
                        "type": "string",
                        "description": "Текст уведомления",
                    },
                },
            ),
            handler=notify,
        ),
    ]