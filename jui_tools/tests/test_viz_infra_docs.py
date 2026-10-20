"""The server room's reading on viz's side (infra_docs.py → document_tools' infra.room; ticket 2026-10-20-jui-viz-
server-room, part B; the boundary's §5.2/§8): the routes' checks, the reply as the page gets it (the page's seq back,
ok/reason/message with the boundary's HTTP status), what never reaches the page (a file holding a secret-shaped value,
a symlink out of the room, a URL icon), a FIFO never holding a read, and the room row's count from the worker.

The rooms are the boundary's examples, written into a temporary folder by document_tools' make_examples.py (its
functions, not the files: three of them sit under a docs/ the repository's .gitignore keeps out — ticket
2026-10-20-jui-infra-fixtures-under-docs-not-committed)."""
from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import socket
import threading
import time
from pathlib import Path

import pytest
from aiohttp.test_utils import TestClient, TestServer

from jui_cli.viz import infra_docs as I

TOKEN = "t" * 43
FIXTURES = Path(__file__).resolve().parents[2] / "document_tools" / "tests" / "fixtures" / "infra"


def _examples() -> dict:
    spec = importlib.util.spec_from_file_location("infra_make_examples", FIXTURES / "make_examples.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.all_examples()


EXAMPLES = _examples()


def _room(tmp_path: Path, name: str) -> Path:
    """One example room (its files under <name>/), written under tmp_path."""
    for rel, data in EXAMPLES.items():
        if rel.split("/")[0] != name:
            continue
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data if isinstance(data, str) else json.dumps(data, ensure_ascii=False), encoding="utf-8")
    root = tmp_path / name
    (root / ".git").mkdir(exist_ok=True)
    return root


def test_the_examples_are_there_to_use():
    rooms = {rel.split("/")[0] for rel in EXAMPLES}
    assert {"aws-three-tier", "multi-provider", "compose-and-cloud", "large-multi-provider"} <= rooms


def test_counts_and_read_through_the_boundarys_reader(tmp_path):
    root = _room(tmp_path, "aws-three-tier")
    assert I.counts(root) == {"files": 2, "dir": "docs/infra"}
    status, m = I.read(root, seq=7)
    assert status == 200 and m["ok"] and m["seq"] == 7 and m["files"] and m["nodes"] and "readMs" in m
    folded = [n for n in m["nodes"] if n.get("fold")]
    assert folded and all(n["category"] in ("security.iam", "security.policy", "monitoring.alarm") or n.get("fold") for n in folded)


def test_crossing_edges_are_marked(tmp_path):
    status, m = I.read(_room(tmp_path, "multi-provider"))
    assert status == 200 and any(e.get("crossProvider") for e in m["edges"])
    assert len({n.get("providerResolved") for n in m["nodes"]} - {None}) >= 2


def test_a_moved_folder_and_its_icons(tmp_path):
    root = _room(tmp_path, "compose-and-cloud")
    assert I.counts(root)["dir"] == "infra/model"
    status, m = I.read(root)
    assert status == 200 and m["dir"] == "infra/model" and m["icons"]
    for key in m["icons"]:
        got = I.icon(root, key)
        assert got is not None and got[1] in ("image/svg+xml", "image/png", "image/webp")


def test_a_url_icon_is_never_read(tmp_path):
    root = _room(tmp_path, "compose-and-cloud")
    cfg = json.loads((root / "jui.config.json").read_text())
    cfg["infra"]["icons"]["category:queue"] = "https://example.invalid/q.svg"
    (root / "jui.config.json").write_text(json.dumps(cfg))
    status, m = I.read(root)
    assert "category:queue" not in m["icons"] and I.icon(root, "category:queue") is None
    assert any(p.get("code") == "config.icon" and "URL" in p.get("message", "") for p in m["problems"])


def _strings(value) -> set[str]:
    if isinstance(value, str):
        return {value}
    if isinstance(value, dict):
        return set().union(*(_strings(v) for v in value.values())) if value else set()
    if isinstance(value, list):
        return set().union(*(_strings(v) for v in value)) if value else set()
    return set()


@pytest.mark.parametrize("bad", sorted(rel for rel in EXAMPLES if rel.startswith("invalid/") and "secret" in rel))
def test_a_file_holding_a_secret_shape_never_reaches_the_page(tmp_path, bad):
    """The whole file is left out (the boundary: one value leaked, the rest of it is not trusted either): none of its
    strings reaches the page, except those the clean room's reply has anyway."""
    clean = json.dumps(I.read(_room(tmp_path / "clean", "aws-three-tier"))[1], ensure_ascii=False)
    root = _room(tmp_path, "aws-three-tier")
    data = EXAMPLES[bad]
    raw = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
    (root / "docs/infra/zz-secret.json").write_text(raw, encoding="utf-8")
    status, m = I.read(root)
    text = json.dumps(m, ensure_ascii=False)
    leaked = [v for v in _strings(json.loads(raw)) if len(v) >= 6 and v in text and v not in clean]
    assert leaked == [] and "zz-secret.json" not in m["files"]
    assert any("secret" in p.get("code", "") for p in m["problems"])


@pytest.mark.parametrize("make, reason, http", [("none", "no_infra", 404), ("bad_dir", "bad_config", 400)])
def test_a_room_that_cannot_be_read_says_why_with_the_boundarys_status(tmp_path, make, reason, http):
    root = tmp_path / "room"
    (root / ".git").mkdir(parents=True)
    if make == "bad_dir":
        (root / "jui.config.json").write_text(json.dumps({"infra": {"dir": "../outside"}}))
    status, m = I.read(root, seq=3)
    assert (status, m["ok"], m["reason"], m["seq"]) == (http, False, reason, 3) and m["message"]


def test_a_symlinked_folder_is_not_followed(tmp_path):
    src = _room(tmp_path / "src", "aws-three-tier")
    root = tmp_path / "room"
    (root / "docs").mkdir(parents=True)
    (root / "docs/infra").symlink_to(src / "docs/infra")
    assert I.counts(root)["files"] == 0
    status, m = I.read(root)
    # the boundary since 0dee01ae: a folder reached through a symlink is unreadable, and says why (not "no files")
    assert not m["ok"] and m["reason"] == "unreadable" and status >= 400 and m["short"]
    assert not m.get("nodes") and not m.get("files")


def test_a_fifo_in_place_of_a_file_never_holds_the_read(tmp_path):
    root = _room(tmp_path, "aws-three-tier")
    os.mkfifo(root / "docs/infra/zz.json")
    done, out = threading.Event(), {}
    threading.Thread(target=lambda: (out.setdefault("r", I.read(root)), done.set()), daemon=True).start()
    assert done.wait(5), "a FIFO held the read"


def test_the_large_example_reads_within_the_limits(tmp_path):
    status, m = I.read(_room(tmp_path, "large-multi-provider"))
    assert status == 200 and len(m["nodes"]) >= 1900 and len(m["edges"]) >= 4500 and m["readMs"] < 10_000


# ---- the routes and the room row ----

def _port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _serve(world, calls):
    from jui_cli.viz.config import VizConfig
    from jui_cli.viz.server import ServerContext, make_app
    port = _port()
    own = f"127.0.0.1:{port}"

    async def run():
        ctx = ServerContext(config=VizConfig(), port=port, token=TOKEN, state=world.state, world=world, publish=world.publish)
        client = TestClient(TestServer(make_app(ctx), host="127.0.0.1", port=port))
        await client.start_server()
        out = []
        try:
            for method, path, headers, body in calls(own):
                r = await client.request(method, path, headers=headers, data=body)
                out.append((r.status, r.headers.get("Content-Type", ""), await r.read(), dict(r.headers)))
        finally:
            await client.close()
        return out
    return asyncio.run(run())


def _world(root: Path):
    from jui_cli.viz.ingest import World
    from jui_cli.viz.state import VizState, now_ms
    w = World(VizState())
    w.apply_hook({"hook_event_name": "SessionStart", "session_id": "1f000000-0000-4000-8000-000000000001", "cwd": str(root),
                  "source": "startup"}, now_ms())
    w.publish()
    return w, w.state.snapshot()["slices"]["projects"][0]["id"]


def test_the_routes_take_the_page_checks_and_give_the_model_and_an_icon(tmp_path):
    root = _room(tmp_path, "compose-and-cloud")
    world, pid = _world(root)
    key = sorted(I.read(root)[1]["icons"])[0]

    def calls(own):
        ok = {"Host": own, "Origin": f"http://{own}", "X-Jui-Viz-Token": TOKEN, "Content-Type": "application/json"}
        body = json.dumps({"projectId": pid, "seq": 11})
        return [("POST", "/api/infra-docs", ok, body),
                ("POST", "/api/infra-docs", {**ok, "X-Jui-Viz-Token": "x" * 43}, body),
                ("POST", "/api/infra-docs", {k: v for k, v in ok.items() if k != "Origin"}, body),
                ("POST", "/api/infra-docs", {**ok, "Origin": "http://evil.example"}, body),
                ("POST", "/api/infra-docs", {**ok, "Host": own.replace("127.0.0.1", "localhost")}, body),
                ("GET", "/api/infra-docs", ok, None),
                ("POST", "/api/infra-docs", {**ok, "Content-Type": "text/plain"}, body),
                ("POST", "/api/infra-docs", ok, json.dumps({"projectId": "nope"})),
                ("POST", "/api/infra-docs", ok, json.dumps({"path": str(root)})),
                ("POST", "/api/infra-icon", ok, json.dumps({"projectId": pid, "key": key})),
                ("POST", "/api/infra-icon", ok, json.dumps({"projectId": pid, "key": "category:queue"}))]
    got = _serve(world, calls)
    assert [g[0] for g in got] == [200, 401, 403, 403, 403, 405, 415, 404, 400, 200, 404]
    model = json.loads(got[0][2])
    assert model["ok"] and model["seq"] == 11 and model["nodes"] and got[0][3]["Cache-Control"] == "no-store"
    assert got[9][3]["X-Content-Type-Options"] == "nosniff" and got[9][1].startswith(("image/svg+xml", "image/png", "image/webp"))


def test_a_refusal_comes_with_the_boundarys_status_and_the_seq(tmp_path):
    root = tmp_path / "room"
    (root / ".git").mkdir(parents=True)
    world, pid = _world(root)
    got = _serve(world, lambda own: [("POST", "/api/infra-docs", {"Host": own, "Origin": f"http://{own}", "X-Jui-Viz-Token": TOKEN,
                                                                   "Content-Type": "application/json"}, json.dumps({"projectId": pid, "seq": 5}))])
    body = json.loads(got[0][2])
    assert got[0][0] == 404 and body == {"ok": False, "seq": 5, "reason": "no_infra", "message": body["message"], "short": body["short"]}
    assert body["short"] and body["message"]   # the line the page shows as it is, and the whole text


def test_the_room_row_gets_its_count_from_the_worker(tmp_path):
    from jui_cli.viz.state import now_ms
    root = _room(tmp_path, "aws-three-tier")
    world, pid = _world(root)
    end, row = time.time() + 10, {}
    while time.time() < end:
        world.tick(now_ms())
        world.publish()
        row = next(p for p in world.state.snapshot()["slices"]["projects"] if p["id"] == pid)
        if row.get("infraDocs"):
            break
        time.sleep(0.05)
    assert row.get("infraDocs") == {"files": 2, "dir": "docs/infra"}
    assert any(t.name.startswith("jui-viz-infra") for t in threading.enumerate())


# ---- the guards dd's verification found without an arm (P2–P7, P9, P10, P12; 2026-10-20) ----

def _chunked(data: bytes):
    """A body sent chunked (no Content-Length, so the declared-length check cannot refuse it): only the read's own cap can."""
    async def gen():
        for i in range(0, len(data), 1024):
            yield data[i:i + 1024]
    return gen()


def test_the_icon_route_takes_the_same_checks_and_reads_only_configured_keys(tmp_path, monkeypatch):
    """P2: the icon route refuses a wrong token and a foreign Origin itself (not only through the model's route).
    P5: a projectId is an id, never a folder: the room's own path and a relative one are unknown rooms.
    P6: a key the settings do not name is not read, though a file of that name is in the room.
    P4/P12: the length caps of projectId and key. P3: a chunked body (no Content-Length) over the cap is refused (413).
    P7: an icon is never cached."""
    import io
    root = _room(tmp_path, "compose-and-cloud")
    world, pid = _world(root)
    monkeypatch.chdir(tmp_path)   # so the relative paths below name the real room folder (a reader of paths would find it)
    model = I.read(root)[1]
    key = sorted(model["icons"])[0]
    icon_file = model["icons"][key] if isinstance(model["icons"][key], str) else None
    cfg = json.loads((root / "jui.config.json").read_text())
    icon_file = icon_file or next(iter(cfg["infra"]["icons"].values()))
    assert (root / icon_file).is_file()

    def calls(own):
        ok = {"Host": own, "Origin": f"http://{own}", "X-Jui-Viz-Token": TOKEN, "Content-Type": "application/json"}
        icon = json.dumps({"projectId": pid, "key": key})
        return [("POST", "/api/infra-icon", {**ok, "X-Jui-Viz-Token": "x" * 43}, icon),                      # P2
                ("POST", "/api/infra-icon", {**ok, "Origin": "http://evil.example"}, icon),                    # P2
                ("POST", "/api/infra-docs", ok, json.dumps({"projectId": "./compose-and-cloud"})),             # P5
                ("POST", "/api/infra-docs", ok, json.dumps({"projectId": "compose-and-cloud"})),               # P5
                ("POST", "/api/infra-docs", ok, json.dumps({"projectId": "o/compose-and-cloud"})),             # P5
                ("POST", "/api/infra-icon", ok, json.dumps({"projectId": pid, "key": icon_file})),             # P6
                ("POST", "/api/infra-docs", ok, json.dumps({"projectId": "p" * 65})),                          # P4
                ("POST", "/api/infra-icon", ok, json.dumps({"projectId": pid, "key": ""})),                    # P12
                ("POST", "/api/infra-icon", ok, json.dumps({"projectId": pid, "key": "k" * 201})),             # P12
                ("POST", "/api/infra-docs", ok, _chunked(b'{"projectId": "' + b"x" * 20_000 + b'"}')),         # P3
                ("POST", "/api/infra-icon", ok, icon)]                                                        # P7
    got = _serve(world, calls)
    assert [g[0] for g in got] == [401, 403, 404, 404, 404, 404, 400, 400, 400, 413, 200]
    assert all(b"nodes" not in g[2] for g in got[2:5])                     # no model for a path given as an id
    assert got[10][3].get("Cache-Control") == "no-store"


def test_the_model_is_read_off_the_event_loop(tmp_path, monkeypatch):
    """P9: a slow read (1.5 s here) does not hold the server: /health, asked 0.2 s after the press, answers at once."""
    root = _room(tmp_path, "aws-three-tier")
    world, pid = _world(root)
    real = I.read
    monkeypatch.setattr(I, "read", lambda r, seq=None: (time.sleep(1.5), real(r, seq))[1])
    from jui_cli.viz.config import VizConfig
    from jui_cli.viz.server import ServerContext, make_app
    port = _port()
    own = f"127.0.0.1:{port}"

    async def run():
        ctx = ServerContext(config=VizConfig(), port=port, token=TOKEN, state=world.state, world=world, publish=world.publish)
        client = TestClient(TestServer(make_app(ctx), host="127.0.0.1", port=port))
        await client.start_server()
        try:
            ok = {"Host": own, "Origin": f"http://{own}", "X-Jui-Viz-Token": TOKEN, "Content-Type": "application/json"}
            press = asyncio.ensure_future(client.post("/api/infra-docs", headers=ok, data=json.dumps({"projectId": pid})))
            # the client shares the server's loop: a read on the loop would hold this sleep too, so the clock starts first
            t0 = time.monotonic()
            await asyncio.sleep(0.2)
            health = await client.get("/health", headers={"Host": own})
            took = time.monotonic() - t0
            res = await press
            return health.status, took, res.status
        finally:
            await client.close()
    status, took, read_status = asyncio.run(run())
    assert status == 200 and read_status == 200 and took < 1.0, (status, took)   # 1.5 s if the read held the loop


def test_the_rooms_are_counted_every_few_seconds_not_every_tick(tmp_path, monkeypatch):
    """P10: the door's count (a listing of each room's infra folder) runs once per INFRA_EVERY_MS, however often the
    world ticks."""
    from jui_cli.viz.ingest import INFRA_EVERY_MS
    root = _room(tmp_path, "aws-three-tier")
    world, pid = _world(root)
    calls = []
    real = I.counts
    monkeypatch.setattr(I, "counts", lambda r, cache=None: (calls.append(1), real(r, cache))[1])
    t0 = 10_000_000
    for k in range(40):   # 2 s of ticks, 50 ms apart, well inside one INFRA_EVERY_MS
        world.tick(t0 + k * 50)
        time.sleep(0.02)
    assert INFRA_EVERY_MS >= 2_000 and len(calls) == 1, len(calls)


def test_the_icon_and_model_routes_check_their_types_and_never_follow_a_symlink(tmp_path):
    """dd's re-verification: N1 a seq that is not an int (true) comes back as null; N4 a key that is not a string is a
    bad request; N3 a room whose jui.config.json is broken has no icon (404, not a server error); N8 an icon that is a
    symlink to a file outside the room is not read (404, nothing of that file)."""
    root = _room(tmp_path, "compose-and-cloud")
    world, pid = _world(root)
    cfg = json.loads((root / "jui.config.json").read_text())
    key = sorted(k for k in cfg["infra"]["icons"])[0]
    outside = tmp_path / "outside-secret.svg"
    outside.write_text("<svg>outside-of-the-room</svg>")
    linked = root / cfg["infra"]["icons"][key]
    linked.unlink()
    linked.symlink_to(outside)
    broken = tmp_path / "broken"
    (broken / ".git").mkdir(parents=True)
    (broken / "jui.config.json").write_text("{ not json")
    world.apply_hook({"hook_event_name": "SessionStart", "session_id": "1f000000-0000-4000-8000-000000000002", "cwd": str(broken),
                      "source": "startup"}, int(time.time() * 1000))
    world.publish()
    bpid = next(p["id"] for p in world.state.snapshot()["slices"]["projects"] if p["id"] != pid)

    def calls(own):
        ok = {"Host": own, "Origin": f"http://{own}", "X-Jui-Viz-Token": TOKEN, "Content-Type": "application/json"}
        return [("POST", "/api/infra-docs", ok, json.dumps({"projectId": pid, "seq": True})),                       # N1
                ("POST", "/api/infra-icon", ok, json.dumps({"projectId": pid, "key": [key]})),                      # N4
                ("POST", "/api/infra-icon", ok, json.dumps({"projectId": bpid, "key": key})),                       # N3
                ("POST", "/api/infra-icon", ok, json.dumps({"projectId": pid, "key": key}))]                        # N8
    got = _serve(world, calls)
    assert [g[0] for g in got] == [200, 400, 404, 404], [g[0] for g in got]
    assert json.loads(got[0][2])["seq"] is None
    assert b"outside-of-the-room" not in got[3][2]
