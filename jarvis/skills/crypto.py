"""Криптовалюта и акции через CoinGecko."""

from __future__ import annotations

import json
import logging
import urllib.request

from .registry import Skill, object_schema

log = logging.getLogger(__name__)
_API = "https://api.coingecko.com/api/v3"


def _fetch(path: str) -> dict:
    url = f"{_API}{path}"
    req = urllib.request.Request(url, headers={"User-Agent": "Jarvis/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def crypto_price(coin: str = "bitcoin") -> str:
    try:
        data = _fetch(f"/simple/price?ids={coin}&vs_currencies=usd,rub&include_24hr_change=true")
        if coin not in data:
            return f"Монета {coin} не найдена, сэр."
        info = data[coin]
        usd = info.get("usd", "?")
        rub = info.get("rub", "?")
        change = info.get("usd_24h_change")
        change_str = f" ({change:+.2f}% за 24ч)" if change is not None else ""
        return f"{coin.title()}: ${usd} / {rub}руб{change_str}, сэр."
    except Exception as exc:
        return f"Ошибка: {exc}, сэр."


def crypto_list(top: int = 10) -> str:
    try:
        data = _fetch(f"/coins/markets?vs_currency=usd&order=market_cap_desc&per_page={min(top, 50)}&page=1")
        lines = ["Топ криптовалют:"]
        for c in data:
            lines.append(f"  {c['name']} ({c['symbol']}): ${c['current_price']:.2f}")
        return chr(10).join(lines) + chr(10) + "Сэр."
    except Exception as exc:
        return f"Ошибка: {exc}, сэр."


def stock_price(symbol: str = "AAPL") -> str:
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol.upper()}?range=1d&interval=1d"
        req = urllib.request.Request(url, headers={"User-Agent": "Jarvis/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        meta = data["chart"]["result"][0]["meta"]
        price = meta.get("regularMarketPrice", "?")
        prev = meta.get("previousClose", "?")
        name = meta.get("symbol", symbol)
        return f"{name}: ${price} (вчера: ${prev}), сэр."
    except Exception:
        return f"Не удалось получить данные по {symbol}, сэр."


def build_skills() -> list[Skill]:
    return [
        Skill(name="crypto_price", description="Цена криптовалюты в USD и RUB.",
              parameters=object_schema({"coin": {"type": "string", "description": "ID монеты"}}),
              handler=lambda coin="bitcoin": crypto_price(coin)),
        Skill(name="crypto_list", description="Топ криптовалют по капитализации.",
              parameters=object_schema({"top": {"type": "integer", "description": "Количество"}}),
              handler=lambda top=10: crypto_list(top)),
        Skill(name="stock_price", description="Цена акции по тикеру.",
              parameters=object_schema({"symbol": {"type": "string", "description": "Тикер"}}, required=["symbol"]),
              handler=lambda symbol: stock_price(symbol)),
    ]
