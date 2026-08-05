"""Ядро ассистента: связывает аудио, мозг, навыки и интерфейс."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

import numpy as np

from .audio import Microphone, Speaker, SpeechRecorder, SpeechToText, WakeWordDetector
from .brain import Brain, build_brain
from .config import Config
from .skills import SkillRegistry, TimerService, build_registry

log = logging.getLogger(__name__)


class State(str, Enum):
    """Состояние ассистента для отображения в HUD."""

    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"


@dataclass
class Event:
    """Событие для интерфейса: смена состояния или новая реплика."""

    state: State
    text: str = ""
    speaker: str = ""


EventSink = Callable[[Event], None]


class Assistant:
    """Оркестратор: слушает, понимает, выполняет и отвечает."""

    def __init__(self, config: Config, sink: EventSink | None = None) -> None:
        self.config = config
        self._sink = sink or (lambda event: None)
        self.speaker = Speaker(config.tts)
        self.skills: SkillRegistry
        self.timers: TimerService
        self.skills, self.timers = build_registry(config.skills, self._announce)
        self.brain: Brain = build_brain(config, self.skills)
        self.stt = SpeechToText(config.stt)
        self.wake_word = WakeWordDetector(config.wake_word)
        self.recorder = SpeechRecorder(config.mic)
        self._stop = threading.Event()
        self._busy = threading.Lock()
        log.info(
            "Мозг: %s, навыков: %d, акустическое пробуждение: %s",
            type(self.brain).__name__,
            len(self.skills),
            "да" if self.wake_word.available else "нет",
        )

    def _emit(self, state: State, text: str = "", speaker: str = "") -> None:
        """Публикует событие в интерфейс, не позволяя UI уронить ядро."""
        try:
            self._sink(Event(state, text, speaker))
        except Exception:
            log.exception("Ошибка обработчика событий интерфейса")

    def _announce(self, text: str) -> None:
        """Инициативное сообщение ассистента (например, срабатывание таймера)."""
        self._emit(State.SPEAKING, text, "jarvis")
        self.speaker.say(text)
        self._emit(State.IDLE)

    def handle_text(self, text: str) -> str:
        """Обрабатывает текстовую команду и возвращает ответ."""
        command = text.strip()
        if not command:
            return ""
        with self._busy:
            self._emit(State.THINKING, command, "user")
            reply = self.brain.ask(command)
            self._emit(State.SPEAKING, reply, "jarvis")
            self.speaker.say(reply)
            self._emit(State.IDLE)
        return reply

    def stop(self) -> None:
        """Просит цикл прослушивания завершиться."""
        self._stop.set()

    def shutdown(self) -> None:
        """Освобождает ресурсы ассистента."""
        self.stop()
        self.timers.shutdown()

    def _handle_utterance(self, audio: np.ndarray, require_wake_word: bool) -> None:
        """Распознаёт реплику и выполняет команду."""
        self._emit(State.THINKING)
        text = self.stt.transcribe(audio, self.config.mic.sample_rate)
        if not text:
            self._emit(State.IDLE)
            return
        log.info("Распознано: %s", text)
        if require_wake_word:
            if not self.wake_word.text_contains_wake_word(text):
                self._emit(State.IDLE)
                return
            text = self.wake_word.strip_wake_word(text)
            if not text:
                self._announce("Слушаю, сэр.")
                return
        self.handle_text(text)

    def listen_forever(self) -> None:
        """Основной голосовой цикл: пробуждение, запись, ответ."""
        preroll_frames = max(1, self.config.mic.preroll_ms // self.config.mic.frame_ms)
        with Microphone(self.config.mic) as mic:
            self._announce(self.config.greeting)
            acoustic = self.wake_word.available and self.config.wake_word.enabled
            preroll: list[np.ndarray] = []
            self._emit(State.IDLE)
            for frame in mic.frames():
                if self._stop.is_set():
                    return
                if acoustic:
                    if not self.wake_word.detect(frame):
                        continue
                    self.wake_word.reset()
                    log.info("Ключевое слово распознано")
                    self._emit(State.LISTENING)
                    audio = self.recorder.record(mic)
                    self._handle_utterance(audio, require_wake_word=False)
                    mic.drain()
                    self._emit(State.IDLE)
                    continue
                # Без акустической модели пишем всю речь и ищем «Джарвис» в тексте.
                preroll.append(frame)
                del preroll[:-preroll_frames]
                if not self.recorder.is_speech(frame, self.config.mic.sample_rate):
                    continue
                self._emit(State.LISTENING)
                audio = self.recorder.record(mic, preroll=list(preroll))
                preroll.clear()
                self._handle_utterance(audio, require_wake_word=True)
                mic.drain()
                self._emit(State.IDLE)

    def push_to_talk(self) -> None:
        """Одна реплика по горячей клавише, без ключевого слова."""
        with Microphone(self.config.mic) as mic:
            self._emit(State.LISTENING)
            audio = self.recorder.record(mic)
            self._handle_utterance(audio, require_wake_word=False)
            self._emit(State.IDLE)
