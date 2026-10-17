"""jui viz guards: Host, Origin, token, CSP (jui_cli/viz/security.py)."""
from __future__ import annotations

import asyncio

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from jui_cli.viz import security

PORT = 7788


def test_host_accepts_only_the_two_local_names_on_our_port():
    assert security.host_ok("127.0.0.1:7788", PORT)
    assert security.host_ok("localhost:7788", PORT)
    assert security.host_ok("LOCALHOST:7788", PORT)
    # The boundary on each side: right name wrong port, right port wrong name,
    # a name that merely starts with ours, no port, nothing.
    assert not security.host_ok("127.0.0.1:7789", PORT)
    assert not security.host_ok("example.com:7788", PORT)
    assert not security.host_ok("localhost.example.com:7788", PORT)
    assert not security.host_ok("127.0.0.1", PORT)
    assert not security.host_ok(None, PORT)
    assert not security.host_ok("", PORT)


def test_origin_accepts_only_http_on_the_local_names_and_our_port():
    assert security.origin_ok("http://127.0.0.1:7788", PORT)
    assert security.origin_ok("http://localhost:7788", PORT)
    assert not security.origin_ok("https://127.0.0.1:7788", PORT)
    assert not security.origin_ok("http://127.0.0.1:7789", PORT)
    assert not security.origin_ok("http://evil.example", PORT)
    assert not security.origin_ok("null", PORT)
    assert not security.origin_ok(None, PORT)


def test_token_compare_needs_an_exact_non_empty_match():
    token = security.make_token()
    assert len(token) >= 40
    assert security.make_token() != token
    assert security.token_ok(token, token)
    assert not security.token_ok(token[:-1], token)
    assert not security.token_ok(token + "x", token)
    assert not security.token_ok("", token)
    assert not security.token_ok(None, token)
    assert not security.token_ok("", "")  # an unset token never matches


def test_csp_names_our_port_and_the_given_script_hashes_only():
    h = security.script_hash('{"imports":{}}')
    assert h.startswith("'sha256-") and h.endswith("'")
    policy = security.csp(PORT, [h])
    assert f"script-src 'self' {h};" in policy
    assert "ws://127.0.0.1:7788" in policy and "ws://localhost:7788" in policy
    assert "frame-ancestors 'none'" in policy and "object-src 'none'" in policy
    assert "'unsafe-inline'" not in policy.split("script-src", 1)[1].split(";", 1)[0]


def _run(coro):
    return asyncio.run(coro)


def test_middleware_answers_421_to_a_foreign_host_and_sets_headers_otherwise():
    async def main():
        app = web.Application(middlewares=[security.make_middleware(PORT)])
        async def ok(request):
            return web.Response(text="ok")

        app.router.add_get("/", ok)
        async with TestClient(TestServer(app)) as client:
            bad = await client.get("/", headers={"Host": "example.com:7788"})
            assert bad.status == 421
            good = await client.get("/", headers={"Host": "127.0.0.1:7788"})
            assert good.status == 200
            assert good.headers["X-Content-Type-Options"] == "nosniff"
            assert good.headers["Referrer-Policy"] == "no-referrer"
            assert "default-src 'self'" in good.headers["Content-Security-Policy"]
            assert "Access-Control-Allow-Origin" not in good.headers

    _run(main())
