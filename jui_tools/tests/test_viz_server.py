"""jui viz server routes and the WebSocket protocol (jui_cli/viz/server.py)."""
from __future__ import annotations

import asyncio
import io
import json
import socket

import aiohttp
from aiohttp.test_utils import TestClient, TestServer

from jui_cli.viz.config import VizConfig
from jui_cli.viz.server import MAX_HOOK_BODY, ServerContext, make_app
from jui_cli.viz.state import VizState

TOKEN = "t" * 43


def _ctx(**kw) -> ServerContext:
    config = VizConfig(pushIntervalMs=20)
    return ServerContext(config=config, port=0, token=TOKEN, version="test", state=VizState(50), **kw)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def _client(ctx: ServerContext) -> TestClient:
    # make_app puts the port into the Host / CSP checks, so it is chosen first.
    ctx.port = _free_port()
    client = TestClient(TestServer(make_app(ctx), host="127.0.0.1", port=ctx.port))
    await client.start_server()
    return client


def _host(ctx):
    return {"Host": f"127.0.0.1:{ctx.port}"}


def _run(coro):
    return asyncio.run(coro)


def test_page_carries_the_token_in_its_meta_and_is_not_cached():
    async def main():
        ctx = _ctx()
        client = await _client(ctx)
        try:
            res = await client.get("/", headers=_host(ctx))
            body = await res.text()
            assert res.status == 200
            assert f'<meta name="jui-viz-token" content="{TOKEN}">' in body
            assert "__JUI_VIZ_TOKEN__" not in body
            assert res.headers["Cache-Control"] == "no-store"
            dbg = await client.get("/debug", headers=_host(ctx))
            assert dbg.status == 200 and TOKEN in await dbg.text()
        finally:
            await client.close()

    _run(main())


def test_health_has_no_secret():
    async def main():
        ctx = _ctx()
        client = await _client(ctx)
        try:
            res = await client.get("/health", headers=_host(ctx))
            data = await res.json()
            assert data["ok"] is True and data["version"] == "test"
            assert TOKEN not in json.dumps(data)
        finally:
            await client.close()

    _run(main())


def test_hook_needs_the_token_refuses_a_browser_origin_and_hands_the_payload_on():
    async def main():
        got = []
        ctx = _ctx(on_hook=got.append)
        client = await _client(ctx)
        try:
            payload = json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Read"})
            assert (await client.post("/hook", data=payload, headers=_host(ctx))).status == 401
            wrong = {**_host(ctx), "X-Jui-Viz-Token": TOKEN[:-1] + "x"}
            assert (await client.post("/hook", data=payload, headers=wrong)).status == 401
            with_origin = {**_host(ctx), "X-Jui-Viz-Token": TOKEN, "Origin": f"http://127.0.0.1:{ctx.port}"}
            assert (await client.post("/hook", data=payload, headers=with_origin)).status == 403
            ok = {**_host(ctx), "X-Jui-Viz-Token": TOKEN}
            assert (await client.post("/hook", data="not json", headers=ok)).status == 400
            assert (await client.post("/hook", data="[1]", headers=ok)).status == 400
            assert got == []
            res = await client.post("/hook", data=payload, headers=ok)
            assert res.status == 204
            await asyncio.sleep(0.05)
            assert got == [{"hook_event_name": "PreToolUse", "tool_name": "Read"}]
        finally:
            await client.close()

    _run(main())


def test_hook_body_over_the_limit_is_refused():
    async def main():
        got = []
        ctx = _ctx(on_hook=got.append)
        client = await _client(ctx)
        try:
            ok = {**_host(ctx), "X-Jui-Viz-Token": TOKEN}
            big = b'{"x":"' + b"a" * MAX_HOOK_BODY + b'"}'
            res = await client.post("/hook", data=io.BytesIO(big), headers=ok)
            assert res.status == 413
            # The boundary's other side: just under the limit is accepted.
            fits = b'{"x":"' + b"a" * (MAX_HOOK_BODY - 16) + b'"}'
            assert (await client.post("/hook", data=io.BytesIO(fits), headers=ok)).status == 204
        finally:
            await client.close()

    _run(main())


def test_api_snapshot_needs_the_token():
    async def main():
        ctx = _ctx()
        client = await _client(ctx)
        try:
            assert (await client.get("/api/snapshot", headers=_host(ctx))).status == 401
            res = await client.get("/api/snapshot", headers={**_host(ctx), "X-Jui-Viz-Token": TOKEN})
            data = await res.json()
            assert res.status == 200 and "slices" in data and "rev" in data
        finally:
            await client.close()

    _run(main())


def test_static_serves_web_files_and_refuses_paths_out_of_it():
    async def main():
        ctx = _ctx()
        client = await _client(ctx)
        try:
            res = await client.get("/debug.js", headers=_host(ctx))
            assert res.status == 200 and "javascript" in res.headers["Content-Type"]
            for path in ("/../server.py", "/%2e%2e/server.py", "/.hidden", "/nope.js", "/debug.html",
                         "/vendor/../server.py", "/vendor/.x/a.js", "/a/./b.js"):
                assert (await client.get(path, headers=_host(ctx))).status == 404, path
        finally:
            await client.close()

    _run(main())


def test_static_reaches_a_folder_with_a_dot_in_its_name(tmp_path, monkeypatch):
    """vendor/three-0.160.0/ was refused by a pattern that allowed no dot in
    folder names, and the page could not load three.js (d2, 10-18)."""
    from jui_cli.viz import server as srv

    web = tmp_path / "web"
    (web / "vendor" / "three-0.160.0" / "addons").mkdir(parents=True)
    (web / "vendor" / "three-0.160.0" / "three.module.min.js").write_text("export {};")
    (web / "vendor" / "three-0.160.0" / "addons" / "x.js").write_text("export {};")
    (web / "debug.html").write_text("<meta name=\"jui-viz-token\" content=\"__JUI_VIZ_TOKEN__\">")
    monkeypatch.setattr(srv, "web_root", lambda: web)

    async def main():
        ctx = _ctx()
        client = await _client(ctx)
        try:
            for path in ("/vendor/three-0.160.0/three.module.min.js", "/vendor/three-0.160.0/addons/x.js"):
                res = await client.get(path, headers=_host(ctx))
                assert res.status == 200 and "javascript" in res.headers["Content-Type"], path
        finally:
            await client.close()

    _run(main())


def _ws_headers(ctx, origin=None):
    return {**_host(ctx), "Origin": origin or f"http://127.0.0.1:{ctx.port}"}


def test_ws_refuses_a_foreign_origin_before_upgrading():
    async def main():
        ctx = _ctx()
        client = await _client(ctx)
        try:
            try:
                await client.ws_connect("/ws", headers=_ws_headers(ctx, "http://evil.example"))
                raise AssertionError("connected with a foreign Origin")
            except aiohttp.WSServerHandshakeError as exc:
                assert exc.status == 403
        finally:
            await client.close()

    _run(main())


def test_ws_says_hello_then_needs_auth_then_sends_snapshot_and_pushes_changes():
    async def main():
        ctx = _ctx()
        ctx.state.add_event({"kind": "SessionStart", "text": "before"})
        client = await _client(ctx)
        try:
            ws = await client.ws_connect("/ws", headers=_ws_headers(ctx))
            hello = await ws.receive_json(timeout=2)
            assert hello == {"type": "hello", "protocol": 1, "serverVersion": "test"}
            await ws.send_json({"type": "auth", "token": TOKEN})
            snap = await ws.receive_json(timeout=2)
            assert snap["type"] == "snapshot" and "sessions" in snap["slices"]
            events = await ws.receive_json(timeout=2)
            assert events["type"] == "events" and [e["text"] for e in events["items"]] == ["before"]

            ctx.state.set_slice("sessions", [{"id": "s1"}])
            ctx.state.add_event({"kind": "PreToolUse", "text": "after"})
            pushed = await ws.receive_json(timeout=2)
            assert pushed["type"] == "slices" and pushed["changed"] == {"sessions": [{"id": "s1"}]}
            assert pushed["rev"] == ctx.state.rev
            more = await ws.receive_json(timeout=2)
            assert more["type"] == "events" and [e["text"] for e in more["items"]] == ["after"]

            # Nothing changed: the loop stays quiet.
            try:
                extra = await ws.receive_json(timeout=0.2)
                raise AssertionError(f"pushed without a change: {extra}")
            except asyncio.TimeoutError:
                pass

            await ws.send_json({"type": "events.more", "reqId": 7, "beforeSeq": 2, "limit": 10})
            older = await ws.receive_json(timeout=2)
            assert older["older"] is True and [e["seq"] for e in older["items"]] == [1]
            ack = await ws.receive_json(timeout=2)
            assert ack == {"type": "ack", "reqId": 7, "ok": True}
            await ws.close()
        finally:
            await client.close()

    _run(main())


def test_ws_closes_on_a_wrong_token_and_when_auth_does_not_come():
    async def main():
        ctx = _ctx()
        client = await _client(ctx)
        try:
            ws = await client.ws_connect("/ws", headers=_ws_headers(ctx))
            await ws.receive_json(timeout=2)
            await ws.send_json({"type": "auth", "token": "wrong"})
            msg = await ws.receive(timeout=2)
            assert msg.type == aiohttp.WSMsgType.CLOSE and ws.close_code == 4401
            assert ctx.sockets == {}

            for odd in (123, [TOKEN], None):
                ws_odd = await client.ws_connect("/ws", headers=_ws_headers(ctx))
                await ws_odd.receive_json(timeout=2)
                await ws_odd.send_json({"type": "auth", "token": odd})
                msg = await ws_odd.receive(timeout=2)
                assert msg.type == aiohttp.WSMsgType.CLOSE and ws_odd.close_code == 4401, odd

            ws2 = await client.ws_connect("/ws", headers=_ws_headers(ctx))
            await ws2.receive_json(timeout=2)
            msg = await ws2.receive(timeout=4)  # the server waits 2 s for auth
            assert msg.type == aiohttp.WSMsgType.CLOSE and ws2.close_code == 4401
        finally:
            await client.close()

    _run(main())
