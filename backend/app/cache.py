"""Small JSON helpers and freshness checks for on-disk caches."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from backend.app.config import CACHE_DIR


def ensure_cache() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def is_fresh(path: Path, max_age_seconds: float) -> bool:
    if not path.exists():
        return False
    return (time.time() - path.stat().st_mtime) <= max_age_seconds


def read_json(path: Path, max_age_seconds: float | None = None) -> Any | None:
    if max_age_seconds is not None and not is_fresh(path, max_age_seconds):
        return None
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, default=str))
    tmp.replace(path)
