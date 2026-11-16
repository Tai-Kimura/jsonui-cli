"""The Slack intake's Socket Mode (viz/slack/socket_mode.py) against a fake Socket Mode server on 127.0.0.1:
apps.connections.open -> a WebSocket that says hello, sends events_api envelopes and disconnects. Nothing here
reaches Slack, an API or claude."""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import pytest
from aiohttp import WSMsgType, web

from jui_cli.viz.slack import config as C
from jui_cli.viz.slack import fetch as FE
from jui_cli.viz.slack import intake as I
from jui_cli.viz.slack import socket_mode as SM
from jui_cli.viz.slack import store as S

APP = "".join(["xa", "pp-1-QQ5"])
FAST = (0.05, 0.1, 0.2)


@pytest.fixture(autouse=True)
def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("JUI_VIZ_HOME", raising=False)
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)


def cfg_of(tmp_path, **over) -> dict:
    cfg = C._merge(C.DEFAULT, {
        "orchestrationDir": str(tmp_path / "orch"),
        "source": {"mode": "socket",
                   "workspaces": [{"name": "acme", "token": "slk-tok-QQ7", "appToken": APP, "channels": ["C0123"]}]},
        "router": {"anthropicApiKey": "ant-key-QQ8", "prompt": {"projects": {"shop": "the shop", "booking": "booking"}}},
    })
    return C._merge(cfg, over)


def msg(ts: str, channel: str = "C0123", **kw) -> dict:
    return {"type": "message", "channel": channel, "channel_type": "channel", "user": "U1", "text": "x", "ts": ts, **kw}


def env(eid: str, event: dict, kind: str = "events_api") -> dict:
    return {"envelope_id": eid, "type": kind, "accepts_response_payload": False,
            "payload": {"team_id": "T1", "event": event}}


class FakeSocketSlack:
    """scripts: one list per connection, sent after hello. A dict is sent (and, with an envelope_id, its ack is
    awaited before the next); a callable is waited for (until it returns true) before the next item; "drop" closes
    the socket without a word; the end of a script holds it open."""

    def __init__(self, scripts, open_answers=()):
        self.scripts, self.open_answers = list(scripts), list(open_answers)
        self.opens, self.auth, self.acks, self.connections = 0, [], [], 0
        self.order: list[str] = []
        self.port = 0
        self.runner: web.AppRunner | None = None

    async def start(self) -> str:
        app = web.Application()
        app.router.add_post("/api/apps.connections.open", self.open)
        app.router.add_get("/link", self.link)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "127.0.0.1", 0)
        await site.start()
        self.port = site._server.sockets[0].getsockname()[1]
        return f"http://127.0.0.1:{self.port}/api/"

    async def stop(self) -> None:
        await self.runner.cleanup()

    async def open(self, request):
        self.opens += 1
        self.auth.append(request.headers.get("Authorization"))
        if self.open_answers:
            answer = self.open_answers.pop(0)
            if answer is not None:
                return web.json_response(answer)
        return web.json_response({"ok": True, "url": f"ws://127.0.0.1:{self.port}/link?c={self.opens}"})

    async def link(self, request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self.connections += 1
        script = self.scripts.pop(0) if self.scripts else []
        await ws.send_json({"type": "hello", "num_connections": 1})
        for item in script:
            if item == "drop":
                await ws.close()
                return ws
            if callable(item):
                assert await until(item), "the script's wait"
                continue
            await ws.send_json(item)
            self.order.append(f"sent {item.get('envelope_id') or item.get('type')}")
            if item.get("envelope_id"):
                got = await ws.receive(timeout=5)
                assert got.type == WSMsgType.TEXT
                self.acks.append(json.loads(got.data))
                self.order.append(f"ack {self.acks[-1].get('envelope_id')}")
        async for _ in ws:     # held open (or, after a disconnect, until the client goes)
            pass
        return ws


async def until(cond, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        await asyncio.sleep(0.02)
    return False


def run_client(server: FakeSocketSlack, workspace: dict, check, *, timeout=5.0, slow_handler=0.0):
    got: list[tuple[str, dict]] = []

    async def on_message(name, event):
        if slow_handler:
            await asyncio.sleep(slow_handler)
        got.append((name, event))

    async def go():
        base = await server.start()
        client = SM.Client(workspace, on_message, api_base=base, backoff=FAST)
        task = asyncio.create_task(client.run())
        try:
            ok = await until(lambda: check(client, got), timeout)
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            await server.stop()
        return ok, client

    ok, client = asyncio.run(go())
    return ok, client, got


WS = {"name": "acme", "appToken": APP, "channels": ["C0123", "G0456", "D0789"]}


# ---------------------------------------------------------------- the connection

def test_every_envelope_is_acked_at_once_and_only_the_channels_messages_are_handed_on():
    server = FakeSocketSlack([[
        env("e1", msg("1730000001.000100")),
        env("e2", msg("1730000002.000100", channel="C9999")),                      # not one of the channels
        env("e3", msg("1730000003.000100", channel="G0456", channel_type="group")),
        env("e4", msg("1730000004.000100", channel="D0789", channel_type="im")),
        env("e5", msg("1730000005.000100", subtype="message_changed")),            # an edit is not new words
        env("e6", msg("1730000006.000100", subtype="channel_join")),               # Slack's notice
        env("e7", {"type": "reaction_added", "channel": "C0123", "ts": "1730000007.000100"}),
        env("e8", msg("1730000008.000100", channel_type="app_home")),              # not a conversation we read
        env("e9", {}, kind="slash_commands"),
    ]])
    ok, client, got = run_client(server, WS, lambda c, g: len(server.acks) == 9)
    assert ok
    assert [a["envelope_id"] for a in server.acks] == [f"e{i}" for i in range(1, 10)]
    assert all(set(a) == {"envelope_id"} for a in server.acks)
    assert [(n, e["ts"]) for n, e in got] == [("acme", "1730000001.000100"), ("acme", "1730000003.000100"),
                                              ("acme", "1730000004.000100")]
    assert server.auth == [f"Bearer {APP}"]
    st = client.state.public()
    assert st["connected"] is True and st["since"] and st["lastEventAt"] and st["error"] is None


def test_the_ack_goes_before_the_message_is_worked_on():
    server = FakeSocketSlack([[env("e1", msg("1730000001.000100"))]])
    seen_acks_at_work: list[int] = []

    async def go():
        base = await server.start()

        async def on_message(name, event):
            # the ack is already on the wire: it reaches the server while the work is still going
            await until(lambda: server.acks, 1.0)
            seen_acks_at_work.append(len(server.acks))

        client = SM.Client(WS, on_message, api_base=base, backoff=FAST)
        task = asyncio.create_task(client.run())
        await until(lambda: seen_acks_at_work)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await server.stop()

    asyncio.run(go())
    assert seen_acks_at_work == [1]


@pytest.mark.parametrize("reason", ["refresh_requested", "warning"])
def test_a_disconnect_reconnects_at_once_and_the_new_connection_is_read(monkeypatch, reason):
    server = FakeSocketSlack([
        [env("e1", msg("1730000001.000100")), {"type": "disconnect", "reason": reason}],
        [env("e2", msg("1730000002.000100"))],
    ])
    waits: list[float] = []
    real_sleep = asyncio.sleep

    async def sleep(d, *a, **k):
        if d in FAST:
            waits.append(d)
        await real_sleep(d, *a, **k)

    monkeypatch.setattr(SM.asyncio, "sleep", sleep)
    ok, client, got = run_client(server, WS, lambda c, g: len(g) == 2)
    assert ok and server.opens == 2 and server.connections == 2
    assert waits == []                                      # no backoff: Slack asked for a new connection
    assert client.attempt == 0 and client.state.error is None and client.state.connected


def test_a_dropped_socket_and_a_refused_open_are_retried_after_a_wait_and_said_on_the_status():
    server = FakeSocketSlack([["drop"], [env("e1", msg("1730000001.000100"))]],
                             open_answers=[None, {"ok": False, "error": "invalid_auth"}, None])
    errors: list[str] = []

    def check(c, g):
        if c.state.error and (not errors or errors[-1] != c.state.error):
            errors.append(c.state.error)
        return len(g) == 1

    ok, client, got = run_client(server, WS, check)
    assert ok and server.opens == 3
    assert errors[:2] == ["the connection closed", "apps.connections.open: invalid_auth"]
    assert client.state.error is None and client.state.connected     # hello cleared it


def test_link_disabled_waits_the_longest_step(monkeypatch):
    server = FakeSocketSlack([[{"type": "disconnect", "reason": "link_disabled"}]])
    waits: list[float] = []
    real_sleep = asyncio.sleep

    async def sleep(d, *a, **k):
        if d in FAST:
            waits.append(d)
        await real_sleep(min(d, 0.01))

    monkeypatch.setattr(SM.asyncio, "sleep", sleep)
    ok, client, _ = run_client(server, WS, lambda c, g: bool(waits))
    assert ok and waits[0] == FAST[-1] and "link_disabled" in (client.state.error or "")


def test_no_app_token_is_said_and_nothing_is_opened():
    server = FakeSocketSlack([])
    ok, client, _ = run_client(server, {"name": "acme", "channels": ["C0123"]}, lambda c, g: c.state.error)
    assert ok and client.state.error == "no appToken" and server.opens == 0


# ---------------------------------------------------------------- the intake: same road, once

class FakeRoute:
    def __init__(self, answers):
        self.answers, self.seen = list(answers), []

    def __call__(self, message, router_cfg):
        self.seen.append(message)
        return {"adapter": "haiku", **self.answers.pop(0)}


def auth_get(method, token, params):
    assert method == "auth.test" and token == "slk-tok-QQ7"
    return {"ok": True, "url": "https://acme.slack.com/"}


def files_under(root: Path) -> list[str]:
    return sorted(str(p.relative_to(root)) for p in root.rglob("*.json")
                  if S.STATE not in p.parts and not p.name.startswith("."))


def run_service(cfg, server, route, cond, *, timeout=5.0, mutate=None):
    snaps: list[dict] = []

    async def go():
        base = await server.start()
        svc = I.Service(snaps.append, watch_sec=30.0, loader=lambda: cfg,
                        work_kw={"get": auth_get, "route": route}, socket_kw={"api_base": base, "backoff": FAST})
        task = asyncio.create_task(svc.run())
        try:
            ok = await until(lambda: cond(svc), timeout)
            status = svc.status()
            if mutate:
                await mutate(svc)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            await server.stop()
        return ok, status, svc

    ok, status, svc = asyncio.run(go())
    return ok, status, svc, snaps


def test_a_pushed_message_takes_the_intakes_road_at_once_and_the_status_shows_the_socket(tmp_path):
    aws = "".join(["AK", "IA", "IOSFODNN7EXAMPLE"])
    cfg = cfg_of(tmp_path)
    root = C.orchestration_dir(cfg)
    ts = "1730000001.000100"
    server = FakeSocketSlack([[env("e1", msg(ts, text="the shop's key " + aws, files=[{"name": "a.pdf"}]))]])
    route = FakeRoute([{"choice": "shop", "confidence": 0.9}])
    started = time.monotonic()
    ok, status, svc, _ = run_service(cfg, server, route, lambda s: (root / f"projects/shop/{ts}-acme-C0123.json").exists())
    assert ok and time.monotonic() - started < 5.0          # woken, not the 30 s poll
    placed = json.loads((root / f"projects/shop/{ts}-acme-C0123.json").read_text())
    assert aws not in placed["text"] and placed["removedFiles"] == 1
    assert aws not in route.seen[0]["text"]                  # masked before it left the machine
    assert placed["permalink"] == "https://acme.slack.com/archives/C0123/p1730000001000100"
    assert files_under(root) == [f"projects/shop/{ts}-acme-C0123.json"]
    sock = status["socket"]["acme"]
    assert sock["connected"] is True and sock["since"] and sock["lastEventAt"] and sock["error"] is None
    assert set(sock) == {"connected", "since", "lastEventAt", "error", "errorAt"}
    text = json.dumps(status)
    assert APP not in text and "slk-tok-QQ7" not in text and aws not in text


def test_a_message_sent_twice_and_fetched_again_is_taken_once_and_the_fetch_moves_the_cursor(tmp_path):
    cfg = cfg_of(tmp_path)
    root = C.orchestration_dir(cfg)
    a, missed = "1730000001.000100", "1730000002.000100"
    server = FakeSocketSlack([[env("e1", msg(a)), env("e2", msg(a))]])      # Slack's retry: a new envelope
    route = FakeRoute([{"choice": "shop", "confidence": 0.9}, {"choice": "booking", "confidence": 0.9}])
    ok, *_ = run_service(cfg, server, route, lambda s: len(server.acks) == 2 and not S.inbox_files(root)
                         and (root / f"projects/shop/{a}-acme-C0123.json").exists())
    assert ok and len(route.seen) == 1

    def history(method, token, params):
        if method == "auth.test":
            return {"ok": True, "url": ""}
        return {"ok": True, "messages": [{"ts": a, "user": "U1", "text": "x"}, {"ts": missed, "user": "U1", "text": "y"}]}

    got = FE.fetch(cfg, root, get=history, now=1730000100.0)
    assert got == {"fetched": 1, "errors": []}                               # only the one the socket missed
    assert S.Cursor(root).get("acme", "C0123") == missed
    I.process_inbox(cfg, root, route=route)
    assert files_under(root) == [f"projects/booking/{missed}-acme-C0123.json", f"projects/shop/{a}-acme-C0123.json"]
    # once the cursor and the thread watch have passed them, the ledger forgets them
    FE.prune_taken(root, C._merge(cfg, {"source": {"threadWatchDays": 0}}), 1730000100.0)
    assert S.read_json(root / S.STATE / FE.TAKEN) == {}


def test_a_pushed_reply_follows_its_thread(tmp_path):
    cfg = cfg_of(tmp_path)
    root = C.orchestration_dir(cfg)
    # Recent ts: every pass forgets the threads older than the thread watch (14 days by the real clock), so a
    # thread started in 2024 was forgotten before its reply's own pass and the reply went to the router again.
    now = int(time.time())
    parent, reply = f"{now - 60}.000100", f"{now - 30}.000100"
    placed_parent = root / f"projects/shop/{parent}-acme-C0123.json"
    # the reply comes only once the parent is placed: its own pass, the order that went red
    server = FakeSocketSlack([[env("e1", msg(parent)), placed_parent.exists,
                               env("e2", msg(reply, thread_ts=parent, parent_user_id="U1"))]])
    route = FakeRoute([{"choice": "shop", "confidence": 0.9}])
    ok, *_ = run_service(cfg, server, route, lambda s: (root / f"projects/shop/{reply}-acme-C0123.json").exists())
    assert ok and len(route.seen) == 1                       # the reply went without the router
    placed = json.loads((root / f"projects/shop/{reply}-acme-C0123.json").read_text())
    assert placed["router"]["adapter"] == "thread" and placed["threadTs"] == parent


def test_leaving_socket_mode_closes_the_connection(tmp_path):
    cfg = cfg_of(tmp_path)
    server = FakeSocketSlack([[]])
    route = FakeRoute([])
    tasks: list = []

    async def to_api(svc):
        tasks.extend(t for _k, _c, t in svc.sockets.values())
        cfg["source"]["mode"] = "api"
        svc._wake.set()
        assert await until(lambda: not svc.sockets and all(t.done() for t in tasks))
        assert "socket" not in svc.status()

    ok, status, svc, _ = run_service(cfg, server, route, lambda s: s.sockets and s.status()["socket"]["acme"]["connected"],
                                     mutate=to_api)
    assert ok and tasks and all(t.done() for t in tasks)


# ---------------------------------------------------------------- the config

def test_socket_is_a_mode_and_the_app_token_is_kept_off_the_view(tmp_path):
    cfg = cfg_of(tmp_path)
    C.validate(cfg)
    view = C.public_view(cfg)["source"]["workspaces"][0]
    assert view["appToken"] is True and view["token"] is True
    with pytest.raises(C.ConfigError, match="appToken"):
        C.validate(cfg_of(tmp_path, source={"workspaces": [{"name": "acme", "appToken": 7, "channels": []}]}))
    with pytest.raises(C.ConfigError, match="api, connector or socket"):
        C.validate(cfg_of(tmp_path, source={"mode": "push"}))


def test_the_socket_plan_follows_the_config(tmp_path):
    cfg = cfg_of(tmp_path)
    assert SM.plan(cfg) == {"acme": (APP, ("C0123",), "slk-tok-QQ7")}
    assert SM.plan(cfg_of(tmp_path, source={"mode": "api"})) == {}
    assert SM.plan(None) == {}


# ---------------------------------------------------------------- Slack's ticket stays off every view

TICKET = "".join(["tk", "-QQ9-one-time-0123456789"])


class HandshakeRefused(FakeSocketSlack):
    """apps.connections.open answers a URL with Slack's ticket in its query (wss://…/link/?ticket=…&app_id=…), and
    the WebSocket's handshake is refused (401): aiohttp's error repeats the whole URL."""

    async def open(self, request):
        self.opens += 1
        return web.json_response({"ok": True, "url": f"ws://127.0.0.1:{self.port}/link/?ticket={TICKET}&app_id=A0QQ"})

    async def link(self, request):
        return web.Response(status=401)


def test_a_refused_handshake_keeps_slacks_ticket_off_the_status_the_slice_and_the_snapshot(tmp_path):
    from jui_cli.viz.state import VizState

    cfg = cfg_of(tmp_path)
    state = VizState()
    seen: list[dict] = []

    def cond(svc):
        snap = svc.status()
        seen.append(snap)
        state.set_slice("slack", snap)               # what serve's on_slack does; /api/snapshot is state.snapshot()
        return bool(((snap.get("socket") or {}).get("acme") or {}).get("error"))

    server = HandshakeRefused([])
    ok, status, svc, snaps = run_service(cfg, server, FakeRoute([]), cond)
    assert ok and server.opens >= 1
    err = status["socket"]["acme"]["error"]
    assert "Invalid response status" in err and f"127.0.0.1:{server.port}/link/?…" in err      # still says where, without the query
    for view in (status, snaps, seen, state.snapshot()):
        text = json.dumps(view)
        assert TICKET not in text and "ticket=" not in text and "app_id=" not in text


def test_every_error_the_state_keeps_has_no_urls_query():
    st = SM.State()
    st.fail(f"401, message='Invalid response status', url=URL('wss://wss-primary.slack.com/link/?ticket={TICKET}&app_id=A0QQ')")
    assert st.error == "401, message='Invalid response status', url=URL('wss://wss-primary.slack.com/link/?…')"
    st.fail(f"Cannot connect to host wss-primary.slack.com:443 ssl:default [https://x.example/a?b={TICKET}#f]")
    assert TICKET not in st.error and "https://x.example/a?…]" in st.error
    st.fail("the connection closed")
    assert st.error == "the connection closed"
    assert I._from_tilde(f"acme: ws://h/p?ticket={TICKET}") == "acme: ws://h/p?…"   # the same layer as the key mask
