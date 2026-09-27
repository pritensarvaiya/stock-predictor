"""Headline sentiment.

With GEMINI_API_KEY set, Google Gemini reads the headlines and returns a short
summary plus a price-impact rating. Otherwise a local scorer combines VADER
with a small finance phrase list. No API key is embedded.
"""

from __future__ import annotations

import json
import logging
import math
import re
from functools import lru_cache

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from backend.app.cache import read_json, write_json
from backend.app.config import CACHE_DIR, GEMINI_API_KEY, GEMINI_MODEL
from backend.app.http_client import client
from backend.app.sentiment.budget import gemini_budget

log = logging.getLogger(__name__)

SENTIMENT_TTL = 45 * 60

# Longer phrases are preferred over pieces of themselves. Weights are about
# the headline's tone, not a price forecast.
POSITIVE_PHRASES = [
    ("record profit", 1.0),
    ("profit jumps", 1.0),
    ("profit surges", 1.0),
    ("profit rises", 0.9),
    ("profit grows", 0.8),
    ("net profit up", 0.8),
    ("beats estimates", 1.0),
    ("beats expectations", 1.0),
    ("above estimates", 0.8),
    ("raises guidance", 1.0),
    ("guidance raised", 0.9),
    ("order win", 0.9),
    ("bags order", 0.9),
    ("wins order", 0.8),
    ("buyback", 0.7),
    ("special dividend", 0.6),
    ("dividend", 0.35),
    ("upgraded", 0.9),
    ("upgrade", 0.7),
    ("outperform", 0.6),
    ("all-time high", 0.5),
    ("stake buy", 0.45),
    ("capacity expansion", 0.4),
    ("partnership", 0.25),
]
NEGATIVE_PHRASES = [
    ("net loss", 1.0),
    ("posts loss", 0.9),
    ("quarterly loss", 0.9),
    ("profit falls", 1.0),
    ("profit slumps", 1.0),
    ("profit drops", 1.0),
    ("profit declines", 0.9),
    ("misses estimates", 1.0),
    ("misses expectations", 1.0),
    ("below estimates", 0.8),
    ("cuts guidance", 1.0),
    ("guidance cut", 0.9),
    ("downgraded", 1.0),
    ("downgrade", 0.85),
    ("underperform", 0.7),
    ("sell rating", 0.8),
    ("fraud", 1.0),
    ("scam", 1.0),
    ("accounting irregular", 1.0),
    ("default", 0.9),
    ("insolvency", 1.0),
    ("investigation", 0.75),
    ("probe", 0.65),
    ("penalty", 0.6),
    ("pledged shares", 0.7),
    ("resigns", 0.45),
    ("raid", 0.7),
]


@lru_cache(maxsize=1)
def _vader() -> SentimentIntensityAnalyzer:
    return SentimentIntensityAnalyzer()


def _phrase_score(text: str) -> float:
    lowered = text.lower()
    matches: list[tuple[int, int, float]] = []
    for phrase, weight in POSITIVE_PHRASES:
        start = lowered.find(phrase)
        if start >= 0:
            matches.append((start, start + len(phrase), weight))
    for phrase, weight in NEGATIVE_PHRASES:
        start = lowered.find(phrase)
        if start >= 0:
            matches.append((start, start + len(phrase), -weight))
    matches.sort(key=lambda item: (item[0], -(item[1] - item[0])))
    kept: list[tuple[int, int, float]] = []
    for start, end, weight in matches:
        if any(start >= prev_start and end <= prev_end for prev_start, prev_end, _weight in kept):
            continue
        kept.append((start, end, weight))
    if not kept:
        return 0.0
    total = sum(weight for _s, _e, weight in kept)
    return math.tanh(total)


def score_headline(text: str) -> float:
    lexicon = _phrase_score(text)
    compound = _vader().polarity_scores(text)["compound"]
    if abs(lexicon) >= 0.35:
        blended = 0.7 * lexicon + 0.3 * compound
    else:
        blended = 0.4 * lexicon + 0.6 * compound
    return max(-1.0, min(1.0, blended))


def _label(score: float) -> str:
    if score >= 0.15:
        return "positive"
    if score <= -0.15:
        return "negative"
    return "neutral"


def _impact(score: float) -> str:
    if score >= 0.25:
        return "supportive"
    if score <= -0.25:
        return "adverse"
    if abs(score) < 0.08:
        return "unclear"
    return "mixed"


def lexicon_sentiment(items: list[dict], name: str) -> dict:
    headlines = [item for item in items if item.get("kind") == "news"] or items
    if not headlines:
        return {
            "score": 0.0,
            "label": "neutral",
            "method": "lexicon",
            "model": None,
            "price_impact": "unclear",
            "summary": f"No recent headlines were found for {name}, so news is not moving the estimate.",
            "reasons": [],
            "headline_count": 0,
        }
    scores = [score_headline(item["title"]) for item in headlines]
    # Announcements are usually routine. If we only have filings, keep them but say so.
    score = sum(scores) / len(scores)
    positives = sum(1 for value in scores if value >= 0.15)
    negatives = sum(1 for value in scores if value <= -0.15)
    only_filings = all(item.get("kind") == "announcement" for item in headlines)
    source_bit = "NSE announcements" if only_filings else "headlines"
    summary = (
        f"{positives} of {len(scores)} recent {source_bit} lean positive and {negatives} lean negative "
        f"(score {score:+.2f} on a −1 to +1 scale). "
        "This is a local word-list reading — VADER plus a short finance phrase list — not a language model."
    )
    reasons = []
    if positives and not negatives:
        reasons.append("The recent language is mostly upbeat.")
    elif negatives and not positives:
        reasons.append("The recent language is mostly downbeat.")
    elif positives and negatives:
        reasons.append("Headlines point in both directions, so the news signal is mixed.")
    return {
        "score": round(score, 3),
        "label": _label(score),
        "method": "lexicon",
        "model": None,
        "price_impact": _impact(score),
        "summary": summary,
        "reasons": reasons,
        "headline_count": len(scores),
    }


def _strip_json(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    return json.loads(cleaned)


async def gemini_sentiment(items: list[dict], name: str) -> dict | None:
    if not GEMINI_API_KEY or not items:
        return None
    lines = []
    for item in items[:18]:
        when = item.get("published") or "undated"
        kind = item.get("kind") or "news"
        lines.append(f"- [{kind}] {when}: {item['title']} ({item.get('source')})")
    prompt = (
        "You score recent news for an Indian equity. Reply with JSON only, no markdown.\n"
        "Schema: {"
        '"score": number from -1 (clearly negative for the share price) to 1 (clearly positive), '
        '"sentiment": "positive"|"neutral"|"negative", '
        '"price_impact": "supportive"|"mixed"|"adverse"|"unclear", '
        '"summary": string of two plain sentences, '
        '"reasons": array of up to three short strings}\n'
        "Ignore routine filings unless they contain a real surprise. Do not invent numbers. "
        "Do not give a buy or sell instruction.\n"
        f"Company: {name}\n"
        + "\n".join(lines)
    )
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    try:
        response = await client().post(
            url,
            params={"key": GEMINI_API_KEY},
            json={
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"},
            },
            timeout=30.0,
        )
    except Exception as exc:
        log.warning("Gemini request failed: %s", exc)
        return None
    if response.status_code != 200:
        log.warning("Gemini returned %s: %s", response.status_code, response.text[:300])
        return None
    try:
        body = response.json()
        text = body["candidates"][0]["content"]["parts"][0]["text"]
        parsed = _strip_json(text)
        score = max(-1.0, min(1.0, float(parsed["score"])))
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
        log.warning("Gemini response was not usable JSON: %s", exc)
        return None
    reasons = parsed.get("reasons") or []
    if not isinstance(reasons, list):
        reasons = []
    return {
        "score": round(score, 3),
        "label": parsed.get("sentiment") if parsed.get("sentiment") in {"positive", "neutral", "negative"} else _label(score),
        "method": "gemini",
        "model": GEMINI_MODEL,
        "price_impact": parsed.get("price_impact") if parsed.get("price_impact") in {"supportive", "mixed", "adverse", "unclear"} else _impact(score),
        "summary": str(parsed.get("summary") or "").strip() or "Gemini returned no summary.",
        "reasons": [str(item) for item in reasons[:3]],
        "headline_count": len(items),
    }


async def analyze_news(symbol: str, name: str, items: list[dict], *, allow_gemini: bool = True) -> dict:
    method = "gemini" if allow_gemini and GEMINI_API_KEY else "lexicon"
    cache_path = CACHE_DIR / "sentiment" / f"{symbol.upper()}_{method}.json"
    cached = read_json(cache_path, SENTIMENT_TTL)
    if cached and "score" in cached:
        return cached
    result = None
    limited = False
    if method == "gemini":
        if gemini_budget.allow():
            result = await gemini_sentiment(items, name)
        else:
            limited = True
            log.info("Gemini budget reached; using the local word list for %s", symbol)
    if result is None:
        result = lexicon_sentiment(items, name)
        if limited:
            result = {
                **result,
                "summary": result["summary"]
                + " Gemini is paused so the key is not used too quickly. This reading is the local word list.",
            }
        elif method == "gemini":
            result = {
                **result,
                "summary": result["summary"] + " Gemini was configured but the request failed, so this fallback was used.",
            }
    write_json(cache_path, result)
    return result
