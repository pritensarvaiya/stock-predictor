import pandas as pd
import pytest

from backend.app.features.indicators import (
    FEATURE_COLUMNS,
    SESSIONS_REQUIRED,
    compute_symbol_features,
    latest_feature_row,
    short_history_message,
)

STOCK_FEATURES = [key for key in FEATURE_COLUMNS if not key.startswith("nifty_")]


def flat_history(n=90):
    dates = pd.bdate_range("2024-01-02", periods=n)
    rows = []
    for i, day in enumerate(dates):
        price = 100 + i * 0.01
        rows.append(
            {
                "date": day,
                "open": price,
                "high": price * 1.002,
                "low": price * 0.998,
                "close": price,
                "adjclose": price,
                "volume": 1_000_000 + i,
            }
        )
    return pd.DataFrame(rows)


def test_future_shock_does_not_change_past_features_but_does_change_the_label():
    history = flat_history()
    before = compute_symbol_features(history)
    shocked = history.copy()
    prior_close = float(shocked.iloc[-2]["close"])
    shocked.loc[shocked.index[-1], "high"] = prior_close * 1.04
    after = compute_symbol_features(shocked)

    for key in STOCK_FEATURES:
        assert before.iloc[-2][key] == pytest.approx(after.iloc[-2][key], rel=1e-9, abs=1e-12)
    assert before.iloc[-2]["y_next"] == 0
    assert after.iloc[-2]["y_next"] == 1
    assert pd.isna(before.iloc[-1]["y_next"])


def test_watchlist_skips_a_new_listing_without_raising():
    from backend.app.services.watchlist import _score_frames

    rows = _score_frames(
        {"PRASOLCHEM": flat_history(8)},
        flat_history(80),
        [{"symbol": "PRASOLCHEM", "name": "Prasol Chemicals Limited"}],
    )
    assert rows == []


def test_short_history_is_not_scored_and_explains_the_wait():
    history = flat_history(8)
    nifty = flat_history(80)
    assert latest_feature_row(history, nifty) is None
    assert (
        short_history_message(8)
        == f"New listing: only 8 sessions of history, prediction starts after ~{SESSIONS_REQUIRED} sessions"
    )
    assert latest_feature_row(flat_history(SESSIONS_REQUIRED + 10), nifty) is not None


def test_five_day_label_needs_five_future_closes():
    features = compute_symbol_features(flat_history())
    assert features["y_5d"].iloc[-5:].isna().all()
    assert features["y_5d"].iloc[-6] in (0.0, 1.0)
