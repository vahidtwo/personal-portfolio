"""In-memory sliding-window limits for auth endpoints.

Safe because the app runs a single uvicorn worker. Counts reset on restart.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import Request

_hits: dict[str, deque[float]] = defaultdict(deque)
_lock = Lock()

LOGIN_FAILS_PER_USER = 10
LOGIN_FAILS_PER_IP = 30
LOGIN_WINDOW_SECONDS = 15 * 60
REGISTER_PER_IP = 5
REGISTER_WINDOW_SECONDS = 60 * 60


def client_ip(request: Request) -> str:
    cf_ip = request.headers.get("cf-connecting-ip", "").strip()
    if cf_ip:
        return cf_ip
    return request.client.host if request.client else "unknown"


def _prune(bucket: deque[float], window: float, now: float) -> None:
    while bucket and now - bucket[0] > window:
        bucket.popleft()


def is_limited(key: str, limit: int, window: float) -> bool:
    now = time.monotonic()
    with _lock:
        bucket = _hits.get(key)
        if not bucket:
            return False
        _prune(bucket, window, now)
        return len(bucket) >= limit


def record(key: str, window: float) -> None:
    now = time.monotonic()
    with _lock:
        bucket = _hits[key]
        _prune(bucket, window, now)
        bucket.append(now)


def clear(key: str) -> None:
    with _lock:
        _hits.pop(key, None)


def reset_all() -> None:
    with _lock:
        _hits.clear()
