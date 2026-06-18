"""Tiny in-memory rate limiter.

Sliding-window log keyed by an arbitrary string (here, the chat caller's IP).
No external dependency, no Redis: this is process-local and resets on restart,
which is the right trade-off for a single-instance deploy. For a multi-replica
production deploy, back the same interface with a shared store (Redis INCR + TTL).
"""

import threading
import time


class RateLimiter:
    def __init__(self, max_events: int, window_seconds: float) -> None:
        self.max_events = max_events
        self.window_seconds = window_seconds
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str, now: float | None = None) -> bool:
        """Record a hit for `key` and return False once the window is full.

        A non-positive `max_events` disables the limiter (always allows), so a
        config of 0 is an explicit opt-out rather than a lockout.
        """
        if self.max_events <= 0:
            return True
        now = time.monotonic() if now is None else now
        cutoff = now - self.window_seconds
        with self._lock:
            hits = [t for t in self._hits.get(key, ()) if t > cutoff]
            if len(hits) >= self.max_events:
                self._hits[key] = hits
                return False
            hits.append(now)
            self._hits[key] = hits
            return True
