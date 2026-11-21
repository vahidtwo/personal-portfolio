"""HTTPS_ONLY: send plain-http requests to https and add HSTS to https responses.

The scheme comes from scope["scheme"]. Behind Traefik, uvicorn's --proxy-headers sets it from
X-Forwarded-Proto, and only for clients listed in FORWARDED_ALLOW_IPS, so a visitor cannot fake it.
A request that already arrived as https (directly or via the proxy) is never redirected, so there is no loop.
/health is exempt so the container's own healthcheck works over plain http on 127.0.0.1.
"""
from __future__ import annotations

from starlette.types import ASGIApp, Receive, Scope, Send

EXEMPT_PATHS = frozenset({"/health"})


class HttpsRedirectMiddleware:
    def __init__(self, app: ASGIApp, hsts_max_age: int = 86400) -> None:
        self.app = app
        self.hsts = f"max-age={int(hsts_max_age)}".encode()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path", "") in EXEMPT_PATHS:
            await self.app(scope, receive, send)
            return
        if scope.get("scheme") != "https":
            await self._redirect(scope, send)
            return

        async def send_wrapper(message) -> None:
            if message["type"] == "http.response.start":
                headers = [h for h in message.get("headers", []) if h[0].lower() != b"strict-transport-security"]
                headers.append((b"strict-transport-security", self.hsts))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_wrapper)

    @staticmethod
    async def _redirect(scope: Scope, send: Send) -> None:
        host = ""
        for name, value in scope.get("headers", []):
            if name == b"host":
                host = value.decode("latin-1")
                break
        if not host:
            server = scope.get("server") or ("localhost", None)
            host = server[0]
        host = host.split(":", 1)[0] if not host.startswith("[") else host.split("]", 1)[0] + "]"
        path = scope.get("raw_path") or scope.get("path", "/").encode()
        if isinstance(path, bytes):
            path = path.decode("latin-1")
        query = scope.get("query_string", b"").decode("latin-1")
        location = f"https://{host}{path}" + (f"?{query}" if query else "")
        # 308 keeps the method and body (a POST stays a POST).
        await send({
            "type": "http.response.start",
            "status": 308,
            "headers": [(b"location", location.encode("latin-1")), (b"content-length", b"0"), (b"cache-control", b"no-store")],
        })
        await send({"type": "http.response.body", "body": b""})
