"""PWA static routes."""

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.web import BASE_DIR

router = APIRouter()

_APK_PATH = BASE_DIR / "static" / "my-inventory.apk"

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
    return FileResponse(
        BASE_DIR / "static" / "sw.js",
        media_type="application/javascript",
        headers={"Cache-Control": "no-cache"},
    )


@router.get("/offline.html")
def offline_page():
    return FileResponse(
        BASE_DIR / "static" / "offline.html",
        media_type="text/html",
    )
