"""NSE equity list and Nifty index membership.

The live source is NSE's public EQUITY_L.csv (and Nifty Indices constituent
files). A full copy of each file ships in backend/data/fallbacks so search
still works if the download is blocked.
"""

from __future__ import annotations

import csv
import io
import logging
from datetime import datetime, timezone

from backend.app.cache import read_json, write_json
from backend.app.config import CACHE_DIR, FALLBACK_DIR
from backend.app.http_client import request

log = logging.getLogger(__name__)

EQUITY_URL = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
NIFTY_URLS = {
    "NIFTY 100": "https://www.niftyindices.com/IndexConstituent/ind_nifty100list.csv",
    "NIFTY 200": "https://www.niftyindices.com/IndexConstituent/ind_nifty200list.csv",
}
FALLBACK_FILES = {
    "EQUITY": FALLBACK_DIR / "EQUITY_L.csv",
    "NIFTY 100": FALLBACK_DIR / "ind_nifty100list.csv",
    "NIFTY 200": FALLBACK_DIR / "ind_nifty200list.csv",
}
EQUITY_SERIES = {"EQ", "BE", "BZ"}
LIST_TTL = 24 * 3600


def _clean_row(row: dict) -> dict:
    return {(key or "").strip(): (value or "").strip() for key, value in row.items()}


def parse_equity_csv(text: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    symbols = []
    seen = set()
    for raw in reader:
        row = _clean_row(raw)
        symbol = row.get("SYMBOL", "").upper()
        series = row.get("SERIES", "").upper()
        name = row.get("NAME OF COMPANY", "")
        if not symbol or not name or series not in EQUITY_SERIES or symbol in seen:
            continue
        seen.add(symbol)
        symbols.append(
            {
                "symbol": symbol,
                "name": name,
                "series": series,
                "isin": row.get("ISIN NUMBER", ""),
                "listing_date": row.get("DATE OF LISTING", ""),
            }
        )
    symbols.sort(key=lambda item: item["symbol"])
    return symbols


def parse_index_csv(text: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    rows = []
    seen = set()
    for raw in reader:
        row = _clean_row(raw)
        symbol = row.get("Symbol", row.get("SYMBOL", "")).upper()
        name = row.get("Company Name", row.get("NAME OF COMPANY", ""))
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        rows.append({"symbol": symbol, "name": name, "industry": row.get("Industry", "")})
    return rows


def _read_fallback(path) -> str:
    return path.read_text(encoding="utf-8-sig")


async def _download_text(url: str) -> str:
    response = await request("GET", url)
    response.raise_for_status()
    return response.text


async def load_equities(*, force: bool = False) -> dict:
    cache_path = CACHE_DIR / "equities.json"
    if not force:
        cached = read_json(cache_path, LIST_TTL)
        if cached and cached.get("symbols"):
            return cached
    source = "NSE EQUITY_L.csv"
    try:
        text = await _download_text(EQUITY_URL)
        symbols = parse_equity_csv(text)
        if len(symbols) < 500:
            raise RuntimeError(f"equity list looks short ({len(symbols)})")
    except Exception as exc:
        log.warning("NSE equity list download failed (%s); using the shipped fallback", exc)
        symbols = parse_equity_csv(_read_fallback(FALLBACK_FILES["EQUITY"]))
        source = "NSE EQUITY_L.csv (shipped fallback)"
    payload = {
        "source": source,
        "count": len(symbols),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "symbols": symbols,
    }
    write_json(cache_path, payload)
    return payload


async def load_index(name: str, *, force: bool = False) -> list[dict]:
    cache_path = CACHE_DIR / f"index_{name.replace(' ', '_').lower()}.json"
    if not force:
        cached = read_json(cache_path, LIST_TTL)
        if cached and cached.get("symbols"):
            return cached["symbols"]
    try:
        text = await _download_text(NIFTY_URLS[name])
        symbols = parse_index_csv(text)
        if len(symbols) < 50:
            raise RuntimeError(f"{name} list looks short ({len(symbols)})")
    except Exception as exc:
        log.warning("%s download failed (%s); using the shipped fallback", name, exc)
        symbols = parse_index_csv(_read_fallback(FALLBACK_FILES[name]))
    write_json(cache_path, {"symbols": symbols})
    return symbols


def search_symbols(symbols: list[dict], query: str, limit: int = 8) -> list[dict]:
    needle = query.strip().lower()
    if not needle:
        return []
    scored = []
    for item in symbols:
        symbol = item["symbol"].lower()
        name = item["name"].lower()
        if symbol == needle:
            score = 100
        elif symbol.startswith(needle):
            score = 80
        elif name.startswith(needle):
            score = 60
        elif needle in symbol:
            score = 40
        elif needle in name:
            score = 20
        else:
            continue
        scored.append((score, item["symbol"], item))
    scored.sort(key=lambda row: (-row[0], row[1]))
    return [row[2] for row in scored[:limit]]


def find_symbol(symbols: list[dict], symbol: str) -> dict | None:
    target = symbol.upper()
    for item in symbols:
        if item["symbol"] == target:
            return item
    return None
