"""Optional password gate. The app stays open when APP_PASSWORD is unset."""

from __future__ import annotations

import base64
import hashlib
import hmac
import html
import os
from urllib.parse import quote

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

COOKIE = "desk_session"


def password() -> str:
    return os.getenv("APP_PASSWORD", "").strip()


def session_token(secret: str) -> str:
    return hmac.new(b"desk-session-v1", secret.encode(), hashlib.sha256).hexdigest()


def safe_next(value: str | None) -> str:
    if value and value.startswith("/") and not value.startswith("//"):
        return value
    return "/"


def check_password(given: str, secret: str) -> bool:
    return hmac.compare_digest(session_token(given), session_token(secret))


def authorized(request: Request) -> bool:
    secret = password()
    if not secret:
        return True
    expected = session_token(secret)
    cookie = request.cookies.get(COOKIE, "")
    if cookie and hmac.compare_digest(cookie, expected):
        return True
    header = request.headers.get("authorization", "")
    if header.lower().startswith("basic "):
        try:
            raw = base64.b64decode(header.split(" ", 1)[1].strip(), validate=True).decode()
        except Exception:
            return False
        _user, sep, given = raw.partition(":")
        if sep and hmac.compare_digest(session_token(given), expected):
            return True
    return False


def is_public(path: str) -> bool:
    return path in {"/api/health", "/login", "/api/login"}


def login_page(*, error: bool = False, nxt: str = "/") -> HTMLResponse:
    message = "<p class=\"error\">That password did not match.</p>" if error else ""
    status = 401 if error else 200
    safe = html.escape(nxt, quote=True)
    html_doc = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Sign in · Desk</title>
  <style>
    :root {{ color-scheme: dark; }}
    body {{ margin: 0; min-height: 100vh; display: grid; place-items: center;
      background: #0b0d11; color: #e8edf4; font: 16px/1.45 Outfit, "Segoe UI", sans-serif; }}
    form {{ width: min(420px, calc(100% - 32px)); background: #161b22;
      border: 1px solid rgba(232,237,244,.12); border-radius: 22px; padding: 22px;
      box-shadow: 0 12px 32px rgba(0,0,0,.35); }}
    h1 {{ font-family: Georgia, serif; font-weight: 560; letter-spacing: -0.03em; margin: 0 0 8px; }}
    p {{ color: #a7b0bf; margin: 0 0 16px; }}
    .error {{ color: #ff7b7b; }}
    label {{ display: block; font-size: 0.82rem; letter-spacing: 0.04em; color: #a7b0bf; }}
    input {{ width: 100%; box-sizing: border-box; margin-top: 6px; padding: 12px 14px;
      border-radius: 14px; border: 1px solid rgba(232,237,244,.12); background: #12161d; color: inherit; }}
    button {{ margin-top: 14px; width: 100%; padding: 12px; border: 0; border-radius: 999px;
      background: #e8edf4; color: #0c0e12; font: inherit; cursor: pointer; }}
  </style>
</head>
<body>
  <form method="post" action="/api/login">
    <h1>Desk</h1>
    <p>This copy is password protected.</p>
    {message}
    <input type="hidden" name="next" value="{safe}" />
    <label>Password
      <input type="password" name="password" autocomplete="current-password" required />
    </label>
    <button type="submit">Continue</button>
  </form>
</body>
</html>"""
    return HTMLResponse(html_doc, status_code=status)


def attach_session(response, request: Request, secret: str):
    forwarded = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip()
    secure = request.url.scheme == "https" or forwarded == "https"
    response.set_cookie(
        COOKIE,
        session_token(secret),
        httponly=True,
        samesite="lax",
        secure=secure,
        path="/",
        max_age=14 * 24 * 3600,
    )
    return response


async def gate(request: Request, call_next):
    path = request.url.path
    if is_public(path) or authorized(request):
        return await call_next(request)
    if path.startswith("/api"):
        return JSONResponse(status_code=401, content={"detail": "Sign in required"})
    nxt = quote(path + (f"?{request.url.query}" if request.url.query else ""))
    return RedirectResponse(f"/login?next={nxt}", status_code=303)
