"""NSE cash-market hours and holidays in Asia/Kolkata.

The embedded list is the 2026 capital-market calendar (weekends included when
NSE lists them). On startup the app tries NSE's holiday-master API and, when
that succeeds, uses it instead.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
OPEN_TIME = time(9, 15)
CLOSE_TIME = time(15, 30)

# Official CM holidays for 2026, including weekend observances NSE publishes.
# Source: NSE holiday-master (CM segment), confirmed against the exchange circular.
FALLBACK_HOLIDAYS: dict[date, str] = {
    date(2026, 1, 15): "Municipal Corporation Election - Maharashtra",
    date(2026, 1, 26): "Republic Day",
    date(2026, 2, 15): "Mahashivratri",
    date(2026, 3, 3): "Holi",
    date(2026, 3, 21): "Id-Ul-Fitr (Ramadan Eid)",
    date(2026, 3, 26): "Shri Ram Navami",
    date(2026, 3, 31): "Shri Mahavir Jayanti",
    date(2026, 4, 3): "Good Friday",
    date(2026, 4, 14): "Dr. Baba Saheb Ambedkar Jayanti",
    date(2026, 5, 1): "Maharashtra Day",
    date(2026, 5, 28): "Bakri Id",
    date(2026, 6, 26): "Muharram",
    date(2026, 8, 15): "Independence Day",
    date(2026, 9, 14): "Ganesh Chaturthi",
    date(2026, 10, 2): "Mahatma Gandhi Jayanti",
    date(2026, 10, 20): "Dussehra",
    date(2026, 11, 8): "Diwali Laxmi Pujan",
    date(2026, 11, 10): "Diwali-Balipratipada",
    date(2026, 11, 24): "Prakash Gurpurb Sri Guru Nanak Dev",
    date(2026, 12, 25): "Christmas",
}

_holidays: dict[date, str] = dict(FALLBACK_HOLIDAYS)


def set_holidays(holidays: dict[date, str]) -> None:
    global _holidays
    _holidays = dict(holidays) if holidays else dict(FALLBACK_HOLIDAYS)


def holidays() -> dict[date, str]:
    return dict(_holidays)


def is_trading_day(day: date, holiday_map: dict[date, str] | None = None) -> bool:
    days = _holidays if holiday_map is None else holiday_map
    return day.weekday() < 5 and day not in days


def next_trading_day(day: date, holiday_map: dict[date, str] | None = None) -> date:
    cursor = day + timedelta(days=1)
    while not is_trading_day(cursor, holiday_map):
        cursor += timedelta(days=1)
    return cursor


def _at(day: date, clock: time) -> datetime:
    return datetime.combine(day, clock, tzinfo=IST)


def market_status(now: datetime | None = None, holiday_map: dict[date, str] | None = None) -> dict:
    """Describe the cash session and the next session the model is aimed at.

    The prediction horizon is the next session that has not started yet.
    Before the open, that is today. During the session or after the close,
    that is the following trading day.
    """
    clock = now.astimezone(IST) if now else datetime.now(IST)
    if clock.tzinfo is None:
        clock = clock.replace(tzinfo=IST)
    day = clock.date()
    days = _holidays if holiday_map is None else holiday_map
    holiday_name = days.get(day)
    open_dt = _at(day, OPEN_TIME)
    close_dt = _at(day, CLOSE_TIME)
    trading = is_trading_day(day, days)

    if trading and open_dt <= clock < close_dt:
        phase = "open"
        reason = "Regular session is open"
        horizon = next_trading_day(day, days)
        reference_mode = "live"
    elif trading and clock < open_dt:
        phase = "preopen"
        reason = "Before the open"
        horizon = day
        reference_mode = "prior_close"
    else:
        phase = "closed"
        horizon = next_trading_day(day, days)
        reference_mode = "close"
        if holiday_name and day.weekday() < 5:
            reason = f"Holiday · {holiday_name}"
            if "muhurat" in holiday_name.lower() or "laxmi pujan" in holiday_name.lower():
                reason += ". A short muhurat session may be scheduled; the regular session is treated as closed"
        elif day.weekday() >= 5:
            reason = "Weekend"
        else:
            reason = "Session over for the day"

    return {
        "phase": phase,
        "is_open": phase == "open",
        "timezone": "Asia/Kolkata",
        "now": clock.isoformat(),
        "reason": reason,
        "holiday_name": holiday_name if holiday_name and not trading else None,
        "regular_hours": "09:15–15:30 IST",
        "session_open": open_dt.isoformat() if trading else None,
        "session_close": close_dt.isoformat() if trading else None,
        "next_session_date": horizon.isoformat(),
        "next_session_open": _at(horizon, OPEN_TIME).isoformat(),
        "next_session_label": f"{horizon.strftime('%A')} {horizon.day} {horizon.strftime('%B %Y')}",
        "reference_mode": reference_mode,
    }
