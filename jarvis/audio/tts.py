"""Синтез речи: офлайн SAPI5 или neural-голоса Microsoft Edge."""

from __future__ import annotations

import asyncio
import logging
import os
import platform
import subprocess
import tempfile
import threading
import uuid
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
        try:
            engine.say(text)  # type: ignore[attr-defined]
            engine.runAndWait()  # type: ignore[attr-defined]
        except Exception:
            log.exception("Системный TTS не смог произнести текст")
            return False
        return True

    def _speak_edge(self, text: str) -> bool:
        """Произносит текст neural-голосом Edge TTS."""
        try:
            import edge_tts  # type: ignore[import-not-found]
        except ImportError:
            log.warning("edge-tts не установлен, откат на системный голос")
            return False
        tmp = Path(tempfile.gettempdir()) / f"jarvis-tts-{uuid.uuid4().hex[:8]}.mp3"

        async def synthesize() -> None:
            communicate = edge_tts.Communicate(text, self.config.edge_voice)
            await communicate.save(str(tmp))

        try:
            # Если уже есть event loop (например, Qt), не создаём новый.
            try:
                loop = asyncio.get_running_loop()
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(asyncio.run, synthesize())
                    future.result(timeout=30)
            except RuntimeError:
                asyncio.run(synthesize())
        except Exception:
            log.exception("Edge TTS не смог синтезировать речь")
            tmp.unlink(missing_ok=True)
            return False
        try:
            return self._play(tmp)
        finally:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass

    @staticmethod
    def _play(path: Path) -> bool:
        """Воспроизводит аудиофайл доступным способом."""
        # Защита: путь должен быть нормализованным абсолютным путём к файлу .mp3/.wav.
        try:
            resolved = path.resolve()
            if not resolved.is_file():
                log.error("Файл не существует: %s", resolved)
                return False
            if resolved.suffix.lower() not in (".mp3", ".wav", ".ogg", ".flac"):
                log.error("Неподдерживаемый формат: %s", resolved.suffix)
                return False
            path = resolved
        except (OSError, ValueError) as exc:
            log.error("Некорректный путь: %s — %s", path, exc)
            return False

        try:
            from playsound3 import playsound  # type: ignore[import-not-found]

            # playsound3 блокирует и не умеет timeout,
            # поэтому запускаем в потоке с ограничением.
            result = [False]
            def _play_thread() -> None:
                try:
                    playsound(str(path))
                    result[0] = True
                except Exception:
                    log.debug("playsound3 не смог воспроизвести %s", path)
            t = threading.Thread(target=_play_thread, daemon=True)
            t.start()
            t.join(timeout=30)
            if result[0]:
                return True
            log.warning("playsound3 завис, переключаюсь на другой плеер")
        except ImportError:
            pass
        if platform.system() == "Windows":
            # Экранируем путь одинарными кавычками для PowerShell
            # и дополнительно оборачиваем в двойные кавычки.
            safe_path = str(path).replace("'", "''")
            subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    f"(New-Object Media.SoundPlayer '{safe_path}').PlaySync();",
                ],
                check=False,
            )
            return True
        # Linux / macOS: пробуем плееры по порядку.
        players: list[tuple[list[str], bool]] = [
            (["ffplay", "-nodisp", "-autoexit", str(path)], True),
            (["mpv", "--no-video", "--really-quiet", str(path)], True),
            (["aplay", str(path)], False),
        ]
        for cmd, _shell in players:
            try:
                subprocess.run(cmd, check=False, timeout=60)
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
        # Подхватываем голос и скорость из текущего профиля.
        self._apply_profile()
        with self._lock:
            if self.config.engine == "edge" and self._speak_edge(clean):
                return
            if not self._speak_sapi(clean):
                log.info("TTS недоступен, ответ только текстом: %s", clean)

    def _apply_profile(self) -> None:
        """Обновляет голос и скорость из текущего профиля личности."""
        try:
            from ..skills.personality import get_profile_voice, get_profile_tts_rate
            voice = get_profile_voice()
            rate = get_profile_tts_rate()
            if voice and voice != self.config.edge_voice:
                self.config.edge_voice = voice
                log.info("Голос переключён на %s", voice)
            if rate != self.config.rate:
                self.config.rate = rate
        except Exception:
            log.debug("Не удалось применить профиль голоса")
