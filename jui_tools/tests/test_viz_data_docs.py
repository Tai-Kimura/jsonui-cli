"""jui viz: the data server's documents (2.3.5, requester 10-19).

data_docs finds a JsonUI room's API and DB specifications the way `jsonui-doc generate` does (docs/api, docs/db,
docs/db/<name>/, is_swagger_file, has_api_paths) with document_tools' own helpers, counts them for the rack, and reads
them only when asked, from inside the room only. POST /api/data-docs hands them to the page under /api/prompt's checks.
A JsonUI room under tmp_path; nothing reads the real home.
"""
from __future__ import annotations

import asyncio
import html as htmllib
import json
import os
import re
import socket
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from aiohttp.test_utils import TestClient, TestServer

from jui_cli.viz import data_docs
from jui_cli.viz.config import VizConfig
from jui_cli.viz.ingest import World
from jui_cli.viz.server import ServerContext, make_app
from jui_cli.viz.state import VizState

TOKEN = "t" * 43
API = {"openapi": "3.0.0", "info": {"title": "Users API <b>", "version": "1.2", "description": "ユーザー"},
       "paths": {"/users/{id}": {"parameters": [{"name": "id", "in": "path", "required": True, "schema": {"type": "string"}}],
                                 "get": {"summary": "一人を取る", "operationId": "getUser", "tags": ["users"],
                                         "responses": {"200": {"description": "ok", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/User"}}}}}},
                                 "delete": {"summary": "消す", "responses": {"204": {"description": "gone"}}}},
                 "/users": {"post": {"summary": "作る", "requestBody": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/User"}}}},
                                     "responses": {"201": {"description": "made"}}}}},
       "components": {"schemas": {"User": {"type": "object", "properties": {"id": {"type": "string"}}}}}}
USERS_TABLE = {"openapi": "3.0.0", "info": {"title": "users", "version": "1", "x-table-name": "users"},
               "components": {"schemas": {
                   "User": {"type": "object", "description": "利用者", "required": ["id", "email"],
                            "properties": {"id": {"type": "integer", "format": "int64", "x-primary-key": True, "x-auto-increment": True},
                                           "email": {"type": "string", "maxLength": 255, "x-unique": True, "description": "連絡先"},
                                           "role": {"type": "string", "enum": ["admin", "member"], "default": "member", "nullable": True},
                                           "team_id": {"type": "integer", "x-foreign-key": {"table": "teams", "column": "id"}, "x-index": True,
                                                       "x-notes": ["チームは任意", "<i>"]}}},
                   "Role": {"type": "string", "enum": ["admin", "member"]}}}}
TEAMS_TABLE = {"openapi": "3.0.0", "info": {"title": "teams", "version": "1", "x-table-name": "teams"},
               "components": {"schemas": {"Team": {"type": "object", "properties": {"id": {"type": "integer", "x-primary-key": True}, "name": {"type": "string"}}}}}}
EVENTS_TABLE = {"openapi": "3.0.0", "info": {"title": "events", "version": "1", "x-table-name": "events"},
                "components": {"schemas": {"Event": {"type": "object", "properties": {"id": {"type": "integer", "x-primary-key": True}}}}}}


def _room(root: Path, api=True, db=True, multi=False) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "jui.config.json").write_text(json.dumps({"spec_directory": "docs/screens/json"}))
    (root / "docs/screens/json").mkdir(parents=True, exist_ok=True)
    if api:
        (root / "docs/api").mkdir(parents=True, exist_ok=True)
        (root / "docs/api/users.json").write_text(json.dumps(API, ensure_ascii=False))
        (root / "docs/api/notes.json").write_text(json.dumps({"not": "openapi"}))
    if db:
        (root / "docs/db").mkdir(parents=True, exist_ok=True)
        (root / "docs/db/users.json").write_text(json.dumps(USERS_TABLE, ensure_ascii=False))
        (root / "docs/db/teams.json").write_text(json.dumps(TEAMS_TABLE))
    if multi:
        (root / "docs/db/analytics").mkdir(parents=True, exist_ok=True)
        (root / "docs/db/analytics/events.json").write_text(json.dumps(EVENTS_TABLE))
    return root


def _project(root: Path):
    return SimpleNamespace(root=root, sources=[SimpleNamespace(root=root)])


@pytest.mark.parametrize("api,db,want", [(True, True, {"api": 1, "db": 2}), (True, False, {"api": 1, "db": 0}),
                                         (False, True, {"api": 0, "db": 2}), (False, False, {"api": 0, "db": 0})])
def test_counts(tmp_path, api, db, want):
    assert data_docs.counts(_project(_room(tmp_path / "app", api, db))) == want


def test_the_files_are_document_tools_own_choice(tmp_path):
    """The same files, sorted the same way, that generate's discovery takes (is_swagger_file over docs/{api,db}
    rglob *.json), with generator.py's category for each (docs/db/<name>/ a database of its own)."""
    root = _room(tmp_path / "app", multi=True)
    mods = data_docs._doc()
    theirs = [(("db/" + f.relative_to(root / "docs/db").parts[0]) if k == "db" and len(f.relative_to(root / f"docs/{k}").parts) > 1 else k, f)
              for k in ("api", "db") for f in sorted((root / "docs" / k).rglob("*.json")) if mods["swagger"].is_swagger_file(f)]
    ours = [(c, f) for c, f, _d, _r in data_docs._files(_project(root)) if mods["swagger"].is_swagger_file(f)]
    assert ours == theirs
    doc = data_docs.read(_project(root))
    assert [d["category"] for d in doc["db"]] == ["db/analytics", "db"] or sorted(d["category"] for d in doc["db"]) == ["db", "db/analytics"]


def test_what_is_read(tmp_path):
    doc = data_docs.read(_project(_room(tmp_path / "app")))
    (api,) = doc["api"]
    assert api["file"] == "docs/api/users.json" and api["title"] == "Users API <b>" and api["version"] == "1.2"
    assert [(e["method"], e["path"]) for e in api["endpoints"]] == [("GET", "/users/{id}"), ("DELETE", "/users/{id}"), ("POST", "/users")]
    get = api["endpoints"][0]
    assert get["summary"] == "一人を取る" and get["parameters"][0]["name"] == "id" and "200" in get["responses"]
    assert "User" in api["schemas"]
    (db,) = doc["db"]
    assert db["name"] == "db" and {t["name"] for t in db["tables"]} == {"User", "Role", "Team"}


def test_the_er_diagram_is_document_tools_own(tmp_path):
    root = _room(tmp_path / "app")
    mods = data_docs._doc()
    files = [{"name": n, "swagger_data": json.loads((root / f"docs/db/{n}.json").read_text())} for n in ("teams", "users")]
    doc = data_docs.read(_project(root))
    assert doc["db"][0]["erd"] == mods["erd"]._build_mermaid_erd(files)
    assert doc["db"][0]["erd"].startswith("erDiagram")


def _cells(row_html: str) -> list[str]:
    cells = re.findall(r"<td[^>]*>(.*?)</td>", row_html, re.S)
    return [" ".join(htmllib.unescape(re.sub(r"<br>", " ", re.sub(r"<(?!br)[^>]+>", "", c))).split()) for c in cells]


def test_each_column_says_what_the_schema_page_says(tmp_path):
    """The columns carry what schema.py's _render_property_row writes (Field, Type, Description, Default, Key,
    Constraints, Notes), cell for cell as text."""
    mods = data_docs._doc()
    user = USERS_TABLE["components"]["schemas"]["User"]
    for name, prop in user["properties"].items():
        theirs = _cells("".join(mods["schema"]._render_property_row(name, prop, name in user["required"])))
        c = data_docs._column(name, prop, name in user["required"])
        ours = [c["name"], c["type"], c["description"], c["default"], " ".join(c["keys"]) or "-", " ".join(c["constraints"]) or "-", " ".join(c["notes"]) or "-"]
        assert [" ".join(x.split()) for x in ours] == theirs, name


def test_nothing_outside_the_room_is_read(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.json").write_text(json.dumps({**API, "info": {"title": "SECRET", "version": "1"}}))
    root = _room(tmp_path / "app", db=False)
    os.symlink(outside / "secret.json", root / "docs/api/link.json")               # a file pointing out
    (root / "docs/api/sub").mkdir()
    os.symlink(outside, root / "docs/api/sub/out")                                  # a folder pointing out
    other = _room(tmp_path / "other", api=False, db=False)
    (other / "docs").mkdir(exist_ok=True)
    os.symlink(outside, other / "docs/api")                                         # the docs folder itself
    for proj in (_project(root), _project(other)):
        doc = data_docs.read(proj)
        assert "SECRET" not in json.dumps(doc, ensure_ascii=False)
    assert data_docs.counts(_project(other)) == {"api": 0, "db": 0}


def test_caps(tmp_path, monkeypatch):
    root = _room(tmp_path / "app")
    monkeypatch.setattr(data_docs, "MAX_FILE_BYTES", 100)
    assert data_docs.read(_project(root))["api"] == []
    monkeypatch.setattr(data_docs, "MAX_FILE_BYTES", 2_000_000)
    monkeypatch.setattr(data_docs, "MAX_TOTAL_BYTES", 1500)
    doc = data_docs.read(_project(root))
    assert doc["skipped"] >= 1


# ---- the world and the route --------------------------------------------------------------------------------------

def _settle(world, at: int) -> int:
    """Tick until no room is marked and the worker has nothing running (a state, bounded by a count), then publish."""
    import time as _t
    for _ in range(500):
        at += 600
        world.tick(at)
        if not world._data_docs_due and world._data_docs_job is None:
            break
        _t.sleep(0.01)
    world.publish()
    return at


def _world(tmp_path):
    root = _room(tmp_path / "app")
    world = World(VizState())
    world.apply_hook({"hook_event_name": "SessionStart", "session_id": "s1", "cwd": str(root)}, 1)
    _settle(world, 1)
    (pid,) = [p["id"] for p in world.state.slices["projects"]]
    return world, root, pid


def test_the_room_carries_its_counts_and_a_change_updates_them(tmp_path):
    world, root, pid = _world(tmp_path)
    (room,) = world.state.slices["projects"]
    assert room["dataDocs"] == {"api": 1, "db": 2}
    (root / "docs/db/teams.json").unlink()
    world.file_changed(pid, str(root / "docs/db/teams.json"), 10_000_000)
    assert world._data_docs_due == {pid: 10_000_000}          # marked only: nothing read on the caller's thread
    _settle(world, 10_000_000)
    assert world.state.slices["projects"][0]["dataDocs"] == {"api": 1, "db": 1}
    assert "dataDocs" not in json.dumps(world.state.slices.get("specs", []))


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _serve(world, calls):
    port = _free_port()
    own = f"127.0.0.1:{port}"

    async def run():
        ctx = ServerContext(config=VizConfig(pushIntervalMs=50), port=port, token=TOKEN, state=world.state, world=world, publish=world.publish)
        client = TestClient(TestServer(make_app(ctx), host="127.0.0.1", port=port))
        await client.start_server()
        out = []
        try:
            for method, headers, body in calls(own):
                r = await client.request(method, "/api/data-docs", headers=headers, data=body)
                out.append((r.status, r.headers.get("Content-Type", ""), await r.read(), dict(r.headers)))
        finally:
            await client.close()
        return out
    return asyncio.run(run())


def test_the_route_gives_the_documents_to_the_page_and_nothing_to_anyone_else(tmp_path):
    world, root, pid = _world(tmp_path)
    good = json.dumps({"projectId": pid})

    def calls(own):
        ok = {"Host": own, "Origin": f"http://{own}", "X-Jui-Viz-Token": TOKEN, "Content-Type": "application/json"}
        return [
            ("POST", ok, good),
            ("POST", {**ok, "X-Jui-Viz-Token": "x" * 43}, good),
            ("POST", {k: v for k, v in ok.items() if k != "X-Jui-Viz-Token"}, good),
            ("POST", {**ok, "Origin": "http://evil.example"}, good),
            ("POST", {k: v for k, v in ok.items() if k != "Origin"}, good),
            ("POST", {**ok, "Host": f"localhost:{own.split(':')[1]}"}, good),
            ("GET", ok, None),
            ("POST", {**ok, "Content-Type": "text/plain"}, good),
            ("POST", ok, json.dumps({"projectId": "nope"})),
            ("POST", ok, json.dumps({"projectId": str(root)})),
            ("POST", ok, json.dumps({"projectId": pid, "path": "/etc/passwd", "file": "../../etc/passwd"})),
            ("POST", ok, json.dumps({"projectId": 3})),
            ("POST", ok, "x" * 9000),
        ]
    got = _serve(world, calls)
    status = [g[0] for g in got]
    assert status == [200, 401, 401, 403, 403, 403, 405, 415, 404, 400, 200, 400, 413], status
    body = json.loads(got[0][2])
    assert got[0][1] == "application/json" and got[0][3].get("Cache-Control") == "no-store"
    assert body["api"][0]["title"] == "Users API <b>" and len(body["db"]) == 1
    assert got[10][2] == got[0][2]                       # a path in the body changes nothing
    for st, _ct, b, _h in got[1:10] + got[11:]:
        assert b"Users API" not in b                      # a refusal carries no document


# ---- the open is the check (dd's review, 10-19) --------------------------------------------------------------------

@pytest.mark.parametrize("body", [json.dumps(API), json.dumps({"swagger": "2.0", "paths": {}}), json.dumps({"not": "openapi"}),
                                  json.dumps([1, 2]), "{broken", b"\xff\xfe"])
def test_the_bytes_rule_is_is_swagger_files(tmp_path, body):
    f = tmp_path / "x.json"
    f.write_bytes(body if isinstance(body, bytes) else body.encode())
    mods = data_docs._doc()
    assert (data_docs._swagger(f.read_bytes()) is not None) == mods["swagger"].is_swagger_file(f)


def _race(path: Path, a: Path, b: Path, stop: threading.Event):
    """Swap ``path`` between a copy of ``a`` (a regular file) and ``b`` (a symlink, or a big file) as fast as it can."""
    tmp_a, tmp_b = path.with_name(".a.tmp"), path.with_name(".b.tmp")
    while not stop.is_set():
        try:
            tmp_a.write_bytes(a.read_bytes())
            os.replace(tmp_a, path)
            if b.is_symlink():
                if tmp_b.exists() or tmp_b.is_symlink():
                    tmp_b.unlink()
                os.symlink(os.readlink(b), tmp_b)
            else:
                tmp_b.write_bytes(b.read_bytes())
            os.replace(tmp_b, path)
        except OSError:
            pass


def test_a_symlink_swapped_in_never_lets_outside_through(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.json").write_text(json.dumps({**API, "info": {"title": "SECRET", "version": "1"}}))
    root = _room(tmp_path / "app", db=False)
    target = root / "docs/api/users.json"
    good = tmp_path / "good.json"
    good.write_text(json.dumps(API))
    link = tmp_path / "link.json"
    os.symlink(outside / "secret.json", link)
    stop = threading.Event()
    t = threading.Thread(target=_race, args=(target, good, link, stop), daemon=True)
    t.start()
    try:
        seen = [json.dumps(data_docs.read(_project(root)), ensure_ascii=False) for _ in range(300)]
        counted = [data_docs.counts(_project(root)) for _ in range(100)]
    finally:
        stop.set()
        t.join()
    assert not any("SECRET" in x for x in seen)
    assert any("Users API" in x for x in seen)                       # the race was run: the good file was read too
    assert all(c["api"] <= 1 for c in counted)


def test_a_big_file_swapped_in_never_passes_the_cap(tmp_path, monkeypatch):
    monkeypatch.setattr(data_docs, "MAX_FILE_BYTES", 4000)
    root = _room(tmp_path / "app", db=False)
    target = root / "docs/api/users.json"
    small, big = tmp_path / "small.json", tmp_path / "big.json"
    small.write_text(json.dumps(API))
    big.write_text(json.dumps({**API, "info": {"title": "BIG", "version": "1", "description": "x" * 10_000}}))
    stop = threading.Event()
    t = threading.Thread(target=_race, args=(target, small, big, stop), daemon=True)
    t.start()
    try:
        seen = [json.dumps(data_docs.read(_project(root)), ensure_ascii=False) for _ in range(300)]
    finally:
        stop.set()
        t.join()
    assert not any("BIG" in x for x in seen)
    assert any("Users API" in x for x in seen)


def test_the_counts_are_taken_off_the_calling_thread_and_once_for_a_burst(tmp_path, monkeypatch):
    """dd's review (10-19): each watcher event used to count on the event loop. A burst of changes marks the room;
    one count runs, on the worker thread, once the burst is quiet."""
    world, root, pid = _world(tmp_path)
    calls = []
    real = data_docs.counts
    monkeypatch.setattr(data_docs, "counts", lambda p, cache=None: (calls.append(threading.current_thread().name), real(p, cache))[1])
    at = 20_000_000
    for k in range(200):
        world.file_changed(pid, str(root / "docs/api/users.json"), at + k)
        world.tick(at + k)
    assert calls == []                                         # still changing: not counted yet
    _settle(world, at + 200)
    assert len(calls) == 1 and calls[0].startswith("jui-viz-data-docs"), calls
