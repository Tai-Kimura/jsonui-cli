"""The guards of the viz server: Host, Origin, the per-start token, response headers.

The server binds 127.0.0.1 only. What this guards against is OTHER SITES'
PAGES in the user's browser: the Host check stops DNS rebinding (a page on
another name that resolves to 127.0.0.1), the Origin check stops another
site's page from opening the WebSocket, and the token (in a 0600 file and in
the served page) is needed to post hook events or read state.

What it does NOT guard against: another process of the same user. ``GET /``
hands the token to anyone who sends a matching Host header, as
``jsonui-test mock serve`` does — a local process can read it. Anything that
must hold against local processes needs more than this module.
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


def token_ok(given, expected: str) -> bool:
    """Constant-time compare. Anything but a non-empty str is a mismatch, never an error."""
    if not isinstance(given, str) or not isinstance(expected, str) or not given or not expected:
        return False
    try:
        return hmac.compare_digest(given.encode("utf-8"), expected.encode("utf-8"))
    except UnicodeEncodeError:  # lone surrogates from a header decoded as latin-1
        return False


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


def make_middleware(port: int, script_hashes: Iterable[str] = (), on_refused=None):
    """Refuse a foreign Host with 421 before any handler runs. ``on_refused(request, response)``, when given, hears of
    each such refusal (the server logs the ones aimed at POST /api/session/end)."""

    @web.middleware
    async def guard(request: web.Request, handler):
        if not host_ok(request.headers.get("Host"), port):
            refused = web.Response(status=421, text="misdirected request\n")
            if on_refused is not None:
                on_refused(request, refused)
            return refused
        return await handler(request)

    return guard


def install_headers(app: web.Application, port: int, script_hashes: Iterable[str] = ()) -> None:
    """The security headers on EVERY response — 421, 404, 500 and raised HTTP
    errors included. A middleware only sees responses its handler returns,
    so this hooks the moment a response is prepared instead."""
    policy = csp(port, script_hashes)

    async def add(request: web.Request, response: web.StreamResponse) -> None:
        response.headers["Content-Security-Policy"] = policy
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        # Nothing is kept by the browser unless its route says otherwise: a page opened again after an update
        # once ran the new app.js with an app.css from before it (requester 10-22: the talk's tabs, 3D / コスト).
        response.headers.setdefault("Cache-Control", "no-store")

    app.on_response_prepare.append(add)
