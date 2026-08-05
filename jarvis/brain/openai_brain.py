"""Мозг на облачном OpenAI-совместимом API."""

from __future__ import annotations

import json
import uuid
from typing import Any

from ..config import BrainConfig
from ..skills import SkillRegistry
from .base import Brain, Message, ToolCall, parse_arguments


def _serialize(message: Message) -> dict[str, Any]:
    """Переводит внутреннее сообщение в формат OpenAI."""
    if message.role == "tool":
        return {
            "role": "tool",
            "tool_call_id": message.tool_call_id,
            "content": message.content,
        }
    payload: dict[str, Any] = {"role": message.role, "content": message.content}
    if message.tool_calls:
        payload["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {
                    "name": call.name,
                    "arguments": json.dumps(call.arguments, ensure_ascii=False),
                },
            }
            for call in message.tool_calls
        ]
    return payload


class OpenAIBrain(Brain):
    """Использует Chat Completions API с нативным function calling."""

    def __init__(self, config: BrainConfig, skills: SkillRegistry, api_key: str):
        super().__init__(config, skills)
        try:
            from openai import OpenAI  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError("Не установлен пакет openai. Выполните: pip install openai") from exc
        if not api_key:
            raise RuntimeError("Не задан OPENAI_API_KEY. Добавьте ключ в переменные окружения.")
        kwargs: dict[str, Any] = {"api_key": api_key}
        if config.openai_base_url:
            kwargs["base_url"] = config.openai_base_url
        self._client = OpenAI(**kwargs)

    def _chat(self, messages: list[Message]) -> Message:
        """Отправляет историю в OpenAI и разбирает ответ."""
        response = self._client.chat.completions.create(
            model=self.config.openai_model,
            messages=[_serialize(message) for message in messages],
            tools=self.skills.tool_specs(),
            temperature=self.config.temperature,
        )
        choice = response.choices[0].message
        calls = [
            ToolCall(
                id=call.id or uuid.uuid4().hex,
                name=call.function.name,
                arguments=parse_arguments(call.function.arguments),
            )
            for call in (choice.tool_calls or [])
        ]
        return Message("assistant", choice.content or "", tool_calls=calls)
