"""Детектор ключевого слова «Джарвис»."""

from __future__ import annotations

import logging

import numpy as np

from ..config import WakeWordConfig

log = logging.getLogger(__name__)


class WakeWordDetector:
    """Обёртка над openWakeWord с предобученной моделью hey_jarvis."""

    def __init__(self, config: WakeWordConfig) -> None:
        self.config = config
        self._model: object | None = None
        self._key = ""
        if config.enabled:
            self._load()

    @property
    def available(self) -> bool:
        """Доступен ли акустический детектор."""
        return self._model is not None

    def _load(self) -> None:
        """Загружает модель openWakeWord, если пакет установлен."""
        try:
            from openwakeword import utils  # type: ignore[import-not-found]
            from openwakeword.model import Model  # type: ignore[import-not-found]
        except ImportError:
            log.warning("openwakeword не установлен: пробуждение будет по тексту после STT")
            return
        try:
            utils.download_models([self.config.model])
            self._model = Model(wakeword_models=[self.config.model])
        except Exception:  # загрузка моделей может упасть без сети
            log.exception("Не удалось загрузить модель пробуждения")
            self._model = None
            return
        self._key = self.config.model
        log.info("Детектор пробуждения готов: %s", self.config.model)

    def detect(self, frame: np.ndarray) -> bool:
        """Проверяет кадр int16 на наличие ключевого слова."""
        if self._model is None:
            return False
        scores = self._model.predict(frame)  # type: ignore[attr-defined]
        score = max(scores.values()) if scores else 0.0
        return score >= self.config.threshold

    def reset(self) -> None:
        """Сбрасывает внутренний буфер модели после срабатывания."""
        if self._model is not None:
            self._model.reset()  # type: ignore[attr-defined]

    def text_contains_wake_word(self, text: str) -> bool:
        """Резервная проверка ключевого слова по распознанному тексту."""
        normalized = text.lower().replace("ё", "е")
        return any(phrase in normalized for phrase in self.config.fallback_phrases)

    def strip_wake_word(self, text: str) -> str:
        """Убирает обращение «Джарвис» из начала команды."""
        cleaned = text.strip()
        lowered = cleaned.lower().replace("ё", "е")
        for phrase in sorted(self.config.fallback_phrases, key=len, reverse=True):
            index = lowered.find(phrase)
            if index != -1:
                cleaned = (cleaned[:index] + cleaned[index + len(phrase) :]).strip()
                break
        return cleaned.lstrip(" ,.!?:-").strip()
