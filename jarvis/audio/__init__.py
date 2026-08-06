"""Аудиоподсистема Джарвиса: микрофон, пробуждение, STT и TTS."""

from .microphone import Microphone, SpeechRecorder
from .stt import SpeechToText
from .tts import Speaker
from .wakeword import WakeWordDetector

__all__ = [
    "Microphone",
    "SpeechRecorder",
    "SpeechToText",
    "Speaker",
    "WakeWordDetector",
]
