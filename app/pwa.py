"""PWA static routes."""

from fastapi import APIRouter
from fastapi.responses import FileResponse

from app.web import BASE_DIR

router = APIRouter()

@router.get("/manifest.webmanifest")
def web_manifest():
    return FileResponse(
        BASE_DIR / "static" / "manifest.webmanifest",
        media_type="application/manifest+json",
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
