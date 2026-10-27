"""In-memory sliding-window limits for auth endpoints.

Safe because the app runs a single uvicorn worker. Counts reset on restart.
"""

from __future__ import annotations

import ipaddress
import math
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


# https://www.cloudflare.com/ips/ (update if Cloudflare adds ranges)
CLOUDFLARE_NETWORKS = tuple(
    ipaddress.ip_network(net)
    for net in (
        "173.245.48.0/20", "103.21.244.0/22", "103.22.200.0/22", "103.31.4.0/22",
        "141.101.64.0/18", "108.162.192.0/18", "190.93.240.0/20", "188.114.96.0/20",
        "197.234.240.0/22", "198.41.128.0/17", "162.158.0.0/15", "104.16.0.0/13",
        "104.24.0.0/14", "172.64.0.0/13", "131.0.72.0/22",
        "2400:cb00::/32", "2606:4700::/32", "2803:f800::/32", "2405:b500::/32",
        "2405:8100::/32", "2a06:98c0::/29", "2c0f:f248::/32",
    )
)


def _is_cloudflare(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(addr in net for net in CLOUDFLARE_NETWORKS)


def client_ip(request: Request) -> str:
    """Real visitor IP that a client cannot spoof.

    The proxy in front of the app (Traefik) appends the peer that connected to
    it as the last X-Forwarded-For entry. CF-Connecting-IP is trusted only when
    that peer is Cloudflare; a direct hit on the origin uses the peer itself.
    """
    forwarded = request.headers.get("x-forwarded-for", "")
    peer = forwarded.split(",")[-1].strip() if forwarded else ""
    if not peer:
        peer = request.client.host if request.client else "unknown"
    if _is_cloudflare(peer):
        cf_ip = request.headers.get("cf-connecting-ip", "").strip()
        if cf_ip:
            return cf_ip
    return peer


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


def retry_after(key: str, limit: int, window: float) -> int:
    """Seconds until `key` drops below `limit` again (0 when it is not limited).

    That is when the oldest hit that still counts against the limit leaves the window. Rounded up, never 0
    while limited, so it is safe to send as a `Retry-After` header.
    """
    now = time.monotonic()
    with _lock:
        bucket = _hits.get(key)
        if not bucket:
            return 0
        _prune(bucket, window, now)
        if len(bucket) < limit:
            return 0
        blocking = bucket[len(bucket) - limit]
        return max(1, math.ceil(window - (now - blocking)))


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
