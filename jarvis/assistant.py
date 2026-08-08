"""Ядро ассистента: связывает аудио, мозг, навыки и интерфейс."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

import numpy as np

from .audio import Microphone, Speaker, SpeechRecorder, SpeechToText, WakeWordDetector
from .audio.hotkey import HotkeyListener
from .brain import Brain, build_brain
from .config import Config
from .monitor import SystemMonitor
from .profiles import ProfileManager
from .skills import Services, SkillRegistry, build_registry

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
    preview_url: str = ""  # Если задан — показать всплывающее окно с результатами поиска


EventSink = Callable[[Event], None]


class Assistant:
    """Оркестратор: слушает, понимает, выполняет и отвечает."""

    def __init__(self, config: Config, sink: EventSink | None = None) -> None:
        self.config = config
        self._sink = sink or (lambda event: None)
        # Профили: создаём менеджер и применяем текущий профиль
        self.profiles = ProfileManager(
            custom_profiles=config.skills.profiles.custom if config.skills.profiles.enabled else None,
        )
        self._apply_profile(self.profiles.current)
        self.speaker = Speaker(config.tts)
        self.skills: SkillRegistry
        self.services: Services
        self.skills, self.services = build_registry(config, self._announce, self.profiles)
        self.monitor = SystemMonitor(config.monitor, self._announce)
        self.brain: Brain = build_brain(config, self.skills, on_tool_result=self._on_tool_result)
        self.brain.load_session()
        self.stt = SpeechToText(config.stt)
        self.wake_word = WakeWordDetector(config.wake_word)
        self.recorder = SpeechRecorder(config.mic)
        self._stop = threading.Event()
        # RLock: навык может заговорить прямо во время обработки команды.
        self._busy = threading.RLock()
        self._hotkey = HotkeyListener(config.hotkey, self.push_to_talk)
        log.info(
            "Мозг: %s, навыков: %d, профиль: %s, акустическое пробуждение: %s",
            type(self.brain).__name__,
            len(self.skills),
            self.profiles.current.name,
            "да" if self.wake_word.available else "нет",
        )

    def _emit(self, state: State, text: str = "", speaker: str = "", *, preview_url: str = "") -> None:
        """Публикует событие в интерфейс, не позволяя UI уронить ядро."""
        try:
            self._sink(Event(state, text, speaker, preview_url=preview_url))
        except Exception:
            log.exception("Ошибка обработчика событий интерфейса")

    def _announce(self, text: str) -> None:
        """Инициативное сообщение ассистента (таймер, предупреждение мониторинга)."""
        # Не перебиваем диалог: ждём, пока текущая реплика договорит.
        with self._busy:
            self._emit(State.SPEAKING, text, "jarvis")
            self.speaker.say(text)
            self._emit(State.IDLE)

    def _on_tool_result(self, tool_name: str, result_text: str) -> None:
        """Коллбэк от мозга: если это web_search — показывает popup с результатами."""
        if tool_name != "web_search" or not result_text:
            return
        # Не показываем preview если результат — fallback (открытие браузера).
        if "открыл в браузере" in result_text.lower():
            return
        from .skills.web import _last_search_url
        self._emit(State.SPEAKING, result_text, "jarvis", preview_url=_last_search_url)

    def handle_text(self, text: str) -> str:
        """Обрабатывает текстовую команду и возвращает ответ."""
        command = text.strip()
        if not command:
            return ""
        # Проверяем алиасы (skills.aliases + верхнеуровневые)
        command_lower = command.lower()
        all_aliases = {**self.config.aliases, **self.config.skills.aliases}
        for alias, expansion in all_aliases.items():
            if command_lower == alias.lower():
                log.info("Алиас '%s' -> '%s'", alias, expansion)
                command = expansion
                break
        with self._busy:
            self._emit(State.THINKING, command, "user")
            try:
                reply = self.brain.ask(command)
            except Exception:
                log.exception("Ошибка мозгового центра")
                reply = "Проблема в нейронной сети, сэр. Попробуйте ещё раз."
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
        self._hotkey.stop()
        self.monitor.shutdown()
        self.services.shutdown()

    def _handle_utterance(self, audio: np.ndarray, require_wake_word: bool) -> None:
        """Распознаёт реплику и выполняет команду."""
        self._emit(State.THINKING)
        try:
            text = self.stt.transcribe(audio, self.config.mic.sample_rate)
        except (ImportError, RuntimeError) as exc:
            msg = str(exc)
            log.error("STT недоступен: %s", msg)
            self._announce(msg)
            self._emit(State.IDLE)
            return
        except Exception:
            log.exception("Ошибка распознавания речи")
            self._emit(State.IDLE)
            return
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
        self._hotkey.start()
        self.monitor.start()
        try:
            mic = Microphone(self.config.mic)
        except Exception as exc:
            log.error("Не удалось открыть микрофон: %s", exc)
            self._announce(f"Не могу получить доступ к микрофону: {exc}")
            return
        with mic:
            self._try_face_greeting()
            self._announce(self.config.greeting)
            acoustic = self.wake_word.available and self.config.wake_word.enabled
            preroll: list[np.ndarray] = []
            self._emit(State.IDLE)
            for frame in mic.frames():
                try:
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
                except Exception:
                    log.exception("Ошибка в голосовом цикле, продолжаю слушать")
                    self._emit(State.IDLE)

    def _apply_profile(self, profile) -> None:
        """Применяет профиль к конфигу: промпт, TTS, приветствие."""
        self.config.brain.system_prompt = profile.system_prompt
        self.config.greeting = profile.greeting
        # Обновляем TTS-настройки из профиля
        self.config.tts.engine = profile.engine
        self.config.tts.edge_voice = profile.edge_voice
        if profile.voice:
            self.config.tts.voice = profile.voice
        self.config.tts.rate = profile.rate
        self.config.tts.volume = profile.volume
        # Пересоздаём Speaker с новыми настройками, если уже существует
        if hasattr(self, 'speaker') and self.speaker is not None:
            self.speaker.config = self.config.tts
            self.speaker._engine = None  # сбрасываем кэш движка TTS
        log.info("Профиль применён: %s (%s)", profile.name, profile.id)

    def _try_face_greeting(self) -> None:
        """Если включены лица и лицо распознано — переключает профиль и меняет приветствие."""
        face_cfg = self.config.skills.face
        if not face_cfg.enabled:
            return
        try:
            from .face_db import recognize_face, get_face_profile
            name, distance = recognize_face(face_cfg.camera_index, face_cfg.tolerance)
            if name is None:
                return
            log.info("Лицо распознано: %s (dist=%.3f)", name, distance)
            # Проверяем привязку профиля
            if face_cfg.auto_switch_profile:
                profile_id = get_face_profile(name)
                if profile_id and profile_id != self.profiles.current_id:
                    ok, _ = self.profiles.switch(profile_id)
                    if ok:
                        self._apply_profile(self.profiles.current)
                        self.brain.reset()
            # Меняем приветствие на персональное
            if face_cfg.auto_greeting:
                self.config.greeting = f"Добрый день, {name}."
        except Exception:
            # Распознавание лиц — не критично, не должно ломать запуск
            log.debug("Автоматическое распознавание лиц недоступно")

    def switch_profile(self, profile_id: str) -> str:
        """Переключает профиль и перезагружает системный промпт мозга."""
        ok, msg = self.profiles.switch(profile_id)
        if ok:
            self._apply_profile(self.profiles.current)
            # Очищаем историю, чтобы новый промпт вступил в силу
            self.brain.reset()
        return msg

    def push_to_talk(self) -> None:
        """Одна реплика по горячей клавише, без ключевого слова."""
        with Microphone(self.config.mic) as mic:
            self._emit(State.LISTENING)
            audio = self.recorder.record(mic)
            self._handle_utterance(audio, require_wake_word=False)
            self._emit(State.IDLE)
