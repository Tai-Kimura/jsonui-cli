"""A stand-in for `jui viz serve` that the browser tests run against until P1/P2 are on the branch.

It serves the view the way plan 05 §3–§4 says the real server does — `/` with the token in
`<meta name="jui-viz-token">`, `/boot.js`, `/app.css`, `/fonts/*`, `/vendor/*`, `/app.js[?mode=demo]` built by
`jui_cli.viz.bundle`, the CSP with the import map's hash — and speaks plan 04 §5 on `/ws` from a scenario file
(JSON lines; see `scenario.py`). It is NOT the server: no hooks, no state of its own beyond replaying what the
scenario says. `PROTOCOL` below lists which rows of plan 04 §5 it speaks, so the day the real server lands the two
can be compared row by row.

    python tools/viz_e2e/fake_server.py --port 7799 [--scenario path.jsonl] [--e2e] [--token T]

Prints one line `READY http://127.0.0.1:<port>` when it listens.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import pathlib
import re
import secrets
import sys
from importlib import resources

from aiohttp import WSMsgType, web

ROOT = pathlib.Path(__file__).resolve().parents[2]  # jui_tools/
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jui_cli.viz import bundle  # noqa: E402

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from scenario import Scenario  # noqa: E402

# Plan 04 §5, row by row: what this stand-in does with each message. "as plan" = the shape in the table;
# anything else says how it differs. Check this table against the real server when it lands.
PROTOCOL = {
    # server -> browser
    "hello": "as plan: {protocol: 1, serverVersion} right after the socket opens",
    "snapshot": "as plan: {rev, slices} after a good auth and on snapshot.get",
    "slices": "as plan: {rev, changed: {<slice>: [...]}} — sent when the scenario says, not on a 200ms timer",
    "events": "as plan: {items: Event[]} as the scenario says; events.more answers {items: [], older: true}",
    "ack": "as plan: {reqId, ok, error?} for perm.decide / events.more / snapshot.get / spec.sheet",
    "notice": "as plan: {level, text} when the scenario says",
    # browser -> server
    "auth": "as P1: {token}; a wrong token, or none within 2 s, closes the socket with 4401",
    "perm.decide": "as P1 until P5: acked ok=false error=\"unknown type 'perm.decide'\" (recorded in /_fake/state)",
    "events.more": "acked; no older events",
    "snapshot.get": "answered with the current snapshot",
    "presence": "recorded (/_fake/state); no answer, as P1",
    "spec.sheet": "as P1 until P4: acked ok=false error=\"unknown type 'spec.sheet'\"",
}

HOST_OK = re.compile(r"^(127\.0\.0\.1|localhost):(\d+)$")


def web_file(*parts: str):
    return resources.files("jui_cli.viz").joinpath("web", *parts)


def importmap_hash(index_html: str) -> str:
    """CSP hash of the inline import map (plan 05 §4): sha256 over the exact text between the tags."""
    m = re.search(r'<script type="importmap">(.*?)</script>', index_html, re.S)
    if not m:
        raise ValueError("index.html has no import map")
    return "sha256-" + base64.b64encode(hashlib.sha256(m.group(1).encode("utf-8")).digest()).decode()


CONTENT_TYPES = {".js": "text/javascript", ".css": "text/css", ".woff2": "font/woff2", ".txt": "text/plain",
                 ".md": "text/markdown", ".html": "text/html"}


class FakeServer:
    def __init__(self, port: int, scenario: Scenario | None, token: str, e2e: bool):
        self.port, self.scenario, self.token, self.e2e = port, scenario, token, e2e
        self.index = web_file("index.html").read_text(encoding="utf-8")
        self.csp = ("default-src 'self'; "
                    f"script-src 'self' '{importmap_hash(self.index)}'; "
                    f"connect-src 'self' ws://127.0.0.1:{port} ws://localhost:{port}; "
                    "img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; object-src 'none'; "
                    "base-uri 'none'; frame-ancestors 'none'")
        self.sockets: set[web.WebSocketResponse] = set()
        self.decisions: list[dict] = []
        self.presence: list[dict] = []
        self.rejected: list[str] = []

    # ---- HTTP ----------------------------------------------------------------------------------------------
    def headers(self, no_store: bool = False) -> dict:
        h = {"Content-Security-Policy": self.csp, "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer"}
        if no_store:
            h["Cache-Control"] = "no-store"
        return h

    @web.middleware
    async def host_guard(self, request, handler):
        m = HOST_OK.match(request.headers.get("Host", ""))
        if not m or int(m.group(2)) != self.port:
            self.rejected.append("host")
            return web.Response(status=421, text="misdirected request")
        return await handler(request)

    async def index_page(self, request):
        html = self.index.replace("__JUI_VIZ_TOKEN__", self.token)
        return web.Response(text=html, content_type="text/html", headers=self.headers(no_store=True))

    async def app_js(self, request):
        mode = "demo" if request.query.get("mode") == "demo" else "live"
        return web.Response(text=bundle.build(mode, e2e=self.e2e), content_type="text/javascript",
                            headers=self.headers(no_store=True))

    async def static(self, request):
        rel = request.match_info["path"]
        top = request.path.split("/")[1]
        parts = [top] + [p for p in rel.split("/") if p]
        if any(p in ("..", "") or p.startswith(".") for p in parts[1:]):
            raise web.HTTPNotFound()
        f = web_file(*parts)
        if not f.is_file():
            raise web.HTTPNotFound()
        ct = CONTENT_TYPES.get(pathlib.PurePosixPath(rel).suffix, "application/octet-stream")
        return web.Response(body=f.read_bytes(), content_type=ct, headers=self.headers())

    async def boot(self, request):
        return web.Response(text=web_file("boot.js").read_text(encoding="utf-8"), content_type="text/javascript",
                            headers=self.headers())

    async def css(self, request):
        return web.Response(text=web_file("app.css").read_text(encoding="utf-8"), content_type="text/css",
                            headers=self.headers())

    # ---- test controls (not part of the real server) -------------------------------------------------------
    async def fake_state(self, request):
        return web.json_response({"decisions": self.decisions, "presence": self.presence, "rejected": self.rejected,
                                  "sockets": len(self.sockets),
                                  "step": self.scenario.position if self.scenario else None})

    async def fake_step(self, request):
        """Advance the scenario to a named mark (``?to=<mark>``) or by ``?n=<steps>``."""
        if not self.scenario:
            raise web.HTTPNotFound()
        sent = await self.scenario.advance(self.broadcast, to=request.query.get("to"),
                                           n=int(request.query.get("n", "0") or 0))
        return web.json_response({"sent": sent, "step": self.scenario.position})

    # ---- WebSocket (plan 04 §5) ----------------------------------------------------------------------------
    async def broadcast(self, msg: dict):
        data = json.dumps(msg, ensure_ascii=False)
        for ws in list(self.sockets):
            try:
                await ws.send_str(data)
            except ConnectionResetError:
                self.sockets.discard(ws)

    async def ws(self, request):
        origin = request.headers.get("Origin", "")
        if origin not in (f"http://127.0.0.1:{self.port}", f"http://localhost:{self.port}"):
            self.rejected.append("origin")
            return web.Response(status=403, text="forbidden origin")
        ws = web.WebSocketResponse(heartbeat=20)
        await ws.prepare(request)
        await ws.send_json({"type": "hello", "protocol": 1, "serverVersion": "fake"})
        try:
            first = await asyncio.wait_for(ws.receive(), timeout=2.0)
        except asyncio.TimeoutError:
            self.rejected.append("auth-timeout")
            await ws.close(code=4401, message=b"auth timeout")
            return ws
        try:
            msg = json.loads(first.data) if first.type == WSMsgType.TEXT else {}
        except ValueError:
            msg = {}
        if msg.get("type") != "auth" or not secrets.compare_digest(str(msg.get("token", "")), self.token):
            self.rejected.append("auth")
            await ws.close(code=4401, message=b"auth failed")
            return ws
        self.sockets.add(ws)
        try:
            await ws.send_json(self.snapshot())
            if self.scenario:
                for item in self.scenario.backlog():
                    await ws.send_json(item)
            async for m in ws:
                if m.type != WSMsgType.TEXT:
                    continue
                try:
                    req = json.loads(m.data)
                except ValueError:
                    continue
                await self.answer(ws, req)
        finally:
            self.sockets.discard(ws)
        return ws

    def snapshot(self) -> dict:
        rev, slices = (self.scenario.state() if self.scenario else (0, {}))
        return {"type": "snapshot", "rev": rev, "slices": slices}

    async def answer(self, ws, req: dict):
        kind, rid = req.get("type"), req.get("reqId")
        if kind == "snapshot.get":
            await ws.send_json(self.snapshot())
            await ws.send_json({"type": "ack", "reqId": rid, "ok": True})
        elif kind == "perm.decide":
            self.decisions.append({k: req.get(k) for k in ("permId", "behavior", "always", "reason")})
            await ws.send_json({"type": "ack", "reqId": rid, "ok": False, "error": "unknown type 'perm.decide'"})
        elif kind == "events.more":
            await ws.send_json({"type": "events", "items": [], "older": True})
            await ws.send_json({"type": "ack", "reqId": rid, "ok": True})
        elif kind == "presence":
            self.presence.append({"visible": bool(req.get("visible"))})
        elif kind == "spec.sheet":
            await ws.send_json({"type": "ack", "reqId": rid, "ok": False, "error": "unknown type 'spec.sheet'"})

    def app(self) -> web.Application:
        app = web.Application(middlewares=[self.host_guard])
        app.router.add_get("/", self.index_page)
        app.router.add_get("/boot.js", self.boot)
        app.router.add_get("/app.css", self.css)
        app.router.add_get("/app.js", self.app_js)
        app.router.add_get("/fonts/{path:.+}", self.static)
        app.router.add_get("/vendor/{path:.+}", self.static)
        app.router.add_get("/ws", self.ws)
        app.router.add_get("/_fake/state", self.fake_state)
        app.router.add_post("/_fake/step", self.fake_step)
        return app


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--scenario", type=pathlib.Path)
    ap.add_argument("--token", default=None, help="fixed token (default: a new one each start, as the real server)")
    ap.add_argument("--e2e", action="store_true", help="append 80-dbg.js (as JUI_VIZ_E2E=1)")
    ap.add_argument("--autoplay", action="store_true", help="play the scenario by its own clock")
    a = ap.parse_args(argv)
    scenario = Scenario.load(a.scenario) if a.scenario else None
    srv = FakeServer(a.port, scenario, a.token or secrets.token_urlsafe(32), a.e2e)

    async def run():
        runner = web.AppRunner(srv.app())
        await runner.setup()
        await web.TCPSite(runner, "127.0.0.1", a.port).start()
        print(f"READY http://127.0.0.1:{a.port}", flush=True)
        if scenario and a.autoplay:
            await scenario.play(srv.broadcast)
        while True:
            await asyncio.sleep(3600)

    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
