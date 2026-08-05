"""Синтез речи: офлайн SAPI5 или neural-голоса Microsoft Edge."""

from __future__ import annotations

import asyncio
import logging
import platform
import subprocess
import tempfile
import threading
from pathlib import Path

from ..config import TtsConfig

log = logging.getLogger(__name__)


class Speaker:
    """Озвучивает текст выбранным движком, сериализуя вызовы."""

    def __init__(self, config: TtsConfig) -> None:
        self.config = config
        self._lock = threading.Lock()
        self._engine: object | None = None

    def _sapi_engine(self) -> object | None:
        """Ленивая инициализация pyttsx3."""
        if self._engine is not None:
            return self._engine
        try:
            import pyttsx3  # type: ignore[import-not-found]
        except ImportError:
            log.warning("pyttsx3 не установлен")
            return None
        driver = "sapi5" if platform.system() == "Windows" else None
        engine = pyttsx3.init(driver) if driver else pyttsx3.init()
        engine.setProperty("rate", self.config.rate)
        engine.setProperty("volume", max(0.0, min(1.0, self.config.volume)))
        if self.config.voice:
            for voice in engine.getProperty("voices"):
                if self.config.voice.lower() in f"{voice.id} {voice.name}".lower():
                    engine.setProperty("voice", voice.id)
                    break
        self._engine = engine
        return engine

    def _speak_sapi(self, text: str) -> bool:
        """Произносит текст через системный движок."""
        engine = self._sapi_engine()
        if engine is None:
            return False
        engine.say(text)  # type: ignore[attr-defined]
        engine.runAndWait()  # type: ignore[attr-defined]
        return True

    def _speak_edge(self, text: str) -> bool:
        """Произносит текст neural-голосом Edge TTS."""
        try:
            import edge_tts  # type: ignore[import-not-found]
        except ImportError:
            log.warning("edge-tts не установлен, откат на системный голос")
            return False
        path = Path(tempfile.gettempdir()) / "jarvis-tts.mp3"

        async def synthesize() -> None:
            communicate = edge_tts.Communicate(text, self.config.edge_voice)
            await communicate.save(str(path))

        try:
            asyncio.run(synthesize())
        except Exception:
            log.exception("Edge TTS не смог синтезировать речь")
            return False
        return self._play(path)

    @staticmethod
    def _play(path: Path) -> bool:
        """Воспроизводит аудиофайл доступным способом."""
        try:
            from playsound3 import playsound  # type: ignore[import-not-found]

            playsound(str(path))
            return True
        except ImportError:
            pass
        if platform.system() == "Windows":
            subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    f"(New-Object Media.SoundPlayer '{path}').PlaySync();",
                ],
                check=False,
            )
            return True
        for player in ("ffplay", "aplay", "mpv"):
            try:
                subprocess.run([player, "-nodisp", "-autoexit", str(path)], check=False)
                return True
            except FileNotFoundError:
                continue
        log.error("Не нашёл проигрыватель для %s", path)
        return False

    def say(self, text: str) -> None:
        """Озвучивает текст; при сбое движка откатывается на системный голос."""
        clean = " ".join(text.split())
        if not clean:
            return
        with self._lock:
            if self.config.engine == "edge" and self._speak_edge(clean):
                return
            if not self._speak_sapi(clean):
                log.info("TTS недоступен, ответ только текстом: %s", clean)
