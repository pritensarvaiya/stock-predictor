from datetime import datetime
from zoneinfo import ZoneInfo

from backend.app.market_calendar import FALLBACK_HOLIDAYS, IST, market_status

HOLIDAYS = FALLBACK_HOLIDAYS


def at(year, month, day, hour, minute):
    return datetime(year, month, day, hour, minute, tzinfo=ZoneInfo("Asia/Kolkata"))


def test_weekend_is_closed_and_points_at_monday():
    status = market_status(at(2026, 9, 26, 13, 0), HOLIDAYS)
    assert status["phase"] == "closed"
    assert status["is_open"] is False
    assert status["reason"] == "Weekend"
    assert status["next_session_date"] == "2026-09-28"
    assert status["reference_mode"] == "close"
    assert status["timezone"] == "Asia/Kolkata"
    assert IST.key == "Asia/Kolkata"


def test_holiday_is_closed():
    status = market_status(at(2026, 9, 14, 11, 0), HOLIDAYS)
    assert status["phase"] == "closed"
    assert "Ganesh Chaturthi" in status["reason"]
    assert status["next_session_date"] == "2026-09-15"


def test_friday_session_phases():
    preopen = market_status(at(2026, 9, 25, 8, 0), HOLIDAYS)
    assert preopen["phase"] == "preopen"
    assert preopen["next_session_date"] == "2026-09-25"
    assert preopen["reference_mode"] == "prior_close"

    open_ = market_status(at(2026, 9, 25, 10, 0), HOLIDAYS)
    assert open_["phase"] == "open"
    assert open_["is_open"] is True
    assert open_["next_session_date"] == "2026-09-28"
    assert open_["reference_mode"] == "live"

    closed = market_status(at(2026, 9, 25, 16, 0), HOLIDAYS)
    assert closed["phase"] == "closed"
    assert closed["next_session_date"] == "2026-09-28"
    assert closed["reason"] == "Session over for the day"


def test_open_starts_at_nine_fifteen():
    before = market_status(at(2026, 9, 28, 9, 14), HOLIDAYS)
    after = market_status(at(2026, 9, 28, 9, 15), HOLIDAYS)
    assert before["phase"] == "preopen"
    assert after["phase"] == "open"
