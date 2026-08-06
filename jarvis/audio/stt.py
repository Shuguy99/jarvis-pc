"""Распознавание речи через faster-whisper."""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

import numpy as np

from ..config import SttConfig

if TYPE_CHECKING:
    from faster_whisper import WhisperModel

log = logging.getLogger(__name__)

MIN_AUDIO_S = 0.3


class SpeechToText:
    """Локальное распознавание речи без обращения к облаку."""

    def __init__(self, config: SttConfig) -> None:
        self.config = config
        self._model: WhisperModel | None = None
        self._lock = threading.Lock()

    def load(self) -> WhisperModel:
        """Загружает модель Whisper в память и возвращает её."""
        if self._model is not None:
            return self._model
        with self._lock:
            # Повторная проверка после захвата блокировки (double-checked locking).
            if self._model is not None:
                return self._model
            from faster_whisper import WhisperModel  # type: ignore[import-not-found]

            device = self.config.device
            if device == "auto":
                device = "cuda" if self._cuda_available() else "cpu"
            compute_type = self.config.compute_type
            if device == "cuda" and compute_type == "int8":
                compute_type = "float16"
            log.info("Загружаю Whisper %s на %s", self.config.model, device)
            self._model = WhisperModel(self.config.model, device=device, compute_type=compute_type)
            return self._model

    @staticmethod
    def _cuda_available() -> bool:
        """Проверяет наличие CUDA, не требуя torch как обязательной зависимости."""
        try:
            import torch  # type: ignore[import-not-found]
        except ImportError:
            return False
        return bool(torch.cuda.is_available())

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> str:
        """Возвращает распознанный текст для float32-сигнала."""
        if audio.size < MIN_AUDIO_S * sample_rate:
            return ""
        model = self.load()
        segments, _ = model.transcribe(
            audio,
            language=self.config.language,
            beam_size=self.config.beam_size,
            vad_filter=True,
        )
        text = " ".join(segment.text.strip() for segment in segments)
        return " ".join(text.split())
