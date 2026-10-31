"""Sliding-window limits for auth endpoints, persisted in a small SQLite file.

The counts live in DATA_DIR/rate_limit.sqlite (a separate file on the data volume, not the app
database), so a restart or redeploy does not reset them. Wall-clock time is used for that reason.

Backoff: each time a key with a known limit reaches it again, the lockout doubles
(window, 2x, 4x ... capped at MAX_LOCK_SECONDS). A successful login clears the key.
"""

from __future__ import annotations

import ipaddress
import math
import os
import sqlite3
import time
from pathlib import Path
from threading import Lock

from fastapi import Request

_lock = Lock()
_conns: dict[str, sqlite3.Connection] = {}

LOGIN_FAILS_PER_USER = 10
LOGIN_FAILS_PER_IP = 30
LOGIN_WINDOW_SECONDS = 15 * 60
REGISTER_PER_IP = 5
REGISTER_WINDOW_SECONDS = 60 * 60
MAX_LOCK_SECONDS = 24 * 60 * 60
DB_NAME = "rate_limit.sqlite"


def _parse(nets):
    return tuple(ipaddress.ip_network(n) for n in nets)


# https://www.cloudflare.com/ips/ (update if Cloudflare adds ranges)
CLOUDFLARE_NETWORKS = _parse((
    "173.245.48.0/20", "103.21.244.0/22", "103.22.200.0/22", "103.31.4.0/22",
    "141.101.64.0/18", "108.162.192.0/18", "190.93.240.0/20", "188.114.96.0/20",
    "197.234.240.0/22", "198.41.128.0/17", "162.158.0.0/15", "104.16.0.0/13",
    "104.24.0.0/14", "172.64.0.0/13", "131.0.72.0/22",
    "2400:cb00::/32", "2606:4700::/32", "2803:f800::/32", "2405:b500::/32",
    "2405:8100::/32", "2a06:98c0::/29", "2c0f:f248::/32",
))

# https://www.arvancloud.ir/en/ips.txt (update if ArvanCloud adds ranges)
ARVANCLOUD_NETWORKS = _parse((
    "185.143.232.0/22", "188.229.116.16/30", "94.101.182.0/27", "2.144.3.128/28",
    "37.32.16.0/27", "37.32.17.0/27", "37.32.18.0/27", "37.32.19.0/27",
    "185.215.232.0/22", "178.131.120.48/28", "94.101.183.0/28", "78.157.36.112/28",
    "95.38.61.80/28", "193.24.119.0/29",
))


def _in(ip: str, nets) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(addr in net for net in nets)


def _is_cloudflare(ip: str) -> bool:
    return _in(ip, CLOUDFLARE_NETWORKS)


def _is_arvancloud(ip: str) -> bool:
    return _in(ip, ARVANCLOUD_NETWORKS)


def _valid_ip(value: str) -> str | None:
    try:
        return str(ipaddress.ip_address(value.strip()))
    except ValueError:
        return None


def client_ip(request: Request) -> str:
    """Real visitor IP that a client cannot spoof.

    The peer is request.client.host: uvicorn (--proxy-headers) sets it from the entry Traefik
    appends, and the app port is not published. X-Forwarded-For is never read here. A CDN's
    real-IP header is trusted only when the peer is inside that CDN's published ranges.
    """
    peer = request.client.host if request.client else "unknown"
    if _is_arvancloud(peer):
        real = _valid_ip(request.headers.get("ar-real-ip", ""))
        if real:
            return real
    elif _is_cloudflare(peer):
        real = _valid_ip(request.headers.get("cf-connecting-ip", ""))
        if real:
            return real
    return peer


def _db_path() -> Path:
    return Path(os.environ.get("DATA_DIR") or Path(__file__).resolve().parent.parent / "data") / DB_NAME


def _conn() -> sqlite3.Connection:
    path = str(_db_path())
    c = _conns.get(path)
    if c is None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("CREATE TABLE IF NOT EXISTS hits (key TEXT NOT NULL, ts REAL NOT NULL)")
        c.execute("CREATE INDEX IF NOT EXISTS hits_key ON hits (key, ts)")
        c.execute("CREATE TABLE IF NOT EXISTS locks (key TEXT PRIMARY KEY, level INTEGER NOT NULL, until REAL NOT NULL)")
        _conns[path] = c
    return c


def _prune(c: sqlite3.Connection, key: str, window: float, now: float) -> None:
    c.execute("DELETE FROM hits WHERE key = ? AND ts < ?", (key, now - window))
    c.execute("DELETE FROM locks WHERE key = ? AND until < ?", (key, now - MAX_LOCK_SECONDS))


def _window_retry(c, key: str, limit: int, window: float, now: float) -> int:
    rows = [r[0] for r in c.execute("SELECT ts FROM hits WHERE key = ? ORDER BY ts", (key,))]
    if len(rows) < limit:
        return 0
    blocking = rows[len(rows) - limit]
    return max(1, math.ceil(window - (now - blocking)))


def _lock_retry(c, key: str, now: float) -> int:
    row = c.execute("SELECT until FROM locks WHERE key = ?", (key,)).fetchone()
    return max(0, math.ceil(row[0] - now)) if row else 0


def retry_after(key: str, limit: int, window: float) -> int:
    """Seconds until `key` may try again (0 when it is not limited). Never 0 while limited."""
    now = time.time()
    with _lock:
        c = _conn()
        _prune(c, key, window, now)
        return max(_window_retry(c, key, limit, window, now), _lock_retry(c, key, now))


def is_limited(key: str, limit: int, window: float) -> bool:
    return retry_after(key, limit, window) > 0


def record(key: str, window: float, limit: int | None = None) -> None:
    """Count one hit. With `limit`, reaching it starts a lockout that doubles each time."""
    now = time.time()
    with _lock:
        c = _conn()
        _prune(c, key, window, now)
        c.execute("INSERT INTO hits (key, ts) VALUES (?, ?)", (key, now))
        if limit is None:
            return
        count = c.execute("SELECT COUNT(*) FROM hits WHERE key = ?", (key,)).fetchone()[0]
        if count < limit:
            return
        row = c.execute("SELECT level FROM locks WHERE key = ?", (key,)).fetchone()
        level = (row[0] if row else 0) + 1
        until = now + min(MAX_LOCK_SECONDS, window * 2 ** (level - 1))
        c.execute("INSERT OR REPLACE INTO locks (key, level, until) VALUES (?, ?, ?)", (key, level, until))
        c.execute("DELETE FROM hits WHERE key = ?", (key,))


def lock_level(key: str) -> int:
    with _lock:
        row = _conn().execute("SELECT level FROM locks WHERE key = ?", (key,)).fetchone()
        return row[0] if row else 0


def clear(key: str) -> None:
    with _lock:
        c = _conn()
        c.execute("DELETE FROM hits WHERE key = ?", (key,))
        c.execute("DELETE FROM locks WHERE key = ?", (key,))


def close_all() -> None:
    """Drop open connections (what a process restart does); the file and its counts stay."""
    with _lock:
        for c in _conns.values():
            c.close()
        _conns.clear()


def reset_all() -> None:
    with _lock:
        c = _conn()
        c.execute("DELETE FROM hits")
        c.execute("DELETE FROM locks")
