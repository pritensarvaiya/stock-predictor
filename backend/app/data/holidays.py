"""Refresh the cash-market holiday map from NSE. Failures keep the embedded year."""

from __future__ import annotations

import logging
from datetime import datetime

from backend.app.http_client import USER_AGENT, request
from backend.app.market_calendar import set_holidays

log = logging.getLogger(__name__)


async def refresh_holiday_calendar() -> None:
    try:
        await request(
            "GET",
            "https://www.nseindia.com/",
            headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
        )
        response = await request(
            "GET",
            "https://www.nseindia.com/api/holiday-master",
            params={"type": "trading"},
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/json",
                "Referer": "https://www.nseindia.com/",
            },
        )
        if response.status_code != 200:
            raise RuntimeError(f"holiday master {response.status_code}")
        payload = response.json()
        rows = payload.get("CM") or []
        parsed = {}
        for row in rows:
            day = datetime.strptime(row["tradingDate"], "%d-%b-%Y").date()
            name = str(row.get("description") or "Holiday").replace("*", "").strip()
            parsed[day] = name
        if len(parsed) < 8:
            raise RuntimeError("holiday payload was too short")
        set_holidays(parsed)
        log.info("loaded %s NSE cash holidays", len(parsed))
    except Exception as exc:
        log.warning("using the embedded 2026 NSE holiday list (%s)", exc)
