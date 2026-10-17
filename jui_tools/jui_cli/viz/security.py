"""The guards of the viz server: Host, Origin, the per-start token, response headers.

The server binds 127.0.0.1 only. The Host check stops DNS rebinding (a page
on another name that resolves to 127.0.0.1); the Origin check stops another
site's page from opening the WebSocket; the token, written only to a 0600
file and into the served HTML, stops other local processes and pages from
posting hook events or reading state.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from typing import Iterable

from aiohttp import web

TOKEN_HEADER = "X-Jui-Viz-Token"
LOCAL_NAMES = ("127.0.0.1", "localhost")


def make_token() -> str:
    return secrets.token_urlsafe(32)


def host_ok(host: str | None, port: int) -> bool:
    if not host:
        return False
    return host.lower() in {f"{name}:{port}" for name in LOCAL_NAMES}


def origin_ok(origin: str | None, port: int) -> bool:
    if not origin:
        return False
    return origin.lower() in {f"http://{name}:{port}" for name in LOCAL_NAMES}


def token_ok(given: str | None, expected: str) -> bool:
    if not given or not expected:
        return False
    return hmac.compare_digest(given.encode("utf-8"), expected.encode("utf-8"))


def script_hash(source: str) -> str:
    """The CSP source expression for an inline script (the importmap)."""
    digest = hashlib.sha256(source.encode("utf-8")).digest()
    return "'sha256-" + base64.b64encode(digest).decode("ascii") + "'"


def csp(port: int, script_hashes: Iterable[str] = ()) -> str:
    script_src = " ".join(["'self'", *script_hashes])
    return (
        "default-src 'self'; "
        f"script-src {script_src}; "
        f"connect-src 'self' ws://127.0.0.1:{port} ws://localhost:{port}; "
        "img-src 'self' data: blob:; "
        "style-src 'self' 'unsafe-inline'; "
        "object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
    )


def make_middleware(port: int, script_hashes: Iterable[str] = ()):
    """Refuse a foreign Host with 421 and add the security headers to every response."""
    policy = csp(port, script_hashes)

    @web.middleware
    async def guard(request: web.Request, handler):
        if not host_ok(request.headers.get("Host"), port):
            return web.Response(status=421, text="misdirected request\n")
        response = await handler(request)
        response.headers["Content-Security-Policy"] = policy
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    return guard
