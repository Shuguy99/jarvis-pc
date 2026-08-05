"""Базовый слой мозга: история диалога и цикл вызова инструментов."""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from ..config import BrainConfig
from ..skills import SkillRegistry

log = logging.getLogger(__name__)


@dataclass
class ToolCall:
    """Запрос модели на вызов навыка."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class Message:
    """Одно сообщение диалога во внутреннем формате."""

    role: str
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str = ""
    name: str = ""


def parse_arguments(raw: Any) -> dict[str, Any]:
    """Приводит аргументы инструмента к словарю, что бы ни прислала модель."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            log.warning("Не удалось разобрать аргументы: %s", raw)
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


class Brain(ABC):
    """Общая логика диалога: история, системный промпт, цикл инструментов."""

    def __init__(self, config: BrainConfig, skills: SkillRegistry) -> None:
        self.config = config
        self.skills = skills
        self.history: list[Message] = []

    @abstractmethod
    def _chat(self, messages: list[Message]) -> Message:
        """Один запрос к модели; возвращает ответ ассистента."""

    def reset(self) -> None:
        """Очищает историю диалога."""
        self.history.clear()

    def _trim(self) -> None:
        """Ограничивает историю, не разрывая пары «вызов — результат»."""
        limit = max(2, self.config.max_history)
        while len(self.history) > limit:
            del self.history[0]
            while self.history and self.history[0].role == "tool":
                del self.history[0]

    def _messages(self) -> list[Message]:
        """История с системным промптом в начале."""
        return [Message("system", self.config.system_prompt), *self.history]

    def ask(self, user_text: str) -> str:
        """Обрабатывает реплику пользователя и возвращает финальный ответ."""
        self.history.append(Message("user", user_text))
        self._trim()
        for _ in range(max(1, self.config.max_tool_iterations)):
            reply = self._chat(self._messages())
            self.history.append(reply)
            if not reply.tool_calls:
                return reply.content.strip() or "Готово, сэр."
            for call in reply.tool_calls:
                log.info("Вызов навыка %s с %s", call.name, call.arguments)
                result = self.skills.call(call.name, call.arguments)
                self.history.append(
                    Message(
                        role="tool",
                        content=result,
                        tool_call_id=call.id,
                        name=call.name,
                    )
                )
            self._trim()
        return "Слишком много вложенных действий, сэр. Прерываю цикл."
