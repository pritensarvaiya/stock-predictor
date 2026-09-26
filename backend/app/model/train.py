"""Walk-forward training for the two +2% targets.

Run from the repo root:

    python -m backend.app.model.train

The measured hit rate comes only from dates the model had not been trained on.
The saved model is then refit on the full sample with the same recipe, for live use.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
from datetime import datetime, timezone

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from backend.app.config import ARTIFACT_DIR, PRIMARY_DEFINITION, SECONDARY_DEFINITION
from backend.app.data.market_data import get_daily_history, to_yahoo
from backend.app.data.symbols import load_index
from backend.app.features.indicators import (
    FEATURE_COLUMNS,
    FEATURE_META,
    clip_features,
    compute_nifty_features,
    compute_symbol_features,
)
from backend.app.http_client import close_client

log = logging.getLogger(__name__)

FOLDS = (
    ("2024-07-01", "2025-01-01"),
    ("2025-01-01", "2025-07-01"),
    ("2025-07-01", "2026-01-01"),
    ("2026-01-01", "2027-01-01"),
)

TARGETS = {
    "next_session_high": {
        "column": "y_next",
        "name": "Next session high +2%",
        "definition": PRIMARY_DEFINITION,
    },
    "five_day_close": {
        "column": "y_5d",
        "name": "Close +2% within 5 sessions",
        "definition": SECONDARY_DEFINITION,
    },
}


def _pipe() -> Pipeline:
    return Pipeline(
        [
            ("scaler", StandardScaler()),
            ("clf", LogisticRegression(C=0.5, solver="lbfgs", max_iter=800)),
        ]
    )


def fit_estimator(frame: pd.DataFrame, ycol: str) -> dict:
    """Fit on earlier dates and Platt-calibrate on the last 20% of train dates."""
    data = frame.dropna(subset=FEATURE_COLUMNS + [ycol]).sort_values(["date", "symbol"])
    if "symbol" not in data.columns:
        data = data.copy()
        data["symbol"] = ""
    dates = list(pd.to_datetime(pd.Series(data["date"].unique())).sort_values())
    if len(data) < 500 or data[ycol].nunique() < 2:
        raise RuntimeError(f"not enough rows to fit {ycol}")
    cut = dates[int(len(dates) * 0.80)]
    base_df = data[data["date"] < cut]
    cal_df = data[data["date"] >= cut]
    pipe = _pipe()
    if base_df[ycol].nunique() < 2 or len(cal_df) < 200 or cal_df[ycol].nunique() < 2:
        pipe.fit(data[FEATURE_COLUMNS], data[ycol].astype(int))
        return {"pipe": pipe, "platt": None}
    pipe.fit(base_df[FEATURE_COLUMNS], base_df[ycol].astype(int))
    # Platt scaling is a logistic regression on the log-odds, not on the
    # already-squashed probability. Scaling the probability itself bows the
    # top end upward and prints 90%+ scores the test never earned.
    logits = pipe.decision_function(cal_df[FEATURE_COLUMNS]).reshape(-1, 1)
    platt = LogisticRegression(C=1e6, solver="lbfgs", max_iter=400)
    platt.fit(logits, cal_df[ycol].astype(int))
    return {"pipe": pipe, "platt": platt}


def predict_proba(model: dict, frame: pd.DataFrame) -> np.ndarray:
    logits = model["pipe"].decision_function(frame[FEATURE_COLUMNS]).reshape(-1, 1)
    if model.get("platt") is None:
        return 1.0 / (1.0 + np.exp(-logits.ravel()))
    return model["platt"].predict_proba(logits)[:, 1]


def select_thresholds(y: np.ndarray, probabilities: np.ndarray) -> dict:
    """Pick the Likely cutoff.

    "Likely" has to mean the outcome happened more often than not. The most
    inclusive cutoff with at least 400 test calls, precision of at least 52%,
    and a 4 point lift over the base rate wins. A high-volume cutoff that only
    reaches the mid-40s is a better-than-usual day, not a Likely one, so it
    stays in Uncertain.
    """
    y = np.asarray(y, dtype=float)
    probabilities = np.asarray(probabilities, dtype=float)
    base = float(np.mean(y))
    grid = []
    qualified = []
    for threshold in (0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75):
        mask = probabilities >= threshold
        support = int(mask.sum())
        precision = float(y[mask].mean()) if support else None
        lift = (precision - base) if precision is not None else None
        row = {
            "threshold": threshold,
            "n": support,
            "precision": precision,
            "lift": lift,
        }
        grid.append(row)
        if precision is None or support < 400 or lift is None or lift < 0.04 or precision < 0.52:
            continue
        qualified.append(row)
    if not qualified:
        likely = 1.01
        edge = False
        precision = None
        support = 0
        lift = None
    else:
        chosen = min(qualified, key=lambda item: item["threshold"])
        likely = chosen["threshold"]
        precision = chosen["precision"]
        support = chosen["n"]
        lift = chosen["lift"]
        edge = True
    unlikely = max(0.05, base * 0.85)
    if edge:
        unlikely = min(unlikely, likely - 0.05)
    if unlikely >= likely:
        unlikely = max(0.02, likely - 0.05)
    return {
        "base_rate": base,
        "likely_threshold": float(likely),
        "unlikely_threshold": float(unlikely),
        "edge": edge,
        "precision_at_likely": precision,
        "n_likely": int(support),
        "lift": lift,
        "threshold_grid": grid,
    }


def decile_table(y: np.ndarray, probabilities: np.ndarray) -> list[dict]:
    frame = pd.DataFrame({"y": np.asarray(y, dtype=float), "p": np.asarray(probabilities, dtype=float)})
    if frame["p"].nunique() < 3:
        return []
    try:
        frame["bin"] = pd.qcut(frame["p"], 10, duplicates="drop")
    except ValueError:
        return []
    rows = []
    for label, group in frame.groupby("bin", observed=True):
        rows.append(
            {
                "bin": str(label),
                "n": int(len(group)),
                "mean_predicted": float(group["p"].mean()),
                "realized": float(group["y"].mean()),
            }
        )
    return rows


def summarize(y: np.ndarray, probabilities: np.ndarray, likely_threshold: float) -> dict:
    y = np.asarray(y, dtype=float)
    probabilities = np.asarray(probabilities, dtype=float)
    mask = probabilities >= likely_threshold
    support = int(mask.sum())
    positives = float(y.sum())
    precision = float(y[mask].mean()) if support else None
    recall = float(y[mask].sum() / positives) if support and positives else None
    auc = None
    if len(np.unique(y)) > 1:
        auc = float(roc_auc_score(y, probabilities))
    return {
        "n": int(len(y)),
        "base_rate": float(y.mean()),
        "auc": auc,
        "brier": float(brier_score_loss(y, np.clip(probabilities, 0, 1))),
        "likely_threshold": float(likely_threshold),
        "n_likely": support,
        "precision_at_likely": precision,
        "recall_at_likely": recall,
        "mean_predicted": float(probabilities.mean()),
    }


def evaluate_target(panel: pd.DataFrame, ycol: str) -> tuple[dict, list[np.ndarray], list[np.ndarray]]:
    folds = []
    ys: list[np.ndarray] = []
    ps: list[np.ndarray] = []
    for start, end in FOLDS:
        start_ts = pd.Timestamp(start)
        end_ts = pd.Timestamp(end)
        train = panel[panel["date"] < start_ts].dropna(subset=FEATURE_COLUMNS + [ycol])
        test = panel[(panel["date"] >= start_ts) & (panel["date"] < end_ts)].dropna(subset=FEATURE_COLUMNS + [ycol])
        if len(train) < 1500 or len(test) < 200:
            log.info("skip fold %s–%s for %s (train %s, test %s)", start, end, ycol, len(train), len(test))
            continue
        model = fit_estimator(train, ycol)
        probabilities = predict_proba(model, test)
        y = test[ycol].to_numpy(dtype=float)
        ys.append(y)
        ps.append(probabilities)
        # Threshold for the fold report is provisional; pooled selection is authoritative.
        folds.append(
            {
                "test_start": start,
                "test_end": end,
                "n_train": int(len(train)),
                **summarize(y, probabilities, 0.5),
            }
        )
    if not ys:
        raise RuntimeError(f"no walk-forward folds produced for {ycol}")
    return {"folds": folds}, ys, ps


def _coefficients(model: dict) -> list[dict]:
    clf = model["pipe"].named_steps["clf"]
    rows = []
    for key, value in zip(FEATURE_COLUMNS, clf.coef_[0]):
        rows.append({"key": key, "label": FEATURE_META[key][0], "coefficient": float(value)})
    rows.sort(key=lambda item: abs(item["coefficient"]), reverse=True)
    return rows


def _plain(value):
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if isinstance(value, (np.floating, float)):
        value = float(value)
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    return value


def build_panel(frames: dict[str, pd.DataFrame], nifty: pd.DataFrame) -> pd.DataFrame:
    market = compute_nifty_features(nifty).drop(columns=["nifty_close"])
    parts = []
    for symbol, raw in frames.items():
        if len(raw) < 160:
            continue
        features = compute_symbol_features(raw)
        features["symbol"] = symbol
        parts.append(features)
    if not parts:
        raise RuntimeError("no symbol produced features")
    panel = pd.concat(parts, ignore_index=True)
    panel = panel.merge(market, on="date", how="inner")
    panel[FEATURE_COLUMNS] = panel[FEATURE_COLUMNS].replace([np.inf, -np.inf], np.nan)
    panel = clip_features(panel)
    panel["date"] = pd.to_datetime(panel["date"])
    return panel


async def _download() -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    members = await load_index("NIFTY 200")
    log.info("Nifty 200 members: %s", len(members))
    nifty = await get_daily_history("^NSEI", max_age=12 * 3600)
    frames: dict[str, pd.DataFrame] = {}

    async def _one(item: dict):
        symbol = item["symbol"]
        try:
            frames[symbol] = await get_daily_history(to_yahoo(symbol, "NSE"), max_age=18 * 3600)
        except Exception as exc:
            log.warning("skip %s: %s", symbol, exc)

    batch = 10
    for index in range(0, len(members), batch):
        await asyncio.gather(*[_one(item) for item in members[index : index + batch]])
        log.info("histories %s/%s", min(index + batch, len(members)), len(members))
    log.info("usable downloads: %s", len(frames))
    return nifty, frames


async def train() -> dict:
    nifty, frames = await _download()
    panel = build_panel(frames, nifty)
    log.info("panel rows %s symbols %s", len(panel), panel["symbol"].nunique())
    metrics_targets = {}
    models = {}
    for key, spec in TARGETS.items():
        log.info("walk-forward %s", key)
        fold_info, ys, ps = evaluate_target(panel, spec["column"])
        y_all = np.concatenate(ys)
        p_all = np.concatenate(ps)
        thresholds = select_thresholds(y_all, p_all)
        pooled = summarize(y_all, p_all, thresholds["likely_threshold"])
        # Restate each fold at the chosen Likely cutoff so the table matches the signal.
        folds = []
        for fold, y, p in zip(fold_info["folds"], ys, ps):
            folds.append(
                {
                    "test_start": fold["test_start"],
                    "test_end": fold["test_end"],
                    "n_train": fold["n_train"],
                    **summarize(y, p, thresholds["likely_threshold"]),
                }
            )
        labeled = panel.dropna(subset=FEATURE_COLUMNS + [spec["column"]])
        models[key] = fit_estimator(labeled, spec["column"])
        metrics_targets[key] = {
            "name": spec["name"],
            "definition": spec["definition"],
            "column": spec["column"],
            "base_rate": thresholds["base_rate"],
            "likely_threshold": thresholds["likely_threshold"],
            "unlikely_threshold": thresholds["unlikely_threshold"],
            "edge": thresholds["edge"],
            "precision_at_likely": thresholds["precision_at_likely"],
            "n_likely": thresholds["n_likely"],
            "lift": thresholds["lift"],
            "threshold_grid": thresholds["threshold_grid"],
            "pooled": pooled,
            "folds": folds,
            "deciles": decile_table(y_all, p_all),
            "coefficients": _coefficients(models[key]),
        }
        log.info(
            "%s base %.3f likely>=%.2f precision=%s edge=%s auc=%s",
            key,
            thresholds["base_rate"],
            thresholds["likely_threshold"],
            thresholds["precision_at_likely"],
            thresholds["edge"],
            pooled.get("auc"),
        )

    dated = panel.dropna(subset=["ret_1"])
    metrics = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "universe": "NIFTY 200",
        "n_symbols": int(panel["symbol"].nunique()),
        "n_rows": int(len(panel)),
        "date_start": str(pd.to_datetime(dated["date"].min()).date()),
        "date_end": str(pd.to_datetime(panel["date"].max()).date()),
        "model": "L2 logistic regression with Platt calibration",
        "features": FEATURE_COLUMNS,
        "news_in_backtest": False,
        "note": (
            "Hit rate, precision, AUC, and Brier score are pooled walk-forward test results. "
            "Each test fold was scored by a model fit only on earlier dates. "
            "The live model is refit on the full labeled sample with the same recipe. "
            "Likely is the most inclusive cutoff where the test hit rate was at least 52% "
            "and at least 4 points above the base rate. "
            "News sentiment is not in the backtest; live probabilities may be nudged by at most 5 points."
        ),
        "targets": metrics_targets,
    }
    metrics = _plain(metrics)
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    (ARTIFACT_DIR / "metrics.json").write_text(json.dumps(metrics, indent=2))
    joblib.dump({"models": models, "feature_names": FEATURE_COLUMNS, "metrics": metrics}, ARTIFACT_DIR / "model.joblib")
    log.info("wrote %s", ARTIFACT_DIR / "model.joblib")
    return metrics


async def _main() -> None:
    try:
        await train()
    finally:
        await close_client()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    asyncio.run(_main())


if __name__ == "__main__":
    main()
