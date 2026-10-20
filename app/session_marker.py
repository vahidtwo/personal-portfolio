"""A readable "signed in" marker next to the HttpOnly session cookie (batch 1, offline privacy).

The service worker cannot see the HttpOnly session cookie, so offline it could not tell whether a
session still exists. This marker holds no secret (just «1»), has the same lifetime as the session
cookie and is refreshed and removed together with it: set on every response that has a signed-in
session, deleted on any response without one (logout, expired or tampered session). The service
worker serves the offline dashboard only while this marker is present.
"""
from http.cookies import SimpleCookie

from starlette.types import ASGIApp, Message, Receive, Scope, Send

MARKER_COOKIE = "inventory_signed_in"


class SessionMarkerMiddleware:
    """Must sit inside SessionMiddleware (added before it), so scope["session"] is final at send time."""

    def __init__(self, app: ASGIApp, max_age: int, https_only: bool = False) -> None:
        self.app = app
        self.max_age = max_age
        self.https_only = https_only

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        if path.startswith("/static/") or path.endswith(".apk"):
            await self.app(scope, receive, send)
            return
        had_marker = False
        for name, value in scope.get("headers", []):
            if name == b"cookie" and MARKER_COOKIE.encode() in value:
                had_marker = True

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                session = scope.get("session") or {}
                signed_in = bool(session.get("user_id"))
                cookie = SimpleCookie()
                if signed_in:
                    cookie[MARKER_COOKIE] = "1"
                    cookie[MARKER_COOKIE]["max-age"] = self.max_age
                elif had_marker:
                    cookie[MARKER_COOKIE] = ""
                    cookie[MARKER_COOKIE]["max-age"] = 0
                    cookie[MARKER_COOKIE]["expires"] = "Thu, 01 Jan 1970 00:00:00 GMT"
                if MARKER_COOKIE in cookie:
                    morsel = cookie[MARKER_COOKIE]
                    morsel["path"] = "/"
                    morsel["samesite"] = "Lax"
                    if self.https_only:
                        morsel["secure"] = True
                    headers = list(message.get("headers", []))
                    headers.append((b"set-cookie", morsel.OutputString().encode("latin-1")))
                    message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_wrapper)
