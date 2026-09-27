import base64
import hmac

from backend.app.auth import authorized, password, safe_next, session_token
from backend.app.sentiment.budget import GeminiBudget
from backend.app.services.watchlist import watchlist_settings


class _Request:
    def __init__(self, cookie="", authorization=""):
        self.cookies = {"desk_session": cookie} if cookie else {}
        self.headers = {"authorization": authorization} if authorization else {}


def test_open_when_password_unset(monkeypatch):
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    assert password() == ""
    assert authorized(_Request()) is True


def test_cookie_and_basic_auth(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "s3cret")
    assert authorized(_Request()) is False
    assert authorized(_Request(cookie=session_token("s3cret"))) is True
    assert authorized(_Request(cookie=session_token("nope"))) is False
    good = "Basic " + base64.b64encode(b"desk:s3cret").decode()
    bad = "Basic " + base64.b64encode(b"desk:nope").decode()
    assert authorized(_Request(authorization=good)) is True
    assert authorized(_Request(authorization=bad)) is False
    assert hmac.compare_digest(session_token("s3cret"), session_token("s3cret"))


def test_safe_next_rejects_offsite_urls():
    assert safe_next("/stock/RELIANCE") == "/stock/RELIANCE"
    assert safe_next("https://evil.example") == "/"
    assert safe_next("//evil.example") == "/"
    assert safe_next(None) == "/"


def test_watchlist_settings_default_and_overrides(monkeypatch):
    monkeypatch.delenv("WATCHLIST_UNIVERSE", raising=False)
    monkeypatch.delenv("WATCHLIST_BATCH", raising=False)
    assert watchlist_settings() == ("NIFTY 200", 4)
    monkeypatch.setenv("WATCHLIST_UNIVERSE", "nifty 100")
    monkeypatch.setenv("WATCHLIST_BATCH", "2")
    assert watchlist_settings() == ("NIFTY 100", 2)
    monkeypatch.setenv("WATCHLIST_UNIVERSE", "SENSEX")
    monkeypatch.setenv("WATCHLIST_BATCH", "nope")
    assert watchlist_settings() == ("NIFTY 200", 4)
    monkeypatch.setenv("WATCHLIST_BATCH", "100")
    assert watchlist_settings()[1] == 16


def test_gemini_budget_allows_a_short_burst_then_stops():
    budget = GeminiBudget(per_minute=2, per_hour=3)
    assert budget.allow(0) is True
    assert budget.allow(1) is True
    assert budget.allow(2) is False
    assert budget.allow(61) is True
    assert budget.allow(62) is False
