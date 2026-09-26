"""Background scan of Nifty 200, ranked by the chance of a +2% next-session high."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime

import pandas as pd

from backend.app.cache import read_json, write_json
from backend.app.config import CACHE_DIR, DISCLAIMER, PRIMARY_DEFINITION
from backend.app.data.market_data import get_daily_history, to_yahoo
from backend.app.data.news import get_news
from backend.app.data.symbols import load_index
from backend.app.features.indicators import latest_feature_row
from backend.app.market_calendar import IST, market_status
from backend.app.model.predict import (
    load_model,
    market_sentence,
    model_path,
    news_adjust,
    reliability_block,
    score_row,
    signal_for,
    tail_note,
    volatility_note,
)
from backend.app.sentiment.analyze import analyze_news

log = logging.getLogger(__name__)


def _history_age(phase: str) -> float:
    return 20 * 60 if phase == "open" else 18 * 3600


class WatchlistService:
    def __init__(self) -> None:
        self.snapshot: dict | None = None
        self.progress = {"stage": "idle", "done": 0, "total": 0}
        self.error: str | None = None
        self._task: asyncio.Task | None = None
        disk = read_json(CACHE_DIR / "watchlist.json")
        if disk and disk.get("rows"):
            self.snapshot = disk

    def _running(self) -> bool:
        return self._task is not None and not self._task.done()

    def _fresh(self, status: dict) -> bool:
        if not self.snapshot or self.snapshot.get("horizon_date") != status["next_session_date"]:
            return False
        built = self.snapshot.get("built_at_epoch") or 0
        ttl = 20 * 60 if status["is_open"] else 4 * 3600
        return (time.time() - built) < ttl

    def kick(self, force: bool = False) -> None:
        status = market_status()
        if self._running():
            return
        if not force and self._fresh(status):
            return
        self._task = asyncio.create_task(self._run())

    def payload(self) -> dict:
        status = market_status()
        refreshing = self._running() and self.snapshot is not None
        if self.snapshot is None:
            return {
                "status": "error" if self.error and not self._running() else "building",
                "refreshing": self._running(),
                "progress": self.progress,
                "error": self.error,
                "rows": [],
                "definition": PRIMARY_DEFINITION,
                "disclaimer": DISCLAIMER,
                "horizon_date": status["next_session_date"],
                "horizon_label": status["next_session_label"],
                "market": status,
                "universe": "NIFTY 200",
            }
        return {
            **self.snapshot,
            "status": "ready",
            "refreshing": refreshing or not self._fresh(status),
            "progress": self.progress,
            "error": self.error,
            "market": status,
        }

    async def _run(self) -> None:
        try:
            self.error = None
            if not model_path().exists():
                raise FileNotFoundError(
                    "Model artifacts are missing. From the repo root run: python -m backend.app.model.train"
                )
            load_model()
            members = await load_index("NIFTY 200")
            status = market_status()
            max_age = _history_age(status["phase"])
            self.progress = {"stage": "prices", "done": 0, "total": len(members)}
            nifty = await get_daily_history("^NSEI", max_age=max_age)
            frames: dict[str, pd.DataFrame] = {}
            done = 0

            async def _one(item: dict) -> None:
                nonlocal done
                try:
                    frames[item["symbol"]] = await get_daily_history(
                        to_yahoo(item["symbol"], "NSE"), max_age=max_age
                    )
                except Exception as exc:
                    log.info("watchlist skip %s: %s", item["symbol"], exc)
                finally:
                    done += 1
                    self.progress = {"stage": "prices", "done": done, "total": len(members)}

            for index in range(0, len(members), 12):
                await asyncio.gather(*[_one(item) for item in members[index : index + 12]])

            self.progress = {"stage": "scoring", "done": 0, "total": len(frames)}
            rows = await asyncio.to_thread(_score_frames, frames, nifty, members)
            rows.sort(key=lambda row: row["model_probability"], reverse=True)
            top = rows[:40]
            self.progress = {"stage": "news", "done": 0, "total": len(top)}
            for index, row in enumerate(top):
                try:
                    items = await get_news(row["symbol"], row["name"])
                    sentiment = await analyze_news(
                        row["symbol"],
                        row["name"],
                        items,
                        allow_gemini=index < 12,
                    )
                    _apply_news(row, sentiment)
                except Exception as exc:
                    log.info("news skip %s: %s", row["symbol"], exc)
                self.progress = {"stage": "news", "done": index + 1, "total": len(top)}
            rows.sort(key=lambda row: row["probability"], reverse=True)
            for rank, row in enumerate(rows, start=1):
                row["rank"] = rank
            now = datetime.now(IST)
            snapshot = {
                "status": "ready",
                "universe": "NIFTY 200",
                "scanned": len(rows),
                "news_scanned": sum(1 for row in rows if row["news_scanned"]),
                "horizon_date": status["next_session_date"],
                "horizon_label": status["next_session_label"],
                "definition": PRIMARY_DEFINITION,
                "built_at": now.isoformat(),
                "built_at_epoch": time.time(),
                "built_label": now.strftime("%A %d %B, %H:%M IST"),
                "rows": rows,
                "reliability": reliability_block("next_session_high"),
                "disclaimer": DISCLAIMER,
                "market": status,
            }
            self.snapshot = snapshot
            write_json(CACHE_DIR / "watchlist.json", snapshot)
            self.progress = {"stage": "done", "done": len(rows), "total": len(rows)}
            log.info("watchlist ready: %s names", len(rows))
        except Exception as exc:
            log.exception("watchlist build failed")
            self.error = str(exc)
            self.progress = {**self.progress, "stage": "error"}


def _score_frames(frames: dict, nifty: pd.DataFrame, members: list[dict]) -> list[dict]:
    names = {item["symbol"]: item.get("name") or item["symbol"] for item in members}
    industries = {item["symbol"]: item.get("industry") or "" for item in members}
    rows = []
    for symbol, frame in frames.items():
        try:
            feature_row = latest_feature_row(frame, nifty)
            if feature_row is None:
                continue
            scored = score_row(feature_row)
        except Exception:
            continue
        price = float(feature_row["raw_close"])
        prev = feature_row["raw_prev"]
        change_pct = None
        if pd.notna(prev) and float(prev):
            change_pct = price / float(prev) - 1
        drivers = scored["drivers"]
        reasons = [driver["sentence"] for driver in drivers[:2]]
        model_p = scored["p_next"]
        model_5d = scored["p_5d"]
        rows.append(
            {
                "symbol": symbol,
                "name": names.get(symbol, symbol),
                "industry": industries.get(symbol, ""),
                "price": price,
                "change_pct": change_pct,
                "model_probability": model_p,
                "probability": model_p,
                "news_nudge": 0.0,
                "signal": signal_for(model_p, "next_session_high"),
                "model_signal": signal_for(model_p, "next_session_high"),
                "five_day_model_probability": model_5d,
                "five_day_probability": model_5d,
                "five_day_signal": signal_for(model_5d, "five_day_close"),
                "reasons": reasons,
                "market_context": market_sentence(feature_row),
                "volatility_note": volatility_note(drivers),
                "news_summary": None,
                "news_label": None,
                "news_score": None,
                "news_method": None,
                "news_impact": None,
                "news_scanned": False,
            }
        )
    return rows


def _apply_news(row: dict, sentiment: dict) -> None:
    adjusted, nudge = news_adjust(row["model_probability"], sentiment)
    adjusted_5d, _nudge_5d = news_adjust(row["five_day_model_probability"], sentiment)
    row["probability"] = adjusted
    row["news_nudge"] = nudge
    row["signal"] = signal_for(adjusted, "next_session_high")
    row["five_day_probability"] = adjusted_5d
    row["five_day_signal"] = signal_for(adjusted_5d, "five_day_close")
    row["news_summary"] = sentiment.get("summary")
    row["news_label"] = sentiment.get("label")
    row["news_score"] = sentiment.get("score")
    row["news_method"] = sentiment.get("method")
    row["news_impact"] = sentiment.get("price_impact")
    row["news_scanned"] = True
    extra = []
    if sentiment.get("summary"):
        extra.append(sentiment["summary"])
    hot = tail_note(row["probability"], "next_session_high")
    if hot:
        extra.append(hot)
    if extra:
        row["reasons"] = (row["reasons"] + extra)[:3]
