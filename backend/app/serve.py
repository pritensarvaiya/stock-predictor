"""Listen on $PORT (default 8000). One worker keeps the watchlist and rate limit in process."""

from __future__ import annotations

import os

import uvicorn


def main() -> None:
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("backend.app.main:app", host="0.0.0.0", port=port, workers=1)


if __name__ == "__main__":
    main()
