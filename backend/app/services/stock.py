"""Quote, chart, news, and prediction for one symbol."""

from __future__ import annotations

import re

import pandas as pd

from backend.app.config import CLOSED_PRICE_NOTE, DELAY_NOTE, DISCLAIMER
from backend.app.data.market_data import (
    RANGE_MAP,
    apply_live_price,
    chart_payload,
    currency_for,
    get_chart,
    get_daily_history,
    get_quote,
    to_yahoo,
)
from backend.app.data.news import get_news
from backend.app.data.symbols import find_symbol, load_equities
from backend.app.features.indicators import (
    SESSIONS_REQUIRED,
    latest_feature_row,
    session_count,
    short_history_message,
)
from backend.app.http_client import DataError
from backend.app.market_calendar import market_status
from backend.app.model.predict import build_view, score_row
from backend.app.sentiment.analyze import analyze_news

SYMBOL_RE = re.compile(r"^[A-Z0-9][A-Z0-9&\-]{0,20}$")


def clean_symbol(symbol: str) -> str:
    cleaned = symbol.upper().strip()
    if not SYMBOL_RE.match(cleaned):
        raise DataError("Symbol looks invalid")
    return cleaned


def clean_exchange(exchange: str) -> str:
    value = (exchange or "NSE").upper()
    if value not in {"NSE", "BSE", "US"}:
        raise DataError("Exchange must be NSE, BSE, or US")
    return value


async def identity(symbol: str) -> dict:
    equities = await load_equities()
    known = find_symbol(equities["symbols"], symbol)
    if known:
        return known
    return {"symbol": symbol, "name": symbol, "series": None, "isin": None}


def _history_age(phase: str) -> float:
    return 20 * 60 if phase == "open" else 18 * 3600


def _quote_ttl(phase: str) -> float:
    return 30 if phase == "open" else 15 * 60


async def quote(symbol: str, exchange: str) -> dict:
    symbol = clean_symbol(symbol)
    exchange = clean_exchange(exchange)
    status = market_status()
    info = await identity(symbol)
    yahoo = to_yahoo(symbol, exchange)
    payload = await get_quote(yahoo, ttl=_quote_ttl(status["phase"]))
    payload.update(
        {
            "symbol": symbol,
            "name": payload.get("long_name") or info["name"],
            "series": info.get("series"),
            "isin": info.get("isin"),
            "exchange": exchange,
            "currency": payload.get("currency") or currency_for(exchange),
            "market": status,
            "delay_note": DELAY_NOTE if status["is_open"] else f"{CLOSED_PRICE_NOTE} {DELAY_NOTE}",
            "disclaimer": DISCLAIMER,
        }
    )
    return payload


async def chart(symbol: str, exchange: str, range_key: str) -> dict:
    symbol = clean_symbol(symbol)
    exchange = clean_exchange(exchange)
    range_key = range_key.upper()
    if range_key not in RANGE_MAP:
        raise DataError("Range must be one of 1D, 1W, 1M, 6M, 1Y, 5Y")
    status = market_status()
    interval, yahoo_range, intraday = RANGE_MAP[range_key]
    ttl = 40 if status["is_open"] and range_key == "1D" else (5 * 60 if status["is_open"] else 6 * 3600)
    _meta, bars = await get_chart(to_yahoo(symbol, exchange), interval, yahoo_range, ttl=ttl)
    body = chart_payload(range_key, bars)
    body.update(
        {
            "symbol": symbol,
            "exchange": exchange,
            "range": range_key,
            "interval": interval,
            "intraday": intraday,
            "currency": currency_for(exchange),
            "delay_note": DELAY_NOTE,
        }
    )
    return body


async def news(symbol: str, exchange: str, *, allow_gemini: bool = True) -> dict:
    symbol = clean_symbol(symbol)
    exchange = clean_exchange(exchange)
    info = await identity(symbol)
    items = await get_news(symbol, info["name"])
    sentiment = await analyze_news(symbol, info["name"], items, allow_gemini=allow_gemini)
    return {"symbol": symbol, "exchange": exchange, "items": items, "sentiment": sentiment}


def unavailable_prediction(
    symbol: str,
    name: str,
    exchange: str,
    live: dict | None,
    status: dict,
    sessions: int,
    *,
    reason: str | None = None,
    message: str | None = None,
) -> dict:
    """A score the model cannot produce yet. Callers still return price and news."""
    if reason is None:
        reason = "short_history" if sessions < SESSIONS_REQUIRED else "incomplete_history"
    return {
        "available": False,
        "reason": reason,
        "sessions": sessions,
        "sessions_required": SESSIONS_REQUIRED,
        "message": message or short_history_message(sessions),
        "symbol": symbol,
        "name": name,
        "exchange": exchange,
        "as_of": None if not live else live.get("as_of"),
        "horizon_date": status.get("next_session_date"),
        "horizon_label": status.get("next_session_label"),
        "disclaimer": DISCLAIMER,
    }


async def prediction(symbol: str, exchange: str, *, allow_gemini: bool = True) -> dict:
    symbol = clean_symbol(symbol)
    exchange = clean_exchange(exchange)
    status = market_status()
    info = await identity(symbol)
    live = await get_quote(to_yahoo(symbol, exchange), ttl=_quote_ttl(status["phase"]))
    if live.get("price") is None:
        raise DataError(f"No price for {symbol} on {exchange}")
    yahoo = to_yahoo(symbol, exchange)
    try:
        history = await get_daily_history(yahoo, max_age=_history_age(status["phase"]))
    except DataError:
        history = pd.DataFrame()
    sessions = session_count(history)
    if history.empty or sessions < SESSIONS_REQUIRED:
        return unavailable_prediction(symbol, info["name"], exchange, live, status, sessions)
    nifty = await get_daily_history("^NSEI", max_age=_history_age(status["phase"]))
    history = apply_live_price(history, live["price"], status["phase"])
    row = latest_feature_row(history, nifty)
    if row is None:
        return unavailable_prediction(symbol, info["name"], exchange, live, status, sessions)
    research = await news(symbol, exchange, allow_gemini=allow_gemini)
    scored = score_row(row)
    view = build_view(row, scored, research["sentiment"], status, float(live["price"]))
    view.update(
        {
            "symbol": symbol,
            "name": info["name"],
            "exchange": exchange,
            "as_of": live.get("as_of"),
            "news": research["sentiment"],
        }
    )
    return view


async def stock_page(symbol: str, exchange: str) -> dict:
    symbol = clean_symbol(symbol)
    exchange = clean_exchange(exchange)
    quote_payload = await quote(symbol, exchange)
    try:
        pred = await prediction(symbol, exchange, allow_gemini=True)
    except DataError as exc:
        status = quote_payload.get("market") or market_status()
        pred = unavailable_prediction(
            symbol,
            quote_payload.get("name") or symbol,
            exchange,
            quote_payload,
            status,
            sessions=0,
            reason="error",
            message=str(exc),
        )
    try:
        research = await news(symbol, exchange, allow_gemini=True)
    except DataError as exc:
        research = {
            "symbol": symbol,
            "exchange": exchange,
            "items": [],
            "sentiment": None,
            "error": str(exc),
        }
    return {"quote": quote_payload, "prediction": pred, "news": research}
