"""Score one feature row and describe what moved it."""

from __future__ import annotations

import json

import joblib
import numpy as np
import pandas as pd

from backend.app.config import ARTIFACT_DIR, DISCLAIMER
from backend.app.features.indicators import FEATURE_COLUMNS, FEATURE_META, format_feature
from backend.app.model.train import predict_proba

_CACHE: dict | None = None
MAX_NEWS_NUDGE = 0.05


class ModelNotReady(FileNotFoundError):
    pass


def model_path():
    return ARTIFACT_DIR / "model.joblib"


def load_model() -> dict:
    global _CACHE
    if _CACHE is None:
        path = model_path()
        if not path.exists():
            raise ModelNotReady(
                "Model artifacts are missing. From the repo root run: python -m backend.app.model.train"
            )
        _CACHE = joblib.load(path)
    return _CACHE


def metrics() -> dict:
    path = ARTIFACT_DIR / "metrics.json"
    if path.exists():
        return json.loads(path.read_text())
    return load_model()["metrics"]


def signal_for(probability: float, target_key: str) -> str:
    target = metrics()["targets"][target_key]
    if target.get("edge") and probability >= target["likely_threshold"]:
        return "Likely"
    if probability <= target["unlikely_threshold"]:
        return "Unlikely"
    return "Uncertain"


def news_adjust(probability: float, sentiment: dict | None) -> tuple[float, float]:
    if not sentiment or (sentiment.get("headline_count") or 0) < 2:
        return probability, 0.0
    score = float(sentiment.get("score") or 0.0)
    nudge = max(-MAX_NEWS_NUDGE, min(MAX_NEWS_NUDGE, score * MAX_NEWS_NUDGE))
    adjusted = min(0.95, max(0.02, probability + nudge))
    return adjusted, adjusted - probability


def _drivers(model: dict, frame: pd.DataFrame) -> list[dict]:
    pipe = model["pipe"]
    scaler = pipe.named_steps["scaler"]
    clf = pipe.named_steps["clf"]
    values = frame[FEATURE_COLUMNS].to_numpy(dtype=float)
    scale = np.where(scaler.scale_ == 0, 1.0, scaler.scale_)
    contrib = ((values - scaler.mean_) / scale)[0] * clf.coef_[0]
    order = np.argsort(-np.abs(contrib))
    drivers = []
    for index in order[:4]:
        key = FEATURE_COLUMNS[index]
        value = float(frame.iloc[0][key])
        direction = "up" if contrib[index] >= 0 else "down"
        verb = "raises" if direction == "up" else "lowers"
        label = FEATURE_META[key][0]
        shown = format_feature(key, value)
        drivers.append(
            {
                "key": key,
                "label": label,
                "value": value,
                "display": shown,
                "direction": direction,
                "strength": float(abs(contrib[index])),
                "sentence": f"{label} is {shown}. That {verb} the chance of a +2% high.",
            }
        )
    return drivers


def score_row(row: pd.Series) -> dict:
    bundle = load_model()
    frame = pd.DataFrame([{key: float(row[key]) for key in FEATURE_COLUMNS}])
    p_next = float(predict_proba(bundle["models"]["next_session_high"], frame)[0])
    p_5d = float(predict_proba(bundle["models"]["five_day_close"], frame)[0])
    return {
        "p_next": p_next,
        "p_5d": p_5d,
        "drivers": _drivers(bundle["models"]["next_session_high"], frame),
    }


def comparison_sentence(probability: float, base_rate: float) -> str:
    delta = probability - base_rate
    base = f"{base_rate:.0%}"
    if delta >= 0.12:
        return f"That is well above the {base} base rate for Nifty 200 names in the test."
    if delta >= 0.05:
        return f"That is modestly above the {base} base rate."
    if delta > -0.05:
        return f"That sits close to the {base} base rate, so it is not a strong separation from a typical day."
    return f"That is below the {base} base rate."


def tail_note(probability: float, target_key: str) -> str | None:
    """High scores run hotter than the test. Say so next to the headline number."""
    if probability < 0.70:
        return None
    grid = metrics()["targets"][target_key].get("threshold_grid") or []
    row = next((item for item in grid if item.get("threshold") == 0.70 and item.get("precision")), None)
    if not row:
        return None
    return (
        f"This score is in the thin tail. Test calls at or above 70% were followed by the move "
        f"{row['precision']:.0%} of the time ({int(row['n']):,} cases), not at the headline percentage. "
        "Use it to rank, not as a promise."
    )


def reliability_block(target_key: str) -> dict:
    target = metrics()["targets"][target_key]
    meta = metrics()
    if not target.get("edge"):
        sentence = (
            "On the walk-forward test, no probability cutoff beat the base rate by at least 4 points "
            "with enough cases behind it. Likely is withheld. Treat the ranking as weak."
        )
    else:
        sentence = (
            f"When this model said Likely (at or above {target['likely_threshold']:.0%}), "
            f"the +2% outcome happened {target['precision_at_likely']:.0%} of the time, "
            f"against a {target['base_rate']:.0%} base rate, on {int(target['n_likely']):,} test calls. "
            "That hit rate is historical. It is not a guarantee for the next session."
        )
    return {
        "hit_rate": target.get("precision_at_likely"),
        "base_rate": target.get("base_rate"),
        "n_likely": target.get("n_likely"),
        "n_test": target.get("pooled", {}).get("n"),
        "auc": target.get("pooled", {}).get("auc"),
        "brier": target.get("pooled", {}).get("brier"),
        "likely_threshold": target.get("likely_threshold"),
        "unlikely_threshold": target.get("unlikely_threshold"),
        "edge": target.get("edge"),
        "period": f"{meta.get('date_start')} to {meta.get('date_end')}",
        "test_window": _test_window(target),
        "sentence": sentence,
        "news_in_backtest": False,
    }


def _test_window(target: dict) -> str:
    folds = target.get("folds") or []
    if not folds:
        return ""
    return f"{folds[0]['test_start']} to {folds[-1]['test_end']}"


def market_sentence(row: pd.Series) -> str:
    r5 = float(row["nifty_ret_5"])
    r20 = float(row["nifty_ret_20"])
    dist = float(row["nifty_dist_sma50"])
    side = "above" if dist >= 0 else "below"
    return (
        f"Nifty 50 is {r20 * 100:+.1f}% over 20 sessions and {r5 * 100:+.1f}% over 5, "
        f"and it sits {abs(dist) * 100:.1f}% {side} its 50-day average."
    )


def volatility_note(drivers: list[dict]) -> str | None:
    if not drivers:
        return None
    top = drivers[0]
    if top["direction"] == "up" and top["key"] in {"atr_pct", "range_pct"}:
        return (
            "Volatility is doing a lot of the work. The primary target is an intraday high, "
            "so a wider typical range reaches +2% more often even when the close does not."
        )
    return None


def build_view(row: pd.Series, scored: dict, sentiment: dict, status: dict, reference_price: float) -> dict:
    """Assemble the prediction panel from a scored row, news, and the session clock."""
    sentiment = sentiment or {}
    p_next, nudge = news_adjust(scored["p_next"], sentiment)
    p_5d, nudge_5d = news_adjust(scored["p_5d"], sentiment)
    primary_metrics = metrics()["targets"]["next_session_high"]
    secondary_metrics = metrics()["targets"]["five_day_close"]
    drivers = scored["drivers"]
    note = volatility_note(drivers)
    paragraphs = [
        (
            f"Reference price is {reference_price:,.2f}. "
            f"The model, before news, puts the chance of a +2% high in the {status['next_session_label']} session "
            f"at {scored['p_next']:.0%}. {comparison_sentence(scored['p_next'], primary_metrics['base_rate'])}"
        ),
        " ".join(driver["sentence"] for driver in drivers[:3]),
        market_sentence(row),
    ]
    if sentiment.get("summary"):
        if abs(nudge) >= 0.005:
            direction = "up" if nudge > 0 else "down"
            paragraphs.append(
                f"{sentiment['summary']} Headlines nudge the displayed chance {direction} "
                f"by {abs(nudge):.0%} points, to {p_next:.0%}. The backtest does not include this nudge."
            )
        else:
            paragraphs.append(
                f"{sentiment['summary']} News is not strong enough to move the displayed chance. "
                "The backtest does not include headlines."
            )
    paragraphs.append(reliability_block("next_session_high")["sentence"])
    if status.get("reference_mode") == "live":
        paragraphs.append(
            "The cash session is still open, so this uses the latest trade as if it were a close. "
            "The measured hit rate used finished daily closes, so an in-session reading sits a step outside that test."
        )
    if note:
        paragraphs.append(note)
    hot = tail_note(p_next, "next_session_high")
    if hot:
        paragraphs.append(hot)
    paragraphs.append(DISCLAIMER)

    def pack(target_key: str, target_metrics: dict, model_p: float, adjusted: float, used_nudge: float) -> dict:
        return {
            "id": target_key,
            "name": target_metrics["name"],
            "definition": target_metrics["definition"],
            "model_probability": model_p,
            "probability": adjusted,
            "news_nudge": used_nudge,
            "signal": signal_for(adjusted, target_key),
            "model_signal": signal_for(model_p, target_key),
            "base_rate": target_metrics["base_rate"],
            "comparison": comparison_sentence(model_p, target_metrics["base_rate"]),
        }

    return {
        "reference_price": reference_price,
        "reference_mode": status["reference_mode"],
        "horizon_date": status["next_session_date"],
        "horizon_label": status["next_session_label"],
        "primary": pack("next_session_high", primary_metrics, scored["p_next"], p_next, nudge),
        "secondary": pack("five_day_close", secondary_metrics, scored["p_5d"], p_5d, nudge_5d),
        "drivers": drivers,
        "market_context": market_sentence(row),
        "volatility_note": note,
        "tail_note": hot,
        "explanation": [part for part in paragraphs if part],
        "reliability": reliability_block("next_session_high"),
        "secondary_reliability": reliability_block("five_day_close"),
        "disclaimer": DISCLAIMER,
    }
