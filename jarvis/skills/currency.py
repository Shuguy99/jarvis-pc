"""Конвертер валют: реальные курсы через API."""

from __future__ import annotations

import json
import logging
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from ..config import CurrencyConfig
from .registry import Skill, object_schema

log = logging.getLogger(__name__)

_API_URL = "https://api.exchangerate-api.com/v4/latest/{base}"
_CACHE_PATH = Path.home() / ".jarvis" / "rates_cache.json"
_CACHE_TTL = 3600  # 1 час


def _load_cache() -> dict:
    """Загружает кэш курсов."""
    if _CACHE_PATH.is_file():
        try:
            data = json.loads(_CACHE_PATH.read_text("utf-8"))
            if datetime.now(timezone.utc).timestamp() - data.get("ts", 0) < _CACHE_TTL:
                return data.get("rates", {})
        except Exception:
            pass
    return {}


def _save_cache(rates: dict) -> None:
    """Сохраняет кэш курсов."""
    try:
        _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        data = {"ts": datetime.now(timezone.utc).timestamp(), "rates": rates}
        _CACHE_PATH.write_text(json.dumps(data, ensure_ascii=False), "utf-8")
    except Exception as exc:
        log.warning("Не удалось сохранить кэш курсов: %s", exc)


def _fetch_rates(base: str = "USD") -> dict[str, float] | None:
    """Получает курсы валют через API с кэшированием."""
    base = base.upper()
    if base != "USD":
        # API по умолчанию отдаёт от USD, но поддерживает любую базу
        url = _API_URL.format(base=base)
    else:
        # Проверяем кэш
        cached = _load_cache()
        if cached:
            log.debug("Курсы из кэша (%d записей)", len(cached))
            return cached
        url = _API_URL.format(base="USD")

    req = urllib.request.Request(url, headers={"User-Agent": "JarvisAssistant/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        rates = data.get("rates", {})
        if base == "USD":
            _save_cache(rates)
        return rates
    except Exception as exc:
        log.warning("Не удалось получить курсы: %s", exc)
        return None


# Популярные коды с русскими названиями
_CURRENCY_NAMES: dict[str, str] = {
    "RUB": "рублей", "USD": "долларов", "EUR": "евро",
    "GBP": "фунтов", "CNY": "юаней", "JPY": "иен", "KZT": "тенге",
    "UAH": "гривен", "BYN": "белорусских рублей", "TRY": "лир",
    "BTC": "биткоинов", "GEL": "лари", "UZS": "сумов",
    "KRW": "вон", "INR": "рупий", "BRL": "реалов", "PLN": "злотых",
    "CZK": "крон", "CHF": "франков", "CAD": "канадских долларов",
    "AUD": "австралийских долларов",
}


def _resolve_code(name: str) -> str:
    """Превращает название валюты в код. 'рубль' -> 'RUB', 'доллар' -> 'USD'."""
    name = name.strip().upper()
    if len(name) == 3:
        return name
    for code, rus_name in _CURRENCY_NAMES.items():
        if name in rus_name.upper() or name in code:
            return code
    # Обратный поиск
    for code, rus_name in _CURRENCY_NAMES.items():
        if rus_name.upper().startswith(name[:4]):
            return code
    return name


def convert(config: CurrencyConfig, amount: float, from_currency: str, to_currency: str) -> str:
    """Конвертирует сумму из одной валюты в другую."""
    from_code = _resolve_code(from_currency)
    to_code = _resolve_code(to_currency)
    rates = _fetch_rates(from_code)
    if rates is None:
        return "Не удалось получить курсы валют. Проверьте интернет, сэр."
    rate = rates.get(to_code)
    if rate is None:
        available = ", ".join(sorted(rates.keys())[:15]) + " ..."
        return f"Валюта {to_code} не найдена. Доступные: {available}, сэр."
    result = amount * rate
    from_name = _CURRENCY_NAMES.get(from_code, from_code)
    to_name = _CURRENCY_NAMES.get(to_code, to_code)
    if result >= 1:
        formatted = f"{result:,.2f}"
    else:
        formatted = f"{result:,.6f}"
    return f"{amount:,.2f} {from_name} = {formatted} {to_name}. Курс: 1 {from_code} = {rate:.4f} {to_code}, сэр."


def list_currencies() -> str:
    """Показывает поддерживаемые валюты."""
    lines = ["Поддерживаемые валюты:"]
    for code, name in sorted(_CURRENCY_NAMES.items()):
        lines.append(f"  {code} — {name}")
    return "\n".join(lines)


def exchange_rate(config: CurrencyConfig, from_currency: str, to_currency: str) -> str:
    """Показывает текущий курс между двумя валютами."""
    return convert(config, 1.0, from_currency, to_currency)


def build_skills(config: CurrencyConfig) -> list[Skill]:
    """Создаёт навыки конвертера валют."""
    return [
        Skill(
            name="convert_currency",
            description="Конвертировать сумму из одной валюты в другую по реальному курсу.",
            parameters=object_schema(
                {
                    "amount": {"type": "number", "description": "Сумма"},
                    "from_currency": {"type": "string", "description": "Из какой валюты (RUB, USD, EUR, ...)"},
                    "to_currency": {"type": "string", "description": "В какую валюту"},
                },
                required=["amount", "from_currency", "to_currency"],
            ),
            handler=lambda amount, from_currency, to_currency: convert(config, amount, from_currency, to_currency),
        ),
        Skill(
            name="exchange_rate",
            description="Показать текущий курс обмена между двумя валютами.",
            parameters=object_schema(
                {
                    "from_currency": {"type": "string", "description": "Из какой валюты"},
                    "to_currency": {"type": "string", "description": "В какую валюту"},
                },
                required=["from_currency", "to_currency"],
            ),
            handler=lambda from_currency, to_currency: exchange_rate(config, from_currency, to_currency),
        ),
        Skill(
            name="list_currencies",
            description="Показать список поддерживаемых валют.",
            parameters=object_schema({}),
            handler=list_currencies,
        ),
    ]
