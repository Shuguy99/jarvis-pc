"""Реестр навыков: описание инструментов для LLM и их исполнение.

Поддерживает динамическую фильтрацию инструментов по запросу пользователя,
чтобы маленькие LLM модели не тонули в сотнях нерелевантных tool definitions.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)

SkillHandler = Callable[..., str]

# Минимальная длина слова для индексации (короче — предлоги/местоимения).
_MIN_WORD_LEN = 3

# Навыки, которые ВСЕГДА включаются в выдачу (универсальные).
_ALWAYS_INCLUDE: set[str] = {
    "current_time", "current_date", "system_status",
    "battery_status", "web_search", "open_app",
    "remember_fact", "recall_fact",
}

# Слова-стоп: не учитываются при фильтрации.
_STOP_WORDS: frozenset[str] = frozenset({
    "и", "в", "на", "с", "что", "это", "как", "для", "но", "не",
    "да", "нет", "а", "по", "от", "ко", "из", "за", "к", "у",
    "то", "он", "она", "они", "я", "ты", "мы", "все", "мой", "её",
    "the", "a", "an", "is", "are", "do", "can", "please", "just",
    "джарвис", "jarvis", "сэр", "пожалуйста", "можешь", "скажи",
})


class ConfirmationRequired(Exception):
    """Поднимается навыком, когда операция требует подтверждения пользователя.

    Атрибут message содержит текст вопроса для пользователя (передаётся в LLM).
    """
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class Skill:
    """Один навык — функция, которую может вызвать модель."""

    name: str
    description: str
    parameters: dict[str, Any]
    handler: SkillHandler
    keywords: tuple[str, ...] = ()  # дополнительные поисковые термины

    def to_openai_tool(self) -> dict[str, Any]:
        """Описание навыка в формате function calling."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    @property
    def _search_text(self) -> str:
        """Весь текст для индексации: имя + описание + ключевые слова."""
        parts = [self.name, self.description]
        if self.keywords:
            parts.append(" ".join(self.keywords))
        return " ".join(parts).lower()


def _stem(word: str) -> str:
    """Грубый стеммер для русского и английского.

    Обрезает окончания: громкости -> громк, running -> runn.
    """
    w = word.lower().strip()
    if len(w) <= 4:
        return w
    # Русские окончания
    for suffix in ("ости", "остью", "ами", "его", "ему", "ить", "ать", "яет",
                   "ного", "ные", "ный", "ная", "ное",
                   "tee", "tion", "ing", "led", "ers", "ies"):
        if w.endswith(suffix):
            return w[: -len(suffix)]
    if len(w) > 5:
        return w[: -2]
    return w


class SkillRegistry:
    """Хранит навыки и выполняет их по имени.

    Поддерживает динамическую фильтрацию: перед отправкой инструментов в LLM
    можно вызвать ``filtered_tool_specs(query)`` — вернутся только релевантные.
    """

    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}
        # Индекс: stem -> set[skill_name]
        self._index: dict[str, set[str]] = {}

    def register(self, skill: Skill) -> None:
        """Добавляет навык, запрещая дубликаты имён."""
        if skill.name in self._skills:
            raise ValueError(f"Навык {skill.name} уже зарегистрирован")
        self._skills[skill.name] = skill
        self._index_skill(skill)

    def _index_skill(self, skill: Skill) -> None:
        """Добавляет навык в поисковый индекс по стемам."""
        words: set[str] = set()
        for token in re.split(r"[^\w]+", skill._search_text):
            if len(token) >= _MIN_WORD_LEN:
                words.add(_stem(token))
        for stem in words:
            self._index.setdefault(stem, set()).add(skill.name)

    def extend(self, skills: Iterable[Skill]) -> None:
        """Регистрирует несколько навыков."""
        for skill in skills:
            self.register(skill)

    def __contains__(self, name: object) -> bool:
        return name in self._skills

    def __len__(self) -> int:
        return len(self._skills)

    @property
    def names(self) -> list[str]:
        """Имена всех навыков."""
        return sorted(self._skills)

    def tool_specs(self) -> list[dict[str, Any]]:
        """Список описаний ВСЕХ инструментов для LLM."""
        return [self._skills[name].to_openai_tool() for name in self.names]

    def filtered_tool_specs(self, query: str, max_tools: int = 40) -> list[dict[str, Any]]:
        """Возвращает tool specs, отфильтрованные по релевантности к запросу.

        1. Всегда включает универсальные навыки (_ALWAYS_INCLUDE).
        2. Стемит слова из query и ищет совпадения в индексе.
        3. Добавляет навыки, чьё имя содержит любое слово query (бонус).
        4. Сортирует по релевантности, обрезает до max_tools.
        """
        if not query:
            return self.tool_specs()

        # Собираем стемы из запроса
        query_stems: set[str] = set()
        query_words_raw: list[str] = []
        for token in re.split(r"[^\w]+", query.lower()):
            if len(token) >= _MIN_WORD_LEN and token not in _STOP_WORDS:
                query_stems.add(_stem(token))
                query_words_raw.append(token)

        # Считаем релевантность
        scores: dict[str, float] = {}
        for name in self._skills:
            scores[name] = 0.0

        # Поиск по индексу (стемы)
        for stem in query_stems:
            matched = self._index.get(stem, set())
            for name in matched:
                scores[name] += 1.0

        # Бонус за совпадение имени (целое слово из query в имени навыка)
        for name in self._skills:
            name_lower = name.lower()
            for word in query_words_raw:
                if word in name_lower:
                    scores[name] += 3.0

        # Всегда включаем
        for name in _ALWAYS_INCLUDE:
            if name in self._skills:
                scores[name] = max(scores.get(name, 0), 0.5)

        # Сортируем по убыванию релевантности
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)

        # Берём топ-N с ненулевым скором + всегда-include
        selected: list[str] = []
        for name, score in ranked:
            if score > 0 and name not in selected:
                selected.append(name)
            if len(selected) >= max_tools:
                break

        log.debug(
            "Фильтрация: %d слов -> %d из %d навыков (query: %.50s)",
            len(query_stems), len(selected), len(self._skills), query,
        )

        return [self._skills[name].to_openai_tool() for name in selected]

    def call(self, name: str, arguments: dict[str, Any] | None = None) -> str:
        """Выполняет навык и всегда возвращает текстовый результат.

        Если навык поднимает ConfirmationRequired — пробрасывает исключение выше,
        чтобы Brain мог запросить подтверждение у пользователя через LLM.
        """
        skill = self._skills.get(name)
        if skill is None:
            return f"Навык {name!r} не найден."
        try:
            return skill.handler(**(arguments or {}))
        except ConfirmationRequired:
            raise  # пробрасываем для обработки в Brain.ask()
        except TypeError as exc:
            log.warning("Некорректные аргументы для %s: %s", name, exc)
            return f"Некорректные аргументы для навыка {name!r}: {exc}"
        except Exception as exc:  # навык не должен ронять ассистента
            log.exception("Ошибка навыка %s", name)
            return f"Навык {name!r} завершился ошибкой: {exc}"


def string_param(description: str) -> dict[str, Any]:
    """Схема одиночного строкового параметра."""
    return {"type": "string", "description": description}


def object_schema(properties: dict[str, Any], required: Iterable[str] = ()) -> dict[str, Any]:
    """Схема объекта параметров для function calling."""
    return {
        "type": "object",
        "properties": properties,
        "required": list(required),
    }


def require_confirmation(message: str) -> Callable[[SkillHandler], SkillHandler]:
    """Декоратор: оборачивает handler навыка, запрашивая подтверждение перед выполнением.

    Обёрнутый handler поднимает ConfirmationRequired с указанным сообщением.
    Декоратор сохраняет оригинальную функцию в ``handler._original`` для тестов.

    Пример::

        @require_confirmation("Удалить файл {path}?")
        def delete_file(config, path: str) -> str:
            ...
    """
    def decorator(fn: SkillHandler) -> SkillHandler:
        original = fn

        def wrapper(**kwargs: Any) -> str:
            formatted = message.format(**kwargs)
            raise ConfirmationRequired(formatted)

        wrapper._original = original  # type: ignore[attr-defined]
        wrapper.__name__ = fn.__name__
        wrapper.__qualname__ = fn.__qualname__
        wrapper.__doc__ = fn.__doc__
        wrapper.__module__ = fn.__module__
        return wrapper  # type: ignore[return-value]

    return decorator


def _confirm_handler(original: SkillHandler, message: str) -> SkillHandler:
    """Вспомогательная функция: создаёт обёртку с подтверждением (для лямбд).

    Используется в build_skills, где нельзя применить декоратор к лямбде.

    Пример::

        handler=_confirm_handler(lambda path: delete_file(config, path), "Удалить {path}?")
    """
    def wrapper(**kwargs: Any) -> str:
        formatted = message.format(**kwargs)
        raise ConfirmationRequired(formatted)

    wrapper._original = original  # type: ignore[attr-defined]
    wrapper.__name__ = getattr(original, '__name__', 'confirmed_handler')
    return wrapper  # type: ignore[return-value]
