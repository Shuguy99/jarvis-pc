"""Базовый слой мозга: история диалога и цикл вызова инструментов."""

from __future__ import annotations

import json
import logging
import threading
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from ..config import BrainConfig
from ..skills import SkillRegistry
from ..skills.registry import ConfirmationRequired

log = logging.getLogger(__name__)

SESSIONS_DIR = Path.home() / ".jarvis" / "sessions"
_MAX_SESSIONS = 20

# Тип коллбэка, вызываемого после каждого tool call: (имя_навыка, результат).
OnToolResult = Callable[[str, str], None]


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

    def __init__(self, config: BrainConfig, skills: SkillRegistry, on_tool_result: OnToolResult | None = None) -> None:
        self.config = config
        self.skills = skills
        self.history: list[Message] = []
        self._lock = threading.RLock()
        self._on_tool_result = on_tool_result
        # Множество подтверждённых вызовов: (skill_name, frozenset(args))
        self._confirmed: set[tuple[str, frozenset[tuple[str, Any]]]] = set()
        self._last_query: str = ""

    @abstractmethod
    def _chat(self, messages: list[Message]) -> Message:
        """Один запрос к модели; возвращает ответ ассистента."""

    def reset(self) -> None:
        """Очищает историю диалога."""
        with self._lock:
            self.history.clear()
            self._confirmed.clear()
            self._delete_session()

    @staticmethod
    def _hydrate_message(item: dict) -> Message:
        """Восстанавливает Message из JSON, конвертируя tool_calls dicts → ToolCall."""
        item = {k: v for k, v in item.items() if k in Message.__dataclass_fields__}
        if "tool_calls" in item and isinstance(item["tool_calls"], list):
            item["tool_calls"] = [
                ToolCall(**tc) if isinstance(tc, dict) else tc
                for tc in item["tool_calls"]
            ]
        return Message(**item)

    @staticmethod
    def _session_path(name: str = "") -> Path:
        """Возвращает путь к файлу сессии."""
        safe_name = "".join(ch for ch in name if ch.isalnum() or ch in "-_") if name else ""
        if safe_name:
            return SESSIONS_DIR / f"{safe_name}.json"
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        return SESSIONS_DIR / f"{stamp}.json"

    def save_session(self, name: str = "") -> None:
        """Сохраняет историю диалога в файл."""
        try:
            SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
            data = [asdict(m) for m in self.history]
            if not data:
                return
            path = self._session_path(name)
            path.write_text(
                json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8"
            )
            log.debug("Сессия сохранена: %s (%d сообщений)", path.name, len(data))
            self._rotate_sessions()
        except OSError:
            log.exception("Не удалось сохранить сессию")

    def load_session(self, name: str = "") -> None:
        """Восстанавливает историю диалога из файла."""
        # Миграция: если старый session.json существует рядом с каталогом сессий — переносим.
        legacy = SESSIONS_DIR.parent / "session.json"
        if legacy.is_file() and not SESSIONS_DIR.is_dir():
            try:
                SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
                legacy.rename(SESSIONS_DIR / "legacy.json")
                log.info("Миграция session.json → sessions/legacy.json")
            except OSError:
                log.warning("Не удалось мигрировать session.json")

        path = self._session_path(name) if name else self._latest_session_path()
        if path is None or not path.is_file():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                return
            with self._lock:
                self.history = [
                    self._hydrate_message(item)
                    for item in data
                    if isinstance(item, dict) and item.get("role") in ("user", "assistant", "tool")
                ]
            log.info("Сессия восстановлена: %s (%d сообщений)", path.name, len(self.history))
        except (json.JSONDecodeError, OSError, TypeError):
            log.warning("Файл сессии повреждён, начинаю заново: %s", path)

    @staticmethod
    def _latest_session_path() -> Path | None:
        """Возвращает путь к самой свежей сессии."""
        if not SESSIONS_DIR.is_dir():
            return None
        sessions = sorted(SESSIONS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        return sessions[0] if sessions else None

    @staticmethod
    def _rotate_sessions() -> None:
        """Удаляет самые старые сессии, если их больше _MAX_SESSIONS."""
        if not SESSIONS_DIR.is_dir():
            return
        sessions = sorted(SESSIONS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime)
        while len(sessions) > _MAX_SESSIONS:
            oldest = sessions.pop(0)
            try:
                oldest.unlink(missing_ok=True)
                log.debug("Удалена старая сессия: %s", oldest.name)
            except OSError:
                pass

    @staticmethod
    def list_sessions() -> list[str]:
        """Возвращает список имён доступных сессий."""
        if not SESSIONS_DIR.is_dir():
            return []
        return sorted(p.stem for p in SESSIONS_DIR.glob("*.json"))

    @staticmethod
    def _delete_session(name: str = "") -> None:
        """Удаляет файл сессии."""
        try:
            path = Brain._session_path(name) if name else Brain._latest_session_path()
            if path is not None:
                path.unlink(missing_ok=True)
        except OSError:
            pass

    def _trim(self) -> None:
        """Ограничивает историю, не разрывая пары «вызов — результат"."""
        limit = max(2, self.config.max_history)
        with self._lock:
            while len(self.history) > limit:
                del self.history[0]
                while self.history and self.history[0].role == "tool":
                    del self.history[0]

    def _messages(self) -> list[Message]:
        """История с системным промптом в начале."""
        prompt = self.config.system_prompt
        if not prompt:
            from ..skills.personality import get_profile_prompt
            prompt = get_profile_prompt()
        with self._lock:
            return [Message("system", prompt), *list(self.history)]

    def ask(self, user_text: str) -> str:
        """Обрабатывает реплику пользователя и возвращает финальный ответ."""
        with self._lock:
            self._last_query = user_text
            self.history.append(Message("user", user_text))
            self._trim()
            for _ in range(max(1, self.config.max_tool_iterations)):
                reply = self._chat(self._messages())
                self.history.append(reply)
                if not reply.tool_calls:
                    self.save_session()
                    return reply.content.strip() or "Готово, сэр."
                for call in reply.tool_calls:
                    log.info("Вызов навыка %s с %s", call.name, call.arguments)
                    call_key = (call.name, frozenset((k, v) for k, v in (call.arguments or {}).items()))
                    is_confirmed = call_key in self._confirmed
                    try:
                        result = self.skills.call(call.name, call.arguments)
                    except ConfirmationRequired as cr:
                        if is_confirmed:
                            # Уже подтверждено — выполняем напрямую через оригинальный handler.
                            log.info("Повторный вызов подтверждённого %s — выполняем", call.name)
                            skill = self.skills._skills.get(call.name)
                            if skill and hasattr(skill.handler, '_original'):
                                result = skill.handler._original(**(call.arguments or {}))
                            else:
                                result = f"Навык «{call.name}» требует подтверждения, но не удалось выполнить."
                        else:
                            # Навык запросил подтверждение — отправляем вопрос пользователю.
                            log.info("Подтверждение для %s: %s", call.name, cr.message)
                            self._confirmed.add(call_key)
                            confirm_msg = (
                                f"⚠️ Требуется подтверждение: {cr.message}\n"
                                f"Ответьте «да»/«подтверждаю» для выполнения или «нет»/«отмена» для отмены."
                            )
                            self.history.append(
                                Message(
                                    role="tool",
                                    content=confirm_msg,
                                    tool_call_id=call.id,
                                    name=call.name,
                                )
                            )
                            reply = self._chat(self._messages())
                            self.history.append(reply)
                            if not reply.tool_calls:
                                self.save_session()
                                return reply.content.strip() or confirm_msg
                            continue
                    if self._on_tool_result is not None:
                        try:
                            self._on_tool_result(call.name, result)
                        except Exception:
                            log.exception("Ошибка в on_tool_result для %s", call.name)
                    self.history.append(
                        Message(
                            role="tool",
                            content=result,
                            tool_call_id=call.id,
                            name=call.name,
                        )
                    )
                self._trim()
            self.save_session()
            return "Слишком много вложенных действий, сэр. Прерываю цикл."
