"""Мозг на локальной модели через Ollama."""

from __future__ import annotations

import uuid
from typing import Any

import requests

from ..config import BrainConfig
from ..skills import SkillRegistry
from .base import Brain, Message, ToolCall, parse_arguments

REQUEST_TIMEOUT_S = 180


def _serialize(message: Message) -> dict[str, Any]:
    """Переводит внутреннее сообщение в формат Ollama chat API."""
    if message.role == "tool":
        return {
            "role": "tool",
            "content": message.content,
            "tool_name": message.name,
        }
    payload: dict[str, Any] = {"role": message.role, "content": message.content}
    if message.tool_calls:
        payload["tool_calls"] = [
            {"function": {"name": call.name, "arguments": call.arguments}}
            for call in message.tool_calls
        ]
    return payload


class OllamaBrain(Brain):
    """Работает с локальным сервером Ollama и его поддержкой инструментов."""

    def __init__(self, config: BrainConfig, skills: SkillRegistry) -> None:
        super().__init__(config, skills)
        self._url = config.ollama_host.rstrip("/") + "/api/chat"

    def check(self) -> None:
        """Проверяет доступность сервера и наличие модели."""
        host = self.config.ollama_host.rstrip("/")
        try:
            response = requests.get(host + "/api/tags", timeout=5)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise RuntimeError(f"Ollama недоступна на {host}. Запустите «ollama serve».") from exc
        models = {item["name"] for item in response.json().get("models", [])}
        wanted = self.config.ollama_model
        if wanted not in models and f"{wanted}:latest" not in models:
            raise RuntimeError(f"Модель {wanted} не найдена. Выполните: ollama pull {wanted}")

    def _chat(self, messages: list[Message]) -> Message:
        """Отправляет историю в Ollama и разбирает ответ."""
        payload: dict[str, Any] = {
            "model": self.config.ollama_model,
            "messages": [_serialize(message) for message in messages],
            "tools": self.skills.tool_specs(),
            "stream": False,
            "options": {"temperature": self.config.temperature},
        }
        response = requests.post(self._url, json=payload, timeout=REQUEST_TIMEOUT_S)
        response.raise_for_status()
        message = response.json().get("message", {})
        calls = [
            ToolCall(
                id=uuid.uuid4().hex,
                name=call.get("function", {}).get("name", ""),
                arguments=parse_arguments(call.get("function", {}).get("arguments")),
            )
            for call in message.get("tool_calls", [])
        ]
        calls = [call for call in calls if call.name]
        return Message("assistant", message.get("content", ""), tool_calls=calls)
