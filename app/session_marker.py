"""A readable "signed in" marker (always «1»; v11 adds a per-user page key cookie) next to the HttpOnly session cookie (batch 1, offline privacy).

The service worker cannot see the HttpOnly session cookie, so offline it could not tell whether a
session still exists. This marker holds no secret (just «1»), has the same lifetime as the session
cookie and is refreshed and removed together with it: set on every response that has a signed-in
session, deleted on any response without one (logout, expired or tampered session). The service
worker serves the offline dashboard only while this marker is present.
"""
import base64
import hashlib
import hmac
from http.cookies import SimpleCookie

from starlette.types import ASGIApp, Message, Receive, Scope, Send

MARKER_COOKIE = "inventory_signed_in"
# v11: separate readable per-user page-cache key. inventory_signed_in stays exactly "1": the installed
# v10/v11 Android SMS sender (ServerAddress.hasSignedInSession) requires that value.
PAGE_KEY_COOKIE = "inventory_page_key"


def marker_value(secret: str, user_id) -> str:
    """v11: non-secret per-user id ("u" + 22 chars of HMAC-SHA256(secret, user id)).

    The service worker names its cached-page store after it, so a cached dashboard is never shown to another
    account. It reveals nothing about the user id and cannot be forged into a session (the session cookie is
    separate, HttpOnly and signed)."""
    digest = hmac.new(secret.encode(), f"page-cache:{user_id}".encode(), hashlib.sha256).digest()
    return "u" + base64.urlsafe_b64encode(digest).decode().rstrip("=")[:22]


class SessionMarkerMiddleware:
    """Must sit inside SessionMiddleware (added before it), so scope["session"] is final at send time."""

    def __init__(self, app: ASGIApp, max_age: int, https_only: bool = False, secret_key: str = "") -> None:
        self.app = app
        self.secret_key = secret_key
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
            if name == b"cookie" and (MARKER_COOKIE.encode() in value or PAGE_KEY_COOKIE.encode() in value):
                had_marker = True

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                session = scope.get("session") or {}
                user_id = session.get("user_id")
                cookie = SimpleCookie()
                if user_id:
                    cookie[MARKER_COOKIE] = "1"
                    cookie[PAGE_KEY_COOKIE] = marker_value(self.secret_key, user_id)
                    for name in (MARKER_COOKIE, PAGE_KEY_COOKIE):
                        cookie[name]["max-age"] = self.max_age
                elif had_marker:
                    for name in (MARKER_COOKIE, PAGE_KEY_COOKIE):
                        cookie[name] = ""
                        cookie[name]["max-age"] = 0
                        cookie[name]["expires"] = "Thu, 01 Jan 1970 00:00:00 GMT"
                headers = list(message.get("headers", []))
                for name in (MARKER_COOKIE, PAGE_KEY_COOKIE):
                    if name in cookie:
                        morsel = cookie[name]
                        morsel["path"] = "/"
                        morsel["samesite"] = "Lax"
                        if self.https_only:
                            morsel["secure"] = True
                        headers.append((b"set-cookie", morsel.OutputString().encode("latin-1")))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_wrapper)
