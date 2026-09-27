"""A small in-process cap on Gemini calls so a public URL cannot drain the key."""

from __future__ import annotations

import threading
import time

# One watchlist pass asks Gemini for about a dozen names. The cap allows that
# burst, then slows further calls to the local word list.
PER_MINUTE = 12
PER_HOUR = 48


class GeminiBudget:
    def __init__(self, per_minute: int = PER_MINUTE, per_hour: int = PER_HOUR) -> None:
        self.per_minute = per_minute
        self.per_hour = per_hour
        self._times: list[float] = []
        self._lock = threading.Lock()

    def allow(self, now: float | None = None) -> bool:
        moment = time.monotonic() if now is None else now
        with self._lock:
            self._times = [stamp for stamp in self._times if moment - stamp < 3600]
            in_minute = sum(1 for stamp in self._times if moment - stamp < 60)
            if in_minute >= self.per_minute or len(self._times) >= self.per_hour:
                return False
            self._times.append(moment)
            return True


gemini_budget = GeminiBudget()
