"""Поток микрофона и запись реплики с детектором тишины (VAD)."""

from __future__ import annotations

import collections
import logging
import queue
import time
from types import TracebackType
from typing import TYPE_CHECKING

import numpy as np

from ..config import MicConfig

if TYPE_CHECKING:
    import sounddevice as sd

log = logging.getLogger(__name__)


class Microphone:
    """Непрерывный поток 16-битного моно-аудио с микрофона."""

    def __init__(self, config: MicConfig) -> None:
        self.config = config
        self.frame_samples = int(config.sample_rate * config.frame_ms / 1000)
        self._queue: queue.Queue[np.ndarray] = queue.Queue()
        self._stream: sd.InputStream | None = None

    def __enter__(self) -> Microphone:
        self.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.stop()

    def start(self) -> None:
        """Открывает поток захвата звука."""
        import sounddevice as sd  # type: ignore[import-not-found]

        def callback(indata: np.ndarray, frames: int, time_info: object, status: object) -> None:
            if status:
                log.debug("Статус аудиопотока: %s", status)
            self._queue.put(indata[:, 0].copy())

        self._stream = sd.InputStream(
            samplerate=self.config.sample_rate,
            blocksize=self.frame_samples,
            device=self.config.device,
            dtype="int16",
            channels=1,
            callback=callback,
        )
        self._stream.start()
        log.info("Микрофон запущен: %d Гц", self.config.sample_rate)

    def stop(self) -> None:
        """Закрывает поток захвата звука."""
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def frames(self) -> collections.abc.Iterator[np.ndarray]:
        """Бесконечный генератор кадров int16."""
        while True:
            yield self._queue.get()

    def drain(self) -> None:
        """Сбрасывает накопленные кадры, чтобы не слышать собственную речь."""
        while not self._queue.empty():
            self._queue.get_nowait()


class SpeechRecorder:
    """Записывает одну реплику: ждёт речь, останавливается по тишине."""

    def __init__(self, config: MicConfig) -> None:
        self.config = config
        self._vad = self._make_vad(config.vad_aggressiveness)

    @staticmethod
    def _make_vad(aggressiveness: int) -> object | None:
        """Создаёт webrtcvad, если он установлен."""
        try:
            import webrtcvad  # type: ignore[import-not-found]
        except ImportError:
            log.warning("webrtcvad не установлен, использую детектор по громкости")
            return None
        return webrtcvad.Vad(max(0, min(3, aggressiveness)))

    def is_speech(self, frame: np.ndarray, sample_rate: int) -> bool:
        """Определяет, есть ли речь в кадре."""
        if self._vad is not None:
            return bool(self._vad.is_speech(frame.tobytes(), sample_rate))  # type: ignore[attr-defined]
        # Резервный вариант: среднеквадратичная громкость выше порога шума.
        return float(np.sqrt(np.mean(frame.astype(np.float32) ** 2))) > 500.0

    def record(self, mic: Microphone, preroll: list[np.ndarray] | None = None) -> np.ndarray:
        """Пишет реплику до наступления тишины и возвращает float32-сигнал."""
        rate = self.config.sample_rate
        silence_frames = max(1, self.config.silence_ms // self.config.frame_ms)
        collected: list[np.ndarray] = list(preroll or [])
        quiet_streak = 0
        speech_started = False
        started_at = time.monotonic()
        for frame in mic.frames():
            collected.append(frame)
            if self.is_speech(frame, rate):
                speech_started = True
                quiet_streak = 0
            elif speech_started:
                quiet_streak += 1
                if quiet_streak >= silence_frames:
                    break
            elif time.monotonic() - started_at > 4.0:
                # Пользователь не начал говорить — возвращаем пустой сигнал.
                return np.zeros(0, dtype=np.float32)
            if time.monotonic() - started_at > self.config.max_utterance_s:
                break
        audio = np.concatenate(collected) if collected else np.zeros(0, dtype=np.int16)
        return audio.astype(np.float32) / 32768.0
