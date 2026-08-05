"""Запуск HUD вместе с рабочим циклом ассистента в отдельном потоке."""

from __future__ import annotations

import logging
import os
import signal
import sys
import threading
from collections.abc import Callable

from PySide6.QtCore import QMetaObject, Qt, QTimer
from PySide6.QtWidgets import QApplication

from ..assistant import Assistant, Event
from ..config import Config
from .hud import HudWindow

log = logging.getLogger(__name__)

Driver = Callable[[Assistant], None]


def _voice_driver(assistant: Assistant) -> None:
    """Обычный режим HUD: слушать микрофон до закрытия окна."""
    assistant.listen_forever()


def run_hud(config: Config, driver: Driver = _voice_driver) -> int:
    """Показывает оверлей и крутит рабочий цикл ассистента до закрытия окна."""
    app = QApplication.instance() or QApplication(sys.argv)
    window_holder: dict[str, HudWindow] = {}

    def sink(event: Event) -> None:
        window = window_holder.get("window")
        if window is not None:
            window.submit(event)

    assistant = Assistant(config, sink)

    def close() -> None:
        assistant.shutdown()
        # Завершать цикл событий нужно в его же потоке: close() зовётся и из рабочего.
        QMetaObject.invokeMethod(app, "quit", Qt.ConnectionType.QueuedConnection)

    window = HudWindow(config.ui, close)
    window_holder["window"] = window
    window.show()

    # Ctrl+C в консоли должен закрывать оверлей, а не бросать исключение в таймер.
    signal.signal(signal.SIGINT, lambda *_: close())
    # Пустой таймер: без него Qt не отдаёт управление интерпретатору для сигналов.
    heartbeat = QTimer()
    heartbeat.start(200)
    heartbeat.timeout.connect(lambda: None)

    def work() -> None:
        try:
            driver(assistant)
        except Exception:
            log.exception("Рабочий цикл остановлен из-за ошибки")
        finally:
            close()

    thread = threading.Thread(target=work, name="jarvis-worker", daemon=True)
    thread.start()
    code = app.exec()
    assistant.shutdown()
    sys.stdout.flush()
    sys.stderr.flush()
    # Рабочий поток может висеть на чтении ввода; обычное завершение упёрлось бы в его блокировки.
    os._exit(code)
