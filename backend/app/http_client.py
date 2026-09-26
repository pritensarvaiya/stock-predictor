"""Shared HTTP client with a gentle outbound pace for free data sources."""

from __future__ import annotations

import asyncio
import time
from typing import Any
from urllib.parse import quote

import httpx

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

YAHOO_HOSTS = (
    "https://query1.finance.yahoo.com",
    "https://query2.finance.yahoo.com",
)


class DataError(RuntimeError):
    pass


class Pace:
    """Space out call starts without holding the lock while sleeping."""

    def __init__(self, min_interval: float) -> None:
        self.min_interval = min_interval
        self._lock = asyncio.Lock()
        self._next = 0.0

    async def wait(self) -> None:
        async with self._lock:
            now = time.monotonic()
            scheduled = max(now, self._next)
            self._next = scheduled + self.min_interval
            delay = scheduled - now
        if delay > 0:
            await asyncio.sleep(delay)


yahoo_pace = Pace(0.08)
news_pace = Pace(0.15)
_client: httpx.AsyncClient | None = None
_yahoo_sem = asyncio.Semaphore(5)
_news_sem = asyncio.Semaphore(3)


def client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
            timeout=httpx.Timeout(25.0, connect=10.0),
            follow_redirects=True,
        )
    return _client


async def close_client() -> None:
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None


async def request(method: str, url: str, *, pace: Pace | None = None, sem: asyncio.Semaphore | None = None, **kwargs: Any) -> httpx.Response:
    async def _go() -> httpx.Response:
        if pace:
            await pace.wait()
        last_exc: Exception | None = None
        for attempt in range(4):
            try:
                response = await client().request(method, url, **kwargs)
            except httpx.HTTPError as exc:
                last_exc = exc
                await asyncio.sleep(0.4 * (attempt + 1))
                continue
            if response.status_code in {429, 500, 502, 503, 504}:
                await asyncio.sleep(0.6 * (attempt + 1))
                last_exc = DataError(f"{url} returned {response.status_code}")
                continue
            return response
        raise DataError(str(last_exc) if last_exc else f"failed to fetch {url}")

    if sem is None:
        return await _go()
    async with sem:
        return await _go()


async def yahoo_chart(yahoo_symbol: str, interval: str, range_: str) -> dict:
    params = {"interval": interval, "range": range_, "includePrePost": "false", "events": "div,splits"}
    encoded = quote(yahoo_symbol, safe="")
    last_error: Exception | None = None
    for host in YAHOO_HOSTS:
        url = f"{host}/v8/finance/chart/{encoded}"
        try:
            response = await request("GET", url, params=params, pace=yahoo_pace, sem=_yahoo_sem)
        except DataError as exc:
            last_error = exc
            continue
        if response.status_code != 200:
            last_error = DataError(f"Yahoo chart {response.status_code} for {yahoo_symbol}")
            continue
        payload = response.json()
        chart = payload.get("chart") or {}
        result = chart.get("result") or []
        if chart.get("error") or not result:
            description = ""
            if chart.get("error"):
                description = chart["error"].get("description") or ""
            last_error = DataError(description or f"No Yahoo data for {yahoo_symbol}")
            continue
        return payload
    raise DataError(str(last_error) if last_error else f"No Yahoo data for {yahoo_symbol}")
