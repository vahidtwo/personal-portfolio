"""PWA static routes."""

import hashlib
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response

from app.firebase_push import service_worker_firebase_snippet
from app.web import BASE_DIR

from app.config import STATIC_ASSET_VERSION

router = APIRouter()

_APK_PATH = BASE_DIR / "static" / "my-inventory.apk"
# Single source of truth for the Android release shown to the app's update notice.
# Keep versionCode/versionName in sync with android/app/build.gradle.kts (a test checks it).
_RELEASE_PATH = BASE_DIR / "android_release.json"
_APK_DOWNLOAD_URL = "/download/my-inventory.apk"
_sha_cache: dict[str, object] = {}


def _apk_sha256_cached() -> str | None:
    if not _APK_PATH.is_file():
        return None
    stat = _APK_PATH.stat()
    key = (stat.st_mtime_ns, stat.st_size)
    if _sha_cache.get("key") != key:
        digest = hashlib.sha256()
        with _APK_PATH.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        _sha_cache["key"] = key
        _sha_cache["sha256"] = digest.hexdigest()
    return _sha_cache["sha256"]  # type: ignore[return-value]


@router.get("/api/app-version")
def android_app_version():
    """Public: latest Android build, used by the app's «نسخهٔ تازه رسید» notice."""
    try:
        release = json.loads(_RELEASE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise HTTPException(status_code=404, detail="اطلاعات نسخه در دسترس نیست")
    return JSONResponse(
        {
            "versionCode": int(release["versionCode"]),
            "versionName": str(release["versionName"]),
            "url": _APK_DOWNLOAD_URL,
            "sha256": _apk_sha256_cached(),
            "notes": [str(n) for n in release.get("notes", [])],
            # Parsed by the app but ignored for now: forced updates aren't approved.
            "min_required": int(release.get("min_required", 0) or 0),
        },
        headers={"Cache-Control": "no-cache"},
    )

@router.get("/manifest.webmanifest")
def web_manifest():
    return FileResponse(
        BASE_DIR / "static" / "manifest.webmanifest",
        media_type="application/manifest+json",
        headers={"Cache-Control": "no-cache"},
    )


@router.get("/download/my-inventory.apk")
def download_android_apk():
    if not _APK_PATH.is_file():
        raise HTTPException(status_code=404, detail="فایل نصب در دسترس نیست")
    return FileResponse(
        _APK_PATH,
        media_type="application/vnd.android.package-archive",
        filename="my-inventory.apk",
        headers={"Cache-Control": "no-store"},
    )


@router.get("/sw.js")
def service_worker():
    body = (BASE_DIR / "static" / "sw.js").read_text(encoding="utf-8")
    body = body.replace("__STATIC_ASSET_VERSION__", STATIC_ASSET_VERSION)
    body += service_worker_firebase_snippet()
    return Response(
        content=body,
        media_type="application/javascript",
        headers={"Cache-Control": "no-cache"},
    )


@router.get("/offline.html")
def offline_page():
    return FileResponse(
        BASE_DIR / "static" / "offline.html",
        media_type="text/html",
    )
