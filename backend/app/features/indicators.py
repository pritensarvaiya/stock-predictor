"""Technical features and labels.

Features at the close of day t use only information known by that close.
Labels look forward and are never fed back into the feature columns.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

FEATURE_COLUMNS = [
    "ret_1",
    "ret_5",
    "ret_10",
    "ret_20",
    "rsi_14",
    "macd_hist_pct",
    "dist_sma20",
    "dist_sma50",
    "atr_pct",
    "vol_ratio",
    "gap_1",
    "gap_5_mean",
    "dist_high20",
    "range_pct",
    "close_loc",
    "nifty_ret_5",
    "nifty_ret_20",
    "nifty_dist_sma50",
]

FEATURE_META = {
    "ret_1": ("1-day return", "pct"),
    "ret_5": ("5-day return", "pct"),
    "ret_10": ("10-day return", "pct"),
    "ret_20": ("20-day return", "pct"),
    "rsi_14": ("14-day RSI", "rsi"),
    "macd_hist_pct": ("MACD histogram", "pct"),
    "dist_sma20": ("Distance from 20-day average", "pct"),
    "dist_sma50": ("Distance from 50-day average", "pct"),
    "atr_pct": ("Average true range", "pct"),
    "vol_ratio": ("Volume versus recent average", "ratio"),
    "gap_1": ("Today's opening gap", "pct"),
    "gap_5_mean": ("Average gap over 5 sessions", "pct"),
    "dist_high20": ("Distance from the 20-day high", "pct"),
    "range_pct": ("Today's high-low range", "pct"),
    "close_loc": ("Where the close sat in today's range", "loc"),
    "nifty_ret_5": ("Nifty 50 5-day return", "pct"),
    "nifty_ret_20": ("Nifty 50 20-day return", "pct"),
    "nifty_dist_sma50": ("Nifty 50 versus its 50-day average", "pct"),
}

CLIPS = {
    "ret_1": (-0.2, 0.2),
    "ret_5": (-0.35, 0.35),
    "ret_10": (-0.5, 0.5),
    "ret_20": (-0.6, 0.6),
    "rsi_14": (0.0, 100.0),
    "macd_hist_pct": (-0.05, 0.05),
    "dist_sma20": (-0.3, 0.3),
    "dist_sma50": (-0.4, 0.4),
    "atr_pct": (0.0, 0.08),
    "vol_ratio": (0.0, 8.0),
    "gap_1": (-0.1, 0.1),
    "gap_5_mean": (-0.05, 0.05),
    "dist_high20": (-0.4, 0.02),
    "range_pct": (0.0, 0.12),
    "close_loc": (0.0, 1.0),
    "nifty_ret_5": (-0.15, 0.15),
    "nifty_ret_20": (-0.2, 0.2),
    "nifty_dist_sma50": (-0.2, 0.2),
}

MARKET_COLUMNS = ["nifty_ret_5", "nifty_ret_20", "nifty_dist_sma50"]


def format_feature(key: str, value: float) -> str:
    kind = FEATURE_META[key][1]
    if kind == "pct":
        if key in {"atr_pct", "range_pct"}:
            return f"{value * 100:.1f}%"
        return f"{value * 100:+.1f}%"
    if kind == "rsi":
        return f"{value:.0f}"
    if kind == "ratio":
        return f"{value:.1f}×"
    if kind == "loc":
        return f"{value:.0%} of the day's range"
    return f"{value:.3f}"


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    # A run of only up days has no average loss; that is RSI 100, not a missing value.
    rsi = rsi.mask((avg_loss == 0) & (avg_gain > 0), 100.0)
    rsi = rsi.mask((avg_gain == 0) & (avg_loss > 0), 0.0)
    rsi = rsi.mask((avg_gain == 0) & (avg_loss == 0) & avg_gain.notna(), 50.0)
    return rsi


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    prev = close.shift(1)
    true_range = pd.concat([(high - low), (high - prev).abs(), (low - prev).abs()], axis=1).max(axis=1)
    return true_range.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()


def _adjusted(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.sort_values("date").reset_index(drop=True).copy()
    out["date"] = pd.to_datetime(out["date"]).dt.normalize()
    ratio = (out["adjclose"] / out["close"].replace(0, np.nan)).replace([np.inf, -np.inf], np.nan).fillna(1.0)
    for col in ("open", "high", "low", "close"):
        out[col] = out[col].astype(float) * ratio
    out["raw_close"] = frame.sort_values("date").reset_index(drop=True)["close"].astype(float)
    out["raw_prev"] = out["raw_close"].shift(1)
    return out


def compute_symbol_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Per-stock features and forward labels. Market columns are attached later."""
    data = _adjusted(frame)
    close = data["close"]
    high = data["high"]
    low = data["low"]
    open_ = data["open"]
    volume = data["volume"].astype(float)

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    macd_signal = macd_line.ewm(span=9, adjust=False).mean()
    gap = open_ / close.shift(1) - 1
    span = (high - low).replace(0, np.nan)

    out = pd.DataFrame({"date": data["date"]})
    out["raw_close"] = data["raw_close"]
    out["raw_prev"] = data["raw_prev"]
    out["ret_1"] = close.pct_change(1)
    out["ret_5"] = close.pct_change(5)
    out["ret_10"] = close.pct_change(10)
    out["ret_20"] = close.pct_change(20)
    out["rsi_14"] = _rsi(close)
    out["macd_hist_pct"] = (macd_line - macd_signal) / close
    out["dist_sma20"] = close / close.rolling(20).mean() - 1
    out["dist_sma50"] = close / close.rolling(50).mean() - 1
    out["atr_pct"] = _atr(high, low, close) / close
    out["vol_ratio"] = volume / volume.shift(1).rolling(20).mean()
    out["gap_1"] = gap
    out["gap_5_mean"] = gap.rolling(5).mean()
    out["dist_high20"] = close / high.rolling(20).max() - 1
    out["range_pct"] = (high - low) / close
    out["close_loc"] = ((close - low) / span).fillna(0.5)

    future_high = high.shift(-1)
    out["y_next"] = ((future_high / close - 1) >= 0.02).astype(float).where(future_high.notna())
    future = pd.concat([close.shift(-k) for k in range(1, 6)], axis=1)
    out["y_5d"] = ((future.max(axis=1) / close - 1) >= 0.02).where(future.notna().all(axis=1)).astype(float)
    return out


def compute_nifty_features(frame: pd.DataFrame) -> pd.DataFrame:
    data = _adjusted(frame)
    close = data["close"]
    out = pd.DataFrame({"date": data["date"]})
    out["nifty_ret_5"] = close.pct_change(5)
    out["nifty_ret_20"] = close.pct_change(20)
    out["nifty_dist_sma50"] = close / close.rolling(50).mean() - 1
    out["nifty_close"] = data["raw_close"]
    return out


def clip_features(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    for key, (low, high) in CLIPS.items():
        if key in out.columns:
            out[key] = out[key].clip(low, high)
    return out


def latest_feature_row(stock: pd.DataFrame, nifty: pd.DataFrame) -> pd.Series | None:
    features = compute_symbol_features(stock)
    market = compute_nifty_features(nifty)
    merged = features.merge(market.drop(columns=["nifty_close"]), on="date", how="left")
    merged = clip_features(merged)
    usable = merged.dropna(subset=FEATURE_COLUMNS)
    if usable.empty:
        return None
    return usable.iloc[-1]
