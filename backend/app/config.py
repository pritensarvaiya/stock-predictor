"""Paths, environment, and shared copy."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

CACHE_DIR = Path(os.getenv("CACHE_DIR", ROOT / "backend" / "data" / "cache"))
FALLBACK_DIR = ROOT / "backend" / "data" / "fallbacks"
ARTIFACT_DIR = Path(__file__).resolve().parent / "model" / "artifacts"

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite").strip() or "gemini-3.1-flash-lite"

IST_NAME = "Asia/Kolkata"

DISCLAIMER = (
    "These figures are probabilities from a historical model and public headlines. "
    "They are uncertain, they can be wrong, and they are not financial advice or a recommendation to buy or sell."
)

DELAY_NOTE = (
    "Prices come from Yahoo Finance and are often about 15 minutes behind the NSE, sometimes longer. "
    "This is not a live exchange feed."
)

CLOSED_PRICE_NOTE = (
    "The cash market is closed. This is the last traded price from the most recent session, via Yahoo Finance."
)

PRIMARY_DEFINITION = (
    "A hit means the next cash session's high prints at least 2% above the reference price. "
    "It does not mean the stock closes up 2%."
)

SECONDARY_DEFINITION = (
    "A hit means at least one of the next five session closes is 2% or more above the reference price."
)

EXCHANGES = {
    "NSE": {"yahoo_suffix": ".NS", "currency": "INR"},
    "BSE": {"yahoo_suffix": ".BO", "currency": "INR"},
    # US tickers can be added later by passing exchange=US and a symbol universe.
    "US": {"yahoo_suffix": "", "currency": "USD"},
}
