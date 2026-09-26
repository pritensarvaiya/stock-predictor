"""Public news and NSE corporate announcements for one symbol."""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

from backend.app.cache import read_json, write_json
from backend.app.config import CACHE_DIR
from backend.app.http_client import USER_AGENT, client, news_pace, request

log = logging.getLogger(__name__)

NEWS_TTL = 45 * 60
_nse_ready = False


def short_name(name: str) -> str:
    cleaned = name.strip()
    for suffix in (" Limited", " Ltd.", " Ltd", " LIMITED", " LTD"):
        if cleaned.endswith(suffix):
            cleaned = cleaned[: -len(suffix)]
    return cleaned.strip() or name


def _parse_nse_time(value: str) -> str | None:
    for fmt in ("%d-%b-%Y %H:%M:%S", "%d-%b-%Y"):
        try:
            return datetime.strptime(value.strip(), fmt).replace(tzinfo=IST).isoformat()
        except ValueError:
            continue
    return None


def _parse_rfc822(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value).isoformat()
    except (TypeError, ValueError):
        return None


async def _ensure_nse_cookies() -> None:
    global _nse_ready
    if _nse_ready:
        return
    await request(
        "GET",
        "https://www.nseindia.com/",
        headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
    )
    _nse_ready = True


async def fetch_google_news(symbol: str, name: str) -> list[dict]:
    query = f'"{short_name(name)}" OR {symbol} when:14d'
    url = "https://news.google.com/rss/search?" + urlencode(
        {"q": query, "hl": "en-IN", "gl": "IN", "ceid": "IN:en"}
    )
    await news_pace.wait()
    response = await client().get(url, headers={"User-Agent": USER_AGENT})
    if response.status_code != 200 or not response.text.strip():
        log.warning("Google News RSS failed for %s (%s)", symbol, response.status_code)
        return []
    try:
        root = ET.fromstring(response.text)
    except ET.ParseError:
        log.warning("Google News RSS was not XML for %s", symbol)
        return []
    items = []
    for node in root.findall("./channel/item")[:16]:
        title = (node.findtext("title") or "").strip()
        link = (node.findtext("link") or "").strip()
        if not title or not link:
            continue
        source = "Google News"
        headline = title
        if " - " in title:
            headline, source = title.rsplit(" - ", 1)
        items.append(
            {
                "title": headline.strip(),
                "url": link,
                "source": source.strip() or "Google News",
                "published": _parse_rfc822(node.findtext("pubDate")),
                "kind": "news",
            }
        )
    return items


async def fetch_announcements(symbol: str) -> list[dict]:
    try:
        await _ensure_nse_cookies()
        response = await request(
            "GET",
            "https://www.nseindia.com/api/corporate-announcements",
            params={"index": "equities", "symbol": symbol},
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/json",
                "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-announcements",
            },
        )
        if response.status_code != 200:
            return []
        payload = response.json()
    except Exception as exc:
        log.warning("NSE announcements unavailable for %s (%s)", symbol, exc)
        return []
    if not isinstance(payload, list):
        return []
    cutoff = datetime.now(IST) - timedelta(days=21)
    items = []
    for row in payload[:12]:
        published = _parse_nse_time(str(row.get("an_dt") or ""))
        if published:
            try:
                stamp = datetime.fromisoformat(published)
                if stamp.tzinfo is None:
                    stamp = stamp.replace(tzinfo=timezone.utc)
                if stamp < cutoff:
                    continue
            except ValueError:
                pass
        desc = (row.get("desc") or "").strip()
        text = (row.get("attchmntText") or "").strip()
        title = text if len(text) > len(desc) + 10 else (desc or text)
        if not title:
            continue
        items.append(
            {
                "title": title[:280],
                "url": row.get("attchmntFile") or "https://www.nseindia.com/companies-listing/corporate-filings-announcements",
                "source": "NSE announcement",
                "published": published,
                "kind": "announcement",
                "category": desc,
            }
        )
    return items


async def get_news(symbol: str, name: str) -> list[dict]:
    cache_path = CACHE_DIR / "news" / f"{symbol.upper()}.json"
    cached = read_json(cache_path, NEWS_TTL)
    if cached and isinstance(cached.get("items"), list):
        return cached["items"]
    news = await fetch_google_news(symbol, name)
    filings = await fetch_announcements(symbol)
    # News first, then filings, dropping duplicate titles.
    seen = set()
    items = []
    for item in news + filings:
        key = item["title"].lower()
        if key in seen:
            continue
        seen.add(key)
        items.append(item)
    write_json(cache_path, {"items": items})
    return items
