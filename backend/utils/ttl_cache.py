"""Small thread-safe TTL cache; per-process today, swappable for Redis later."""

import copy
import threading
import time
from collections import OrderedDict
from typing import Any, Callable


class _Miss:
    def __repr__(self) -> str:
        return "CACHE_MISS"


CACHE_MISS = _Miss()


class TTLCache:
    """Bounded TTL cache with oldest-first eviction and hit/miss counters."""

    def __init__(self, max_entries: int = 2000, clock: Callable[[], float] = time.monotonic):
        self.max_entries = max(1, int(max_entries))
        self._clock = clock
        self._lock = threading.Lock()
        self._entries: "OrderedDict[Any, tuple[float, Any]]" = OrderedDict()
        self.hits = 0
        self.misses = 0

    def get(self, key: Any) -> Any:
        """Return a deep copy of a live entry, or CACHE_MISS."""
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                self.misses += 1
                return CACHE_MISS
            expires_at, value = entry
            if expires_at <= self._clock():
                del self._entries[key]
                self.misses += 1
                return CACHE_MISS
            self.hits += 1
            return copy.deepcopy(value)

    def set(self, key: Any, value: Any, ttl_seconds: float) -> None:
        """Store a deep copy of value for ttl_seconds."""
        if ttl_seconds <= 0:
            return
        with self._lock:
            if key not in self._entries and len(self._entries) >= self.max_entries:
                self._entries.popitem(last=False)
            self._entries[key] = (self._clock() + ttl_seconds, copy.deepcopy(value))

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    @property
    def stats(self) -> dict:
        with self._lock:
            return {"hits": self.hits, "misses": self.misses, "entries": len(self._entries)}
