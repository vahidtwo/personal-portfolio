"""Gzip only for static CSS and JS (batch 1, Gorg's call).

HTML is never compressed here (it carries a CSRF token next to user input: BREACH), and the APK
or any other file is passed through untouched so its size and sha256 never change.
"""
from starlette.middleware.gzip import GZipMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

GZIP_SUFFIXES = (".css", ".js")


def should_gzip(path: str) -> bool:
    return path.startswith("/static/") and path.endswith(GZIP_SUFFIXES)


class StaticGZipMiddleware:
    def __init__(self, app: ASGIApp, minimum_size: int = 1000) -> None:
        self.app = app
        self.gzip = GZipMiddleware(app, minimum_size=minimum_size)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and should_gzip(scope.get("path", "")):
            await self.gzip(scope, receive, send)
            return
        await self.app(scope, receive, send)
