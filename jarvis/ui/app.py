"""Запуск HUD вместе с голосовым циклом ассистента в отдельном потоке."""

from __future__ import annotations

import logging
import sys
import threading

from ..assistant import Assistant, Event
from ..config import Config

log = logging.getLogger(__name__)


def run_hud(config: Config) -> int:
    """Показывает оверлей и слушает микрофон до закрытия окна."""
    from PySide6.QtWidgets import QApplication  # noqa: delayed import — optional dep

    from .hud import HudWindow

    app = QApplication.instance() or QApplication(sys.argv)
    window_holder: dict[str, HudWindow] = {}

    def sink(event: Event) -> None:
        window = window_holder.get("window")
        if window is not None:
            window.submit(event)

    assistant = Assistant(config, sink)
    window = HudWindow(config.ui, assistant.shutdown)
    window_holder["window"] = window
    window.show()

    def voice_loop() -> None:
        try:
            assistant.listen_forever()
        except Exception:
            log.exception("Голосовой цикл остановлен из-за ошибки")

    thread = threading.Thread(target=voice_loop, name="jarvis-voice", daemon=True)
    thread.start()
    try:
        return app.exec()
    finally:
        assistant.shutdown()
