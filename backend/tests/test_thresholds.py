import numpy as np
import pytest

from backend.app.model.predict import news_adjust
from backend.app.model.train import select_thresholds


def test_likely_cutoff_requires_a_real_edge():
    rng = np.random.default_rng(1)
    y = rng.integers(0, 2, size=4000)
    weak = np.full(4000, 0.5)
    no_edge = select_thresholds(y, weak)
    assert no_edge["edge"] is False
    assert no_edge["likely_threshold"] > 1

    strong = np.where(y == 1, 0.82, 0.18)
    edged = select_thresholds(y, strong)
    assert edged["edge"] is True
    assert edged["precision_at_likely"] > 0.7
    assert edged["precision_at_likely"] > edged["base_rate"] + 0.04
    assert edged["unlikely_threshold"] < edged["likely_threshold"]


def test_a_better_than_usual_rate_below_half_is_not_likely():
    rng = np.random.default_rng(2)
    low = rng.uniform(0.05, 0.29, 6000)
    high = rng.uniform(0.60, 0.80, 2000)
    probabilities = np.concatenate([low, high])
    outcomes = np.zeros(8000)
    outcomes[:6000] = rng.random(6000) < 0.10
    outcomes[6000:] = rng.random(2000) < 0.45
    result = select_thresholds(outcomes, probabilities)
    assert result["edge"] is False
    assert result["likely_threshold"] > 1


def test_news_nudge_is_capped_and_needs_more_than_one_headline():
    same, nudge = news_adjust(0.4, {"score": 1, "headline_count": 1})
    assert same == 0.4 and nudge == 0
    adjusted, nudge = news_adjust(0.4, {"score": 1, "headline_count": 4})
    assert adjusted == pytest.approx(0.45)
    assert nudge == pytest.approx(0.05)
    floored, _nudge = news_adjust(0.03, {"score": -1, "headline_count": 3})
    assert floored == 0.02
