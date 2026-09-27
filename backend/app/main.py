"""Desk API: NSE search, prices, a calibrated +2% model, and a next-session list."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from urllib.parse import parse_qs

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.app.auth import attach_session, authorized, check_password, gate, login_page, password, safe_next
from backend.app.cache import ensure_cache
from backend.app.config import DISCLAIMER, GEMINI_API_KEY, GEMINI_MODEL, ROOT
from backend.app.data.holidays import refresh_holiday_calendar
from backend.app.data.symbols import load_equities, search_symbols
from backend.app.http_client import DataError, close_client
from backend.app.market_calendar import market_status
from backend.app.model.predict import ModelNotReady, metrics, model_path
from backend.app.services.stock import chart, clean_exchange, clean_symbol, prediction, quote, stock_page
from backend.app.services.stock import news as stock_news
from backend.app.services.watchlist import WatchlistService

log = logging.getLogger(__name__)
watchlist = WatchlistService()


async def _warm_equities() -> None:
    try:
        await load_equities()
    except Exception:
        log.exception("equity list warmup failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    ensure_cache()
    # Holiday and equity refreshes must not hold the process before it can listen.
    # The embedded holiday list and the shipped equity file cover a slow or blocked NSE.
    holiday_task = asyncio.create_task(refresh_holiday_calendar())
    equity_task = asyncio.create_task(_warm_equities())
    watchlist.kick()
    yield
    for task in (holiday_task, equity_task, watchlist._task):
        if task and not task.done():
            task.cancel()
    await close_client()


app = FastAPI(title="Desk", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
app.middleware("http")(gate)


@app.exception_handler(DataError)
async def on_data_error(_request, exc: DataError):
    return JSONResponse(status_code=502, content={"detail": str(exc)})


@app.exception_handler(ModelNotReady)
async def on_model_missing(_request, exc: ModelNotReady):
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.get("/api/health")
async def health():
    # Render probes this on every deploy and after a free-instance wake.
    # It must answer from local files only. Equity and price caches are
    # rebuilt later, in the background, and are gone after spin-down.
    return {
        "ok": True,
        "model": model_path().exists(),
        "gemini": bool(GEMINI_API_KEY),
        "auth": bool(password()),
    }


@app.get("/api/market")
async def market():
    return market_status()


@app.get("/api/symbols")
async def symbols(q: str | None = None, limit: int = Query(8, ge=1, le=50)):
    payload = await load_equities()
    if q:
        return {
            "count": payload["count"],
            "source": payload["source"],
            "matches": search_symbols(payload["symbols"], q, limit),
        }
    return payload


@app.get("/api/quote/{symbol}")
async def quote_route(symbol: str, exchange: str = "NSE"):
    return await quote(symbol, exchange)


@app.get("/api/chart/{symbol}")
async def chart_route(symbol: str, range: str = "6M", exchange: str = "NSE"):
    return await chart(symbol, exchange, range)


@app.get("/api/news/{symbol}")
async def news_route(symbol: str, exchange: str = "NSE"):
    return await stock_news(symbol, exchange)


@app.get("/api/predict/{symbol}")
async def predict_route(symbol: str, exchange: str = "NSE"):
    try:
        return await prediction(symbol, exchange)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/stock/{symbol}")
async def stock_route(symbol: str, exchange: str = "NSE"):
    try:
        return await stock_page(symbol, exchange)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/watchlist")
async def watchlist_route():
    watchlist.kick()
    return watchlist.payload()


@app.post("/api/watchlist/refresh")
async def watchlist_refresh():
    watchlist.kick(force=True)
    return watchlist.payload()


@app.get("/api/metrics")
async def metrics_route():
    try:
        body = metrics()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    body = {**body, "disclaimer": DISCLAIMER}
    return body


@app.get("/login")
async def login_form(request: Request, next: str = "/"):
    if password() and authorized(request):
        return RedirectResponse(safe_next(next), status_code=303)
    if not password():
        return RedirectResponse("/", status_code=303)
    return login_page(nxt=safe_next(next))


@app.post("/api/login")
async def login_submit(request: Request):
    form = parse_qs((await request.body()).decode())
    given = form.get("password", [""])[0]
    nxt = safe_next(form.get("next", ["/"])[0])
    secret = password()
    if not secret:
        return RedirectResponse("/", status_code=303)
    if check_password(given, secret):
        response = RedirectResponse(nxt, status_code=303)
        return attach_session(response, request, secret)
    return login_page(error=True, nxt=nxt)


@app.get("/api/symbol-check/{symbol}")
async def symbol_check(symbol: str, exchange: str = "NSE"):
    """Small helper so the UI can reject junk paths before calling Yahoo."""
    try:
        clean_symbol(symbol)
        clean_exchange(exchange)
    except DataError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True}


dist = ROOT / "frontend" / "dist"
if dist.exists():

    class SpaFiles(StaticFiles):
        async def get_response(self, path: str, scope):
            try:
                return await super().get_response(path, scope)
            except StarletteHTTPException as exc:
                if exc.status_code == 404 and not path.startswith("assets/"):
                    return await super().get_response("index.html", scope)
                raise

    app.mount("/", SpaFiles(directory=dist, html=True), name="frontend")
