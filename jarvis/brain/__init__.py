"""Выбор мозга ассистента в зависимости от конфигурации."""

from __future__ import annotations

import logging

from ..config import Config
from ..skills import SkillRegistry
from .base import Brain, Message, ToolCall
from .offline_brain import OfflineBrain
from .ollama_brain import OllamaBrain
from .openai_brain import OpenAIBrain

log = logging.getLogger(__name__)

__all__ = [
    "Brain",
    "Message",
    "ToolCall",
    "OfflineBrain",
    "OllamaBrain",
    "OpenAIBrain",
    "build_brain",
]


def build_brain(config: Config, skills: SkillRegistry) -> Brain:
    """Создаёт мозг, откатываясь в офлайн-режим при недоступности бэкенда."""
    backend = config.brain.backend.lower()
    if backend == "offline":
        return OfflineBrain(config.brain, skills)
    try:
        if backend == "openai":
            return OpenAIBrain(config.brain, skills, config.openai_api_key)
        if backend == "ollama":
            brain = OllamaBrain(config.brain, skills)
            brain.check()
            return brain
    except RuntimeError as exc:
        log.error("Бэкенд %s недоступен: %s. Перехожу в офлайн-режим.", backend, exc)
        return OfflineBrain(config.brain, skills)
    log.error("Неизвестный бэкенд %s. Использую офлайн-режим.", backend)
    return OfflineBrain(config.brain, skills)
