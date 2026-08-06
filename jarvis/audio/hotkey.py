"""Горячие клавиши: push-to-talk и глобальные сочетания.

Зависит от pynput (опционально). Если pynput не установлен,
горячие клавиши недоступны, но ассистент продолжает работать.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

log = logging.getLogger(__name__)


def _parse_hotkey(hotkey: str) -> list[tuple[str, str]]:
    """Разбирает строку 'ctrl+alt+j' в список (модификатор, ключ)."""
    parts = [p.strip().lower() for p in hotkey.split("+")]
    if len(parts) < 2:
        return []
    mods = []
    for part in parts[:-1]:
        if part in ("ctrl", "control"):
            mods.append(("ctrl_l", "ctrl"))
        elif part in ("alt", "menu"):
            mods.append(("alt_l", "alt"))
        elif part in ("shift",):
            mods.append(("shift_l", "shift"))
        elif part in ("win", "super", "meta"):
            mods.append(("cmd_l", "cmd"))
    key = parts[-1]
    return [(mod, code) for mod, code in mods] + [(f"Key.{key}", key)]


def _pynput_key(key_str: str) -> str:
    """Преобразует 'j' или 'Key.f1' в формат pynput."""
    if key_str.startswith("Key."):
        return key_str
    if len(key_str) == 1:
        return key_str
    return f"Key.{key_str}"


class HotkeyListener:
    """Слушает глобальное сочетание клавиш и вызывает callback.

    Использует pynput, если доступен. Работает в фоновом потоке.
    """

    def __init__(self, hotkey: str, callback: Callable[[], None]) -> None:
        self._hotkey = hotkey
        self._callback = callback
        self._listener: object | None = None
        self._thread: threading.Thread | None = None

    @property
    def available(self) -> bool:
        """Доступен ли модуль pynput."""
        try:
            import pynput  # type: ignore[import-not-found]  # noqa: F401
            return True
        except ImportError:
            return False

    def start(self) -> None:
        """Запускает фоновый слушатель горячих клавиш."""
        try:
            from pynput import keyboard  # type: ignore[import-not-found]
        except ImportError:
            log.info("pynput не установлен — горячие клавиши недоступны")
            return

        combo = _parse_hotkey(self._hotkey)
        if not combo:
            log.warning("Не удалось разобрать горячую клавишу: %s", self._hotkey)
            return

        current: set[str] = set()

        def on_press(key: object) -> bool:
            try:
                key_name = key.char if hasattr(key, "char") and key.char else str(key)
            except AttributeError:
                key_name = str(key)
            current.add(key_name.lower())
            # Проверяем, все ли клавиши комбинации нажаты.
            pressed = {name for _, name in combo}
            if pressed <= current:
                current.clear()
                threading.Thread(target=self._callback, daemon=True).start()
            return True

        def on_release(key: object) -> bool:
            try:
                key_name = key.char if hasattr(key, "char") and key.char else str(key)
            except AttributeError:
                key_name = str(key)
            current.discard(key_name.lower())
            return True

        self._listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        self._thread = threading.Thread(target=self._listener.start, name="hotkey", daemon=True)
        self._thread.start()
        log.info("Горячая клавиша %s активна", self._hotkey)

    def stop(self) -> None:
        """Останавливает слушатель."""
        if self._listener is not None:
            try:
                self._listener.stop()  # type: ignore[attr-defined]
            except Exception:
                pass
            self._listener = None
