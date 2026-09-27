"""Yahoo Finance chart client.

Indian names use the .NS (NSE) or .BO (BSE) suffix. The same function accepts
a bare US ticker when exchange is US, so that market can be added later
without a second price stack.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from backend.app.cache import is_fresh
from backend.app.config import CACHE_DIR, DELAY_NOTE, EXCHANGES
from backend.app.http_client import DataError, yahoo_chart

log = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")

RANGE_MAP = {
    "1D": ("5m", "1d", True),
    "1W": ("15m", "5d", True),
    "1M": ("1d", "1mo", False),
    "6M": ("1d", "6mo", False),
    "1Y": ("1d", "1y", False),
    "5Y": ("1wk", "5y", False),
}

_mem: dict[tuple, tuple[float, dict]] = {}


def to_yahoo(symbol: str, exchange: str) -> str:
    exchange = exchange.upper()
    if symbol.startswith("^"):
        return symbol
    if exchange not in EXCHANGES:
        raise DataError(f"Unknown exchange {exchange}")
    suffix = EXCHANGES[exchange]["yahoo_suffix"]
    return f"{symbol}{suffix}"


def currency_for(exchange: str) -> str:
    return EXCHANGES[exchange.upper()]["currency"]


def _history_path(yahoo_symbol: str):
    safe = yahoo_symbol.replace("^", "").replace("/", "_")
    return CACHE_DIR / "daily" / f"{safe}.pkl"


def parse_chart(payload: dict) -> tuple[dict, list[dict]]:
    result = payload["chart"]["result"][0]
    meta = result.get("meta") or {}
    timestamps = result.get("timestamp") or []
    quote = (result.get("indicators") or {}).get("quote") or [{}]
    quote = quote[0]
    adj_block = (result.get("indicators") or {}).get("adjclose") or [{}]
    adj = adj_block[0].get("adjclose") if adj_block else None
    bars = []
    for i, ts in enumerate(timestamps):
        try:
            open_, high, low, close = quote["open"][i], quote["high"][i], quote["low"][i], quote["close"][i]
        except (KeyError, IndexError, TypeError):
            continue
        if None in (open_, high, low, close):
            continue
        volume = 0.0
        if quote.get("volume") and i < len(quote["volume"]) and quote["volume"][i] is not None:
            volume = float(quote["volume"][i])
        adjclose = float(close)
        if adj and i < len(adj) and adj[i] is not None:
            adjclose = float(adj[i])
        bars.append(
            {
                "ts": int(ts),
                "open": float(open_),
                "high": float(high),
                "low": float(low),
                "close": float(close),
                "volume": volume,
                "adjclose": adjclose,
            }
        )
    return meta, bars


def bars_to_frame(bars: list[dict]) -> pd.DataFrame:
    if not bars:
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume", "adjclose"])
    frame = pd.DataFrame(bars)
    dates = (
        pd.to_datetime(frame["ts"], unit="s", utc=True)
        .dt.tz_convert(IST)
        .dt.tz_localize(None)
        .dt.normalize()
    )
    frame.insert(0, "date", dates)
    frame = frame.drop_duplicates("date", keep="last").sort_values("date").reset_index(drop=True)
    return frame


def quote_from_meta(meta: dict, bars: list[dict]) -> dict:
    price = meta.get("regularMarketPrice")
    # chartPreviousClose is the bar before the requested window, not the prior session.
    # Daily bars make the prior session explicit.
    if len(bars) >= 2:
        previous = bars[-2]["close"]
    else:
        previous = meta.get("previousClose") or meta.get("chartPreviousClose")
    if price is None and bars:
        price = bars[-1]["close"]
    price_f = float(price) if price is not None else None
    prev_f = float(previous) if previous is not None else None
    change = None
    change_pct = None
    if price_f is not None and prev_f:
        change = price_f - prev_f
        change_pct = change / prev_f
    as_of = None
    if meta.get("regularMarketTime"):
        as_of = datetime.fromtimestamp(int(meta["regularMarketTime"]), tz=IST).isoformat()
    elif bars:
        as_of = datetime.fromtimestamp(bars[-1]["ts"], tz=IST).isoformat()
    day_high = meta.get("regularMarketDayHigh")
    day_low = meta.get("regularMarketDayLow")
    if day_high is None and bars:
        day_high = max(bar["high"] for bar in bars)
    if day_low is None and bars:
        day_low = min(bar["low"] for bar in bars)
    volume = meta.get("regularMarketVolume")
    return {
        "price": price_f,
        "previous_close": prev_f,
        "change": change,
        "change_pct": change_pct,
        "day_high": float(day_high) if day_high is not None else None,
        "day_low": float(day_low) if day_low is not None else None,
        "volume": float(volume) if volume is not None else (bars[-1]["volume"] if bars else None),
        "as_of": as_of,
        "currency": meta.get("currency") or "INR",
        "exchange_name": meta.get("fullExchangeName") or meta.get("exchangeName"),
        "long_name": meta.get("longName") or meta.get("shortName"),
        "fifty_two_week_high": meta.get("fiftyTwoWeekHigh"),
        "fifty_two_week_low": meta.get("fiftyTwoWeekLow"),
        "source": "Yahoo Finance",
        "delay_note": DELAY_NOTE,
    }


async def get_chart(yahoo_symbol: str, interval: str, range_: str, *, ttl: float) -> tuple[dict, list[dict]]:
    key = (yahoo_symbol, interval, range_)
    hit = _mem.get(key)
    now = time.time()
    if hit and now - hit[0] < ttl:
        return hit[1]["meta"], hit[1]["bars"]
    payload = await yahoo_chart(yahoo_symbol, interval, range_)
    meta, bars = parse_chart(payload)
    # ttl 0 is a one-shot download (the 5-year history). Keeping those bars
    # would pin every scanned symbol in RAM for the life of the process.
    if ttl > 0:
        _mem[key] = (now, {"meta": meta, "bars": bars})
    return meta, bars


async def get_quote(yahoo_symbol: str, *, ttl: float) -> dict:
    meta, bars = await get_chart(yahoo_symbol, "1d", "5d", ttl=ttl)
    return quote_from_meta(meta, bars)


async def get_daily_history(yahoo_symbol: str, *, max_age: float) -> pd.DataFrame:
    path = _history_path(yahoo_symbol)
    if is_fresh(path, max_age):
        frame = pd.read_pickle(path)
        frame["date"] = pd.to_datetime(frame["date"]).dt.normalize()
        return frame
    _meta, bars = await get_chart(yahoo_symbol, "1d", "5y", ttl=0)
    frame = bars_to_frame(bars)
    if frame.empty:
        raise DataError(f"No daily history for {yahoo_symbol}")
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_pickle(path)
    # The 5y response was stored with ttl 0 in memory; drop it so a later
    # short-range quote is not confused with this key. Key differs by range.
    return frame


def apply_live_price(frame: pd.DataFrame, live_price: float | None, phase: str) -> pd.DataFrame:
    """During the session, fold the latest trade into the current daily bar."""
    if phase != "open" or not live_price or frame.empty:
        return frame
    out = frame.copy()
    idx = out.index[-1]
    old = float(out.at[idx, "close"])
    if not old:
        return out
    scale = float(live_price) / old
    out.at[idx, "close"] = float(live_price)
    out.at[idx, "adjclose"] = float(out.at[idx, "adjclose"]) * scale
    out.at[idx, "high"] = max(float(out.at[idx, "high"]), float(live_price))
    out.at[idx, "low"] = min(float(out.at[idx, "low"]), float(live_price))
    return out


def chart_payload(range_key: str, bars: list[dict]) -> dict:
    _interval, _range, intraday = RANGE_MAP[range_key]
    points = []
    for bar in bars:
        if intraday:
            stamp = bar["ts"]
        else:
            stamp = datetime.fromtimestamp(bar["ts"], tz=IST).date().isoformat()
        points.append(
            {
                "time": stamp,
                "open": bar["open"],
                "high": bar["high"],
                "low": bar["low"],
                "close": bar["close"],
            }
        )
    return {"intraday": intraday, "bars": points}
