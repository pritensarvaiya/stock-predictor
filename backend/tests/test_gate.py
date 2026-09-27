import base64
import hmac

from backend.app.auth import authorized, password, safe_next, session_token
from backend.app.sentiment.budget import GeminiBudget


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


def test_gemini_budget_allows_a_short_burst_then_stops():
    budget = GeminiBudget(per_minute=2, per_hour=3)
    assert budget.allow(0) is True
    assert budget.allow(1) is True
    assert budget.allow(2) is False
    assert budget.allow(61) is True
    assert budget.allow(62) is False
