---
title: Desk
emoji: 📈
colorFrom: gray
colorTo: green
sdk: docker
app_port: 8000
---

# Desk

A local research desk for an individual investor in India (Asia/Kolkata). It searches the full NSE equity list, shows delayed prices and a chart, estimates the chance a stock prints a +2% move, and ranks a Nifty 200 watchlist for the next cash session.

The numbers are probabilities from a historical model. They are often wrong. This is not financial advice.

## Run it

```bash
./scripts/setup.sh
./scripts/dev.sh
```

Open [http://127.0.0.1:5173](http://127.0.0.1:5173). The API is on port 8000 and the Vite dev server proxies `/api` to it.

On Windows, from the repo root in PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python -m pip install -r backend\requirements.txt
Copy-Item .env.example .env
cd frontend
npm install
cd ..
.\.venv\Scripts\python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

Leave that window running, and in a second window:

```powershell
cd frontend
npm run dev -- --host 127.0.0.1 --port 5173
```

`setup.sh` creates a virtualenv, installs Python and npm packages, and copies `.env.example` to `.env` if you do not already have one. The first Nifty 200 scan downloads daily history and can take a few minutes. Later scans reuse the on-disk cache.

To put the same app on a public URL, see [DEPLOY.md](DEPLOY.md). That path is one container on `$PORT` and does not replace these local commands.

To rebuild the measured model after you have had the cache warm:

```bash
source .venv/bin/activate
python -m backend.app.model.train
```

## Environment

| Variable | Purpose |
| --- | --- |
| `GEMINI_API_KEY` | Optional. When set, news summaries and the price-impact note come from Google Gemini. Never commit a real key. |
| `GEMINI_MODEL` | Gemini model id. Defaults to `gemini-3.1-flash-lite`. |
| `APP_PASSWORD` | Optional. When set, the UI and API ask for this password. Leave unset for open local use. |
| `PORT` | Listen port for the container. Local `scripts/dev.sh` stays on 8000 and 5173. |

With no key, sentiment is a local scorer: [VADER](https://github.com/cjhutto/vaderSentiment) plus a short list of finance phrases. That fallback is a word list. It misses context. FinBERT would need PyTorch, which is a heavy install for a local app, so it is not the default.

## What the screen is estimating

Two definitions, both shown:

1. **Next session high +2%** (this is what the watchlist ranks). The next NSE cash session's high is at least 2% above the reference price. A hit does not mean the stock closes up 2%. Volatile names reach it more often.
2. **Close +2% within 5 sessions.** At least one of the next five session closes is 2% or more above the reference price.

The reference price is the last close when the market is shut, which matches the backtest. During the session it is the latest trade, and the page says so, because that case was not the one measured.

Signals are **Likely**, **Uncertain**, and **Unlikely**. Likely is only used when a walk-forward cutoff beat the base rate by at least 4 percentage points with at least 250 test calls behind it. Otherwise Likely is withheld.

Headlines can nudge a live probability by at most 5 points. That nudge is not part of the historical hit rate. The hit rate on the stock page and the method page is the walk-forward precision of the price model.

## Data sources

- **Listings:** [NSE EQUITY_L.csv](https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv), series EQ, BE, and BZ. A full copy ships in `backend/data/fallbacks/` so search still works if the download is blocked. The app refreshes it when NSE is reachable.
- **Index membership:** Nifty Indices constituent files for the Nifty 100 and Nifty 200. The model and the watchlist use the Nifty 200.
- **Prices and charts:** Yahoo Finance chart endpoint (`.NS` for NSE, `.BO` for BSE). Treat quotes as delayed, often by about 15 minutes. They are not an exchange feed. The UI says this.
- **Benchmark:** Nifty 50 via `^NSEI`.
- **News:** Google News RSS (personal, non-commercial use of that feed) and NSE corporate announcements when the exchange API responds.
- **Hours:** NSE cash session 09:15–15:30 IST, weekdays, skipping the exchange holiday list. The app tries NSE's holiday-master API and otherwise uses the embedded 2026 capital-market calendar.

Caching and a small outbound pace limit sit in front of Yahoo, Google News, and NSE so a refresh loop does not hammer them. Quotes are cached for about half a minute while the market is open and longer when it is closed.

Any NSE symbol on the detail page can be switched to BSE (same ticker, `.BO`). US tickers are a later addition: `exchange=US` already maps to a bare Yahoo symbol, but there is no US symbol universe in the search box yet.

## Model

Features at the close of day *t* use only information known by that close: returns, RSI, MACD histogram, moving-average distance, ATR, volume change, gaps, the day's range, and the Nifty 50's 5-day, 20-day, and 50-day trend. Labels look forward and are not used as inputs.

Training is walk-forward. Test folds are H2 2024, H1 2025, H2 2025, and 2026 to date. Inside each training window the logistic regression is fit on the earlier dates and Platt-calibrated on the log-odds from the latest 20% of those dates. Reported hit rate, AUC, Brier score, and the decile table are pooled out-of-sample test rows. See **Method** in the app for the measured figures from the last training run (`backend/app/model/artifacts/metrics.json`).

Last training run, 26 Sep 2026, Nifty 200, features from 28 Sep 2021 through 25 Sep 2026:

| Target | Test rows | Base rate | AUC | Brier | Likely if probability | Hit rate when Likely | Likely calls |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Next session high +2% | 107,734 | 24.4% | 0.669 | 0.172 | ≥ 50% | 52.3% | 4,935 |
| Close +2% within 5 sessions | 106,934 | 41.3% | 0.588 | 0.239 | ≥ 55% | 53.4% | 15,618 |

Likely means the test hit rate was at least 52% and at least 4 points above the base rate. For the next-session high, that is a real but modest edge: those calls landed a bit more often than not, against a 24% base rate. Scores above 70% are a thin tail. In that same test, calls at or above 70% were followed by a +2% high 63% of the time, not at the headline percentage. The app says this next to an extreme score.

## Layout

```
backend/app          FastAPI app, data clients, features, model
backend/data         shipped NSE/Nifty files; runtime cache is gitignored
frontend             React + Vite
scripts/setup.sh     one-time install
scripts/dev.sh       API and UI together
```

Tests that do not need the network:

```bash
source .venv/bin/activate
python -m pytest backend/tests
```
