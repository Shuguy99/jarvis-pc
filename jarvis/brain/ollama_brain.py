"""Мозг на локальной модели через Ollama с retry и circuit breaker."""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

import requests

from ..config import BrainConfig
from ..skills import SkillRegistry
from .base import Brain, Message, OnToolResult, ToolCall, parse_arguments

log = logging.getLogger(__name__)

REQUEST_TIMEOUT_S = 180
MAX_RETRIES = 2
RETRY_BACKOFF_S = 3.0
# Сколько секунд ждать перед повторной попыткой после ошибки.
CIRCUIT_RESET_S = 60.0
# Через сколько секунд circuit breaker снова разрешает запросы.


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
    """Работает с локальным сервером Ollama и его поддержкой инструментов.

    Встроенный circuit breaker: при трёх подряд неудачных запросах
    блокирует вызовы на CIRCUIT_RESET_S секунд, чтобы не нагружать
    зависший Ollama-сервер.
    """

    def __init__(self, config: BrainConfig, skills: SkillRegistry, on_tool_result: OnToolResult | None = None) -> None:
        super().__init__(config, skills, on_tool_result)
        self._url = config.ollama_host.rstrip("/") + "/api/chat"
        self._consecutive_failures = 0
        self._circuit_open_until: float = 0.0

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

    def _is_circuit_open(self) -> bool:
        """Проверяет, открыт ли circuit breaker (запросы заблокированы)."""
        if self._circuit_open_until <= time.monotonic():
            self._circuit_open_until = 0.0
            return False
        return True

    def _record_success(self) -> None:
        """Сбрасывает счётчик ошибок при успешном запросе."""
        self._consecutive_failures = 0

    def _record_failure(self) -> None:
        """Увеличивает счётчик и, при пороге, размыкает circuit breaker."""
        self._consecutive_failures += 1
        if self._consecutive_failures >= 3:
            self._circuit_open_until = time.monotonic() + CIRCUIT_RESET_S
            log.warning(
                "Circuit breaker открыт: Ollama не отвечает %d раз. "
                "Пауза %.0f секунд.",
                self._consecutive_failures,
                CIRCUIT_RESET_S,
            )

    def _chat(self, messages: list[Message]) -> Message:
        """Отправляет историю в Ollama с retry и circuit breaker."""
        if self._is_circuit_open():
            remaining = self._circuit_open_until - time.monotonic()
            log.warning("Circuit breaker: ждём %.0f с до следующей попытки", remaining)
            return Message(
                "assistant",
                f"Сэр, Ollama не отвечает уже несколько попыток. "
                f"Подождите {int(remaining) + 1} секунд или перезапустите «ollama serve».",
            )

        payload: dict[str, Any] = {
            "model": self.config.ollama_model,
            "messages": [_serialize(message) for message in messages],
            "tools": self.skills.tool_specs(),
            "stream": False,
            "options": {"temperature": self.config.temperature},
        }

        last_exc: Exception | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = requests.post(self._url, json=payload, timeout=REQUEST_TIMEOUT_S)
                response.raise_for_status()
                self._record_success()
                return self._parse_response(response.json())
            except requests.ConnectionError as exc:
                last_exc = exc
                log.warning("Ollama недоступна (попытка %d/%d): %s", attempt, MAX_RETRIES, exc)
            except requests.Timeout as exc:
                last_exc = exc
                log.warning("Ollama не отвечает (попытка %d/%d): %s", attempt, MAX_RETRIES, exc)
            except requests.HTTPError as exc:
                last_exc = exc
                # 4xx — не retry, это ошибка запроса
                if exc.response is not None and 400 <= exc.response.status_code < 500:
                    log.error("Ollama вернула ошибку клиента: %s", exc)
                    self._record_failure()
                    return Message("assistant", f"Ollama сообщила об ошибке: {exc}")
                log.warning("Ollama вернула ошибку сервера (попытка %d/%d): %s", attempt, MAX_RETRIES, exc)
            except requests.RequestException as exc:
                last_exc = exc
                log.warning("Ошибка сети при обращении к Ollama (попытка %d/%d): %s", attempt, MAX_RETRIES, exc)

            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF_S * attempt)

        self._record_failure()
        return Message(
            "assistant",
            f"Сэр, не удалось получить ответ от Ollama после {MAX_RETRIES} попыток. "
            f"Проверьте, запущен ли «ollama serve» и доступна ли модель {self.config.ollama_model}.",
        )

    @staticmethod
    def _parse_response(data: dict[str, Any]) -> Message:
        """Разбирает ответ Ollama в внутренний формат."""
        message = data.get("message", {})
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
