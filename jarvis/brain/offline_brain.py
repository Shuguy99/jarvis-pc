"""Резервный мозг без LLM: разбор команд по ключевым словам."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from re import Pattern
from typing import Any

from ..config import BrainConfig
from ..skills import SkillRegistry
from .base import Brain, Message

MINUTE_WORDS = ("минут", "минуты", "минуту")


@dataclass(frozen=True)
class Rule:
    """Правило сопоставления фразы с навыком."""

    pattern: Pattern[str]
    skill: str
    build_args: Callable[[re.Match[str]], dict[str, Any]]


def _timer_args(match: re.Match[str]) -> dict[str, Any]:
    """Считает секунды для таймера из числа и единицы измерения."""
    amount = float(match.group("amount"))
    unit = match.group("unit")
    multiplier = 60 if unit.startswith(MINUTE_WORDS) else 1
    if unit.startswith("час"):
        multiplier = 3600
    return {"seconds": amount * multiplier, "label": match.group("label").strip()}


RULES: tuple[Rule, ...] = (
    Rule(re.compile(r"котор(ый|ая) час|сколько времени"), "current_time", lambda m: {}),
    Rule(re.compile(r"какое (сегодня )?число|какой (сегодня )?день"), "current_date", lambda m: {}),
    Rule(
        re.compile(r"(состояние|статус) (системы|компьютера|пк)|загрузк[аи] (цп|процессора)"),
        "system_status",
        lambda m: {},
    ),
    Rule(re.compile(r"(сделай |сними )?скриншот|снимок экрана"), "take_screenshot", lambda m: {}),
    Rule(
        re.compile(r"(прочитай|считай|распознай) (весь )?текст|что (здесь |там )?написано"),
        "read_screen_text",
        lambda m: {},
    ),
    Rule(
        re.compile(r"(проанализируй|посмотри на|что на) (это |моё )?(экране?|окно|окне)"),
        "analyze_screen",
        lambda m: {},
    ),
    Rule(
        re.compile(r"запомни[,:]? (?:что )?(?P<text>.+)"),
        "remember_fact",
        lambda m: {"text": m.group("text").strip()},
    ),
    Rule(
        re.compile(r"(?:вспомни|продиктуй|что ты помнишь про)[,:]? (?P<query>.+)"),
        "recall_fact",
        lambda m: {"query": m.group("query").strip()},
    ),
    Rule(
        re.compile(r"(?:включи|поставь) (?:в )?(?:спотифай|spotify)[ ,:]+(?P<query>.+)"),
        "spotify_play",
        lambda m: {"query": m.group("query").strip()},
    ),
    Rule(re.compile(r"заблокируй (компьютер|пк|экран)"), "lock_workstation", lambda m: {}),
    Rule(
        re.compile(r"(поставь|установи) громкость (на )?(?P<level>\d+)"),
        "set_volume",
        lambda m: {"level": int(m.group("level"))},
    ),
    Rule(
        re.compile(r"(сделай )?(громче|погромче)"),
        "change_volume",
        lambda m: {"delta": 10},
    ),
    Rule(
        re.compile(r"(сделай )?(тише|потише)"),
        "change_volume",
        lambda m: {"delta": -10},
    ),
    Rule(
        re.compile(r"(открой|запусти) (сайт|ссылку) (?P<url>\S+)"),
        "open_url",
        lambda m: {"url": m.group("url")},
    ),
    Rule(
        re.compile(r"(открой|запусти) (?P<app>.+)"),
        "open_app",
        lambda m: {"name": m.group("app").strip()},
    ),
    Rule(
        re.compile(r"закрой (?P<app>.+)"),
        "close_app",
        lambda m: {"name": m.group("app").strip()},
    ),
    Rule(
        re.compile(r"(найди|поищи|загугли) (?P<query>.+)"),
        "web_search",
        lambda m: {"query": m.group("query").strip()},
    ),
    Rule(
        re.compile(r"погода(?: в (?P<city>[\w\- ]+))?"),
        "weather",
        lambda m: {"city": (m.group("city") or "Moscow").strip()},
    ),
    Rule(
        re.compile(
            r"(?:поставь )?таймер (?:на )?(?P<amount>\d+(?:[.,]\d+)?) ?"
            r"(?P<unit>секунд\w*|минут\w*|час\w*)(?P<label>.*)"
        ),
        "set_timer",
        _timer_args,
    ),
    Rule(re.compile(r"(покажи )?таймеры"), "list_timers", lambda m: {}),
    Rule(
        re.compile(r"запиши(?: заметку)?[:,]? (?P<text>.+)"),
        "add_note",
        lambda m: {"text": m.group("text").strip()},
    ),
    Rule(re.compile(r"(прочитай|покажи) заметки"), "read_notes", lambda m: {}),
    Rule(
        re.compile(r"(следующ\w+ трек|переключи трек)"),
        "media_control",
        lambda m: {"action": "next"},
    ),
    Rule(
        re.compile(r"(включи|поставь|останови|пауза) (музыку|воспроизведение|трек)"),
        "media_control",
        lambda m: {"action": "play"},
    ),
    Rule(
        re.compile(r"(что такое|кто такой|кто такая|расскажи про) (?P<query>.+)"),
        "fetch_summary",
        lambda m: {"query": m.group("query").strip()},
    ),
)


def match_rule(text: str) -> tuple[str, dict[str, Any]] | None:
    """Находит подходящее правило для фразы."""
    normalized = text.lower().replace("ё", "е").strip(" .!?")
    for rule in RULES:
        match = rule.pattern.search(normalized)
        if match:
            return rule.skill, rule.build_args(match)
    return None


class OfflineBrain(Brain):
    """Работает без сети: сопоставляет фразы с навыками по регулярным выражениям."""

    def __init__(self, config: BrainConfig, skills: SkillRegistry) -> None:
        super().__init__(config, skills)

    def _chat(self, messages: list[Message]) -> Message:
        """Заглушка: офлайн-режим не обращается к модели."""
        raise NotImplementedError

    def ask(self, user_text: str) -> str:
        """Выполняет навык по правилу либо честно сообщает о непонимании."""
        matched = match_rule(user_text)
        if matched is None:
            return (
                "Без языковой модели я понимаю только прямые команды, сэр. "
                "Например: «открой блокнот» или «какая погода в Москве»."
            )
        skill, arguments = matched
        return self.skills.call(skill, arguments)
