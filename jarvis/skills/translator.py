"""Переводчик: перевод текста через Google Translate (бесплатно) или локально."""

from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request

from .registry import Skill, object_schema

log = logging.getLogger(__name__)

_GOOGLE_TRANSLATE_URL = "https://translate.googleapis.com/translate_a/single"
_LANG_CODES = {
    "русский": "ru", "английский": "en", "немецкий": "de", "французский": "fr",
    "испанский": "es", "итальянский": "it", "португальский": "pt", "китайский": "zh",
    "японский": "ja", "корейский": "ko", "арабский": "ar", "турецкий": "tr",
    "украинский": "uk", "белорусский": "be", "казахский": "kk", "польский": "pl",
    "чешский": "cs", "голландский": "nl", "шведский": "sv", "финский": "fi",
}


def _detect_language(text: str) -> str:
    """Определяет язык текста (простая эвристика для кириллицы/латиницы)."""
    cyrillic = sum(1 for c in text if '\u0400' <= c <= '\u04ff')
    latin = sum(1 for c in text if c.isalpha() and ('a' <= c.lower() <= 'z'))
    if cyrillic > latin:
        return "ru"
    return "en"


def _translate_google(text: str, from_lang: str, to_lang: str) -> str:
    """Перевод через неофициальный Google Translate API."""
    params = {
        "client": "gtx",
        "sl": from_lang,
        "tl": to_lang,
        "dt": "t",
        "q": text,
    }
    qs = urllib.parse.urlencode(params)
    url = f"{_GOOGLE_TRANSLATE_URL}?{qs}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        log.warning("Google Translate ошибка: %s", exc)
        return f"Ошибка перевода: {exc}, сэр."
    # Ответ: [[[["translated", ...], ...], ...], ...]
    translated_parts = []
    try:
        for block in data[0]:
            if isinstance(block, list) and len(block) > 0 and isinstance(block[0], list):
                for part in block:
                    if isinstance(part, list) and len(part) > 0:
                        translated_parts.append(str(part[0]))
            elif isinstance(block, list) and len(block) > 0 and isinstance(block[0], str):
                translated_parts.append(block[0])
    except (IndexError, TypeError):
        pass
    result = "".join(translated_parts).strip()
    if not result:
        return "Не удалось перевести, сэр."
    return result


def _resolve_lang(name: str) -> str:
    """Преобразует название языка в код. Если не распознал — возвращает как есть."""
    name_lower = name.lower().strip()
    if name_lower in _LANG_CODES:
        return _LANG_CODES[name_lower]
    # Может уже код
    if len(name_lower) == 2:
        return name_lower
    return name_lower


def translate_text(text: str, to_lang: str = "", from_lang: str = "") -> str:
    """Переводит текст. Язык-источник определяется автоматически если не указан."""
    if not text.strip():
        return "Укажите текст для перевода, сэр."
    src = _resolve_lang(from_lang) if from_lang else "auto"
    dst = _resolve_lang(to_lang) if to_lang else "en" if _detect_language(text) == "ru" else "ru"
    result = _translate_google(text, src, dst)
    if result.startswith("Ошибка"):
        return result
    lang_name = to_lang or ("английский" if dst == "en" else "русский")
    return f"Перевод на {lang_name}: {result}"


def detect_language(text: str) -> str:
    """Определяет язык текста."""
    if not text.strip():
        return "Пустой текст, сэр."
    code = _detect_language(text)
    # Обратный маппинг
    code_to_name = {v: k for k, v in _LANG_CODES.items()}
    name = code_to_name.get(code, code)
    return f"Определён язык: {name} ({code})."


def build_skills() -> list[Skill]:
    """Создаёт навыки переводчика."""
    return [
        Skill(
            name="translate_text",
            description=(
                "Перевести текст на другой язык. Язык определяется автоматически. "
                "Можно явно указать целевой язык (русский, английский, немецкий и т.д.)."
            ),
            parameters=object_schema(
                {
                    "text": {"type": "string", "description": "Текст для перевода"},
                    "to_lang": {"type": "string", "description": "Целевой язык (название или код, пустое = автоматически)"},
                    "from_lang": {"type": "string", "description": "Язык исходного текста (пустое = автоматически)"},
                },
                required=["text"],
            ),
            handler=translate_text,
        ),
        Skill(
            name="detect_language",
            description="Определить язык текста.",
            parameters=object_schema(
                {
                    "text": {"type": "string", "description": "Текст для анализа"},
                },
                required=["text"],
            ),
            handler=detect_language,
        ),
    ]
