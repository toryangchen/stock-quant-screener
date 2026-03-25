from __future__ import annotations

import time
from dataclasses import dataclass
from threading import Lock
from typing import Any


@dataclass
class CacheEntry:
    expires_at: float
    value: Any


class TTLCache:
    def __init__(self) -> None:
        self._items: dict[str, CacheEntry] = {}
        self._lock = Lock()

    def get(self, key: str) -> Any | None:
        now = time.time()
        with self._lock:
            entry = self._items.get(key)
            if entry is None:
                return None
            if entry.expires_at <= now:
                self._items.pop(key, None)
                return None
            return entry.value

    def set(self, key: str, value: Any, ttl_seconds: int) -> Any:
        if ttl_seconds <= 0:
            return value
        with self._lock:
            self._items[key] = CacheEntry(expires_at=time.time() + ttl_seconds, value=value)
        return value

    def invalidate_prefix(self, prefix: str) -> None:
        with self._lock:
            for key in list(self._items):
                if key.startswith(prefix):
                    self._items.pop(key, None)
