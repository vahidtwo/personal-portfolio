"""Firebase options for the Android app, found with the server's service account.

The app reads them from /api/push/config, so the APK needs no google-services.json. Order:
FIREBASE_ANDROID_APP_ID (env override) > memory > the JSON cache in DATA_DIR > the Firebase Management API
(list the project's Android apps, create `app.myinventory` when missing). Resolution runs in one background
thread with retries; requests never wait for it and get `android: null` until it is done.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any

import app.config as config

logger = logging.getLogger(__name__)

PACKAGE_NAME = "app.myinventory"
DISPLAY_NAME = "daraiito"
API = "https://firebase.googleapis.com/v1beta1"
SCOPES = ("https://www.googleapis.com/auth/firebase",)
CACHE_FILE = "firebase_android.json"
FIRST_RETRY_SECONDS = 60
RETRY_SECONDS = 10 * 60
OPERATION_POLL_SECONDS = 2
OPERATION_TIMEOUT_SECONDS = 120
HTTP_TIMEOUT_SECONDS = 20

_lock = threading.Lock()
_cached: dict[str, str] | None = None
_cache_loaded = False
_thread: threading.Thread | None = None
_stop = threading.Event()


class ResolveError(RuntimeError):
    """A Management API call failed; the message carries Google's error as returned."""


def _cache_path() -> Path:
    return Path(os.environ.get("DATA_DIR") or config.DATA_DIR) / CACHE_FILE


def _project() -> tuple[str, str]:
    return (config.FIREBASE_PROJECT_ID or "").strip(), (config.FIREBASE_MESSAGING_SENDER_ID or "").strip()


def _valid(entry: Any) -> dict[str, str] | None:
    """A cached entry is used only for the configured project and a matching Android app ID."""
    if not isinstance(entry, dict):
        return None
    project_id, sender_id = _project()
    app_id = str(entry.get("appId") or "")
    api_key = str(entry.get("apiKey") or "")
    if not project_id or not sender_id or not api_key:
        return None
    if entry.get("projectId") != project_id or entry.get("senderId") != sender_id:
        return None
    if not config.ANDROID_APP_ID_RE.match(app_id) or app_id.split(":")[1] != sender_id:
        return None
    return {"appId": app_id, "apiKey": api_key, "projectId": project_id, "senderId": sender_id}


def _read_cache_file() -> dict[str, str] | None:
    path = _cache_path()
    try:
        return _valid(json.loads(path.read_text(encoding="utf-8")))
    except FileNotFoundError:
        return None
    except Exception as exc:
        logger.warning("Ignoring unreadable %s: %s", path.name, exc)
        return None


def _write_cache_file(entry: dict[str, str], key_source: str) -> None:
    path = _cache_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({**entry, "packageName": PACKAGE_NAME, "keySource": key_source}), encoding="utf-8")
        os.replace(tmp, path)
    except OSError as exc:
        logger.warning("Could not save %s (kept in memory only): %s", path.name, exc)


def cached_android_config() -> dict[str, str] | None:
    """Never touches the network: memory, else the cache file (read once)."""
    global _cached, _cache_loaded
    with _lock:
        if _cached is None and not _cache_loaded:
            _cached = _read_cache_file()
            _cache_loaded = True
        return _valid(_cached)


def android_push_config() -> dict[str, str] | None:
    """What /api/push/config serves as `android`: the env override, else whatever is already resolved."""
    if (config.FIREBASE_ANDROID_APP_ID or "").strip():
        return config.firebase_android_config()
    return cached_android_config()


def _remember(entry: dict[str, str], key_source: str) -> None:
    global _cached, _cache_loaded
    with _lock:
        _cached = entry
        _cache_loaded = True
    _write_cache_file(entry, key_source)


def reset_for_tests() -> None:
    global _cached, _cache_loaded, _thread
    stop_background_resolution()
    with _lock:
        _cached = None
        _cache_loaded = False
        _thread = None
    _stop.clear()


# ---- Management API ----------------------------------------------------------------------------------

def _session():
    from google.auth.transport.requests import AuthorizedSession
    from google.oauth2 import service_account

    from app.firebase_push import _service_account_dict

    creds = service_account.Credentials.from_service_account_info(_service_account_dict(), scopes=list(SCOPES))
    return AuthorizedSession(creds)


def _json(response, what: str) -> dict:
    try:
        body = response.json()
    except Exception:
        body = {"raw": (getattr(response, "text", "") or "")[:500]}
    if response.status_code >= 400:
        raise ResolveError(f"{what}: HTTP {response.status_code} {json.dumps(body.get('error', body), ensure_ascii=False)}")
    return body


def _find_app(session, project_id: str) -> str | None:
    page = None
    while True:
        params = {"pageSize": 100, **({"pageToken": page} if page else {})}
        body = _json(session.get(f"{API}/projects/{project_id}/androidApps", params=params,
                                 timeout=HTTP_TIMEOUT_SECONDS), "androidApps.list")
        for item in body.get("apps", []):
            if item.get("packageName") == PACKAGE_NAME and item.get("state", "ACTIVE") == "ACTIVE":
                return item.get("appId")
        page = body.get("nextPageToken")
        if not page:
            return None


def _create_app(session, project_id: str, sleep=time.sleep) -> str:
    op = _json(session.post(f"{API}/projects/{project_id}/androidApps",
                            json={"packageName": PACKAGE_NAME, "displayName": DISPLAY_NAME},
                            timeout=HTTP_TIMEOUT_SECONDS), "androidApps.create")
    logger.info("Created Firebase Android app %s; waiting for operation %s", PACKAGE_NAME, op.get("name"))
    deadline = time.monotonic() + OPERATION_TIMEOUT_SECONDS
    while not op.get("done"):
        if time.monotonic() > deadline:
            raise ResolveError(f"androidApps.create: operation {op.get('name')} not done in time")
        sleep(OPERATION_POLL_SECONDS)
        op = _json(session.get(f"{API}/{op['name']}", timeout=HTTP_TIMEOUT_SECONDS), "operations.get")
    if op.get("error"):
        raise ResolveError(f"androidApps.create: {json.dumps(op['error'], ensure_ascii=False)}")
    app_id = (op.get("response") or {}).get("appId")
    if not app_id:
        raise ResolveError("androidApps.create: operation finished without an appId")
    return app_id


def _config_api_key(session, project_id: str, app_id: str) -> str | None:
    body = _json(session.get(f"{API}/projects/{project_id}/androidApps/{app_id}/config",
                             timeout=HTTP_TIMEOUT_SECONDS), "androidApps.getConfig")
    contents = json.loads(base64.b64decode(body.get("configFileContents") or b"").decode("utf-8") or "{}")
    for client in contents.get("client", []):
        info = client.get("client_info", {})
        if info.get("mobilesdk_app_id") != app_id and (
            info.get("android_client_info", {}).get("package_name") != PACKAGE_NAME
        ):
            continue
        for key in client.get("api_key", []):
            if key.get("current_key"):
                return key["current_key"]
    return None


def resolve_once(session_factory=None, sleep=time.sleep) -> dict[str, str] | None:
    """One full attempt. Returns the options, or raises ResolveError / FirebaseAdminConfigError."""
    project_id, sender_id = _project()
    if not project_id or not sender_id:
        raise ResolveError("FIREBASE_PROJECT_ID or FIREBASE_MESSAGING_SENDER_ID is not set")
    session = (session_factory or _session)()
    app_id = _find_app(session, project_id) or _create_app(session, project_id, sleep=sleep)
    key_source = "FIREBASE_ANDROID_API_KEY"
    api_key = (config.FIREBASE_ANDROID_API_KEY or "").strip()
    if not api_key:
        try:
            api_key = _config_api_key(session, project_id, app_id) or ""
            key_source = "androidApps.getConfig"
        except ResolveError as exc:
            logger.warning("%s", exc)
    if not api_key:
        api_key = (config.FIREBASE_API_KEY or "").strip()
        key_source = "FIREBASE_API_KEY"
        logger.warning(
            "Android push uses the web API key (FIREBASE_API_KEY); its restrictions were not checked. "
            "If the app reports token-failed, allow Android apps or set FIREBASE_ANDROID_API_KEY."
        )
    entry = _valid({"appId": app_id, "apiKey": api_key, "projectId": project_id, "senderId": sender_id})
    if entry is None:
        raise ResolveError(f"resolved Android app ID {app_id!r} does not match sender {sender_id}")
    _remember(entry, key_source)
    logger.info("Firebase Android app %s resolved: %s (key from %s)", PACKAGE_NAME, app_id, key_source)
    return entry


def _admin_env_complete() -> bool:
    return all(
        (getattr(config, name) or "").strip()
        for name in ("FIREBASE_PROJECT_ID", "FIREBASE_MESSAGING_SENDER_ID", "FIREBASE_CLIENT_EMAIL", "FIREBASE_PRIVATE_KEY")
    )


def _loop(session_factory, first_retry: float, retry: float) -> None:
    wait = first_retry
    while not _stop.is_set():
        if android_push_config() is not None:
            return
        try:
            resolve_once(session_factory)
            return
        except Exception as exc:
            logger.error("Firebase Android app resolution failed (retry in %ds): %s", int(wait), exc)
        if _stop.wait(wait):
            return
        wait = retry


def start_background_resolution(session_factory=None, *, first_retry: float = FIRST_RETRY_SECONDS,
                                retry: float = RETRY_SECONDS) -> bool:
    """Start the resolver thread unless it is running or nothing is needed. Never blocks."""
    global _thread
    if (config.FIREBASE_ANDROID_APP_ID or "").strip() or not _admin_env_complete():
        return False
    if cached_android_config() is not None:
        return False
    with _lock:
        if _thread is not None and _thread.is_alive():
            return False
        _stop.clear()
        _thread = threading.Thread(target=_loop, args=(session_factory, first_retry, retry),
                                   name="firebase-android-resolve", daemon=True)
        _thread.start()
    return True


def stop_background_resolution() -> None:
    _stop.set()
    t = _thread
    if t is not None and t.is_alive() and t is not threading.current_thread():
        t.join(timeout=2)
