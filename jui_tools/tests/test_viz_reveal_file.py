"""A file of the 応答の履歴 shown in Finder (POST /api/reveal-file, 2.3.12; requester 10-21: 「画像以外はファイル名出して
リンクっぽくして、押したらfinderでそのファイル選択してウィンドウ開く」; ticket 2026-10-21-jui-viz-hist-tool-row-shows-no-
image-when-closed).

The page names a file by the reference it already has — a SendUserFile call's file (the robot, the call's record, its
place) or an attachment (the session, the id, the extension) — never a path; the server resolves it by the same rule as
the picture it reads (history._sent_path, attachments' folder), under the checks of /api/prompt, and runs `open -R` on
it. `open` is a stand-in here that records its arguments; nothing is shown in the real Finder. The stage is
test_viz_history_sent_files.py's (a fake projects folder under tmp_path).
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

import pytest
from aiohttp.test_utils import TestClient, TestServer

from jui_cli.viz import server as srv
from jui_cli.viz.config import VizConfig
from jui_cli.viz.ingest import World
from jui_cli.viz.server import ServerContext, make_app
from jui_cli.viz.sources import history as H
from jui_cli.viz.state import VizState
from tests.test_viz_history_images import TOKEN, _free_port, _ok_headers, _write
from tests.test_viz_history_sent_files import CWD, SID, _files, _send, _transcript


def test_sent_reveal_at_gives_the_path_the_call_holds_any_kind_and_refuses_the_rest(tmp_path):
    d = _files(tmp_path)
    (d / "folder.md").mkdir()
    p, s = _transcript(tmp_path, d)
    fd = os.open(p, os.O_RDONLY)
    try:
        assert H.sent_reveal_at(fd, s[1], 1) == (200, str(d / "notes.md"))   # no picture: shown all the same
        assert H.sent_reveal_at(fd, s[1], 0) == (200, str(d / "a.png"))
        assert H.sent_reveal_at(fd, s[2], 1)[0] == 403                     # a symlink last
        assert H.sent_reveal_at(fd, s[2], 2)[0] == 403                     # a ".." part
        assert H.sent_reveal_at(fd, s[2], 4) == (404, "gone")
        assert H.sent_reveal_at(fd, s[3], 0)[0] == 404                     # a Read is no SendUserFile
        assert H.sent_reveal_at(fd, s[1] + 3, 0)[0] == 404                 # not the start of a line
    finally:
        os.close(fd)
    q = _write(tmp_path / "f.jsonl", [_send([str(d / "folder.md")])])
    fd = os.open(q, os.O_RDONLY)
    try:
        assert H.sent_reveal_at(fd, 0, 0)[0] == 403                       # a folder is no file to show
    finally:
        os.close(fd)


def test_a_relative_path_is_shown_from_the_calls_cwd(tmp_path):
    _files(tmp_path)
    rec = _send(["sent/notes.md"])
    rec["cwd"] = str(tmp_path)
    p = _write(tmp_path / "t.jsonl", [rec])
    fd = os.open(p, os.O_RDONLY)
    try:
        assert H.sent_reveal_at(fd, 0, 0) == (200, os.path.join(str(tmp_path), "sent/notes.md"))
    finally:
        os.close(fd)


@pytest.fixture()
def opened(tmp_path, monkeypatch):
    """`open` found first on PATH is a stand-in that writes its arguments, one call a line (the server starts "open"
    by name, as the real one is found); macOS as far as the route knows."""
    log = tmp_path / "opened.txt"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stand = bin_dir / "open"
    stand.write_text(f"#!{sys.executable} -I\nimport json, sys\nopen({str(log)!r}, 'a').write(json.dumps(sys.argv[1:]) + '\\n')\n")
    stand.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setattr(srv.sys, "platform", "darwin")
    monkeypatch.setenv("JUI_VIZ_HOME", str(tmp_path / "viz"))
    return lambda: [json.loads(x) for x in log.read_text().splitlines()] if log.exists() else []


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
                r = await client.request(method, "/api/reveal-file", headers=headers, data=body)
                out.append((r.status, await r.read()))
        finally:
            await client.close()
        return out
    return asyncio.run(run())


def test_the_route_shows_a_sent_file_and_an_attachment_and_nothing_else(tmp_path, opened):
    d = _files(tmp_path)
    p, s = _transcript(tmp_path, d)
    world = World(VizState())
    world.history_reader = H.reader(tmp_path / ".claude" / "projects")
    world.apply_hook({"hook_event_name": "SessionStart", "session_id": SID, "cwd": CWD, "transcript_path": str(p)}, 1)
    kept = world.attachments.save(SID, "memo.txt", "text/plain", b"a memo")
    fid, ext = kept["id"], kept["path"].rsplit(".", 1)[-1]
    sent = lambda off, n: json.dumps({"sent": {"agentId": SID, "off": off, "n": n}})   # noqa: E731
    att = lambda i, e: json.dumps({"attach": {"sessionId": SID, "id": i, "ext": e}})   # noqa: E731

    def calls(own):
        ok = _ok_headers(own)
        return [
            ("POST", ok, sent(s[1], 1)),                                            # 0 notes.md
            ("POST", ok, att(fid, ext)),                                            # 1 the kept memo
            ("POST", {**ok, "X-Jui-Viz-Token": "x" * 43}, sent(s[1], 1)),           # 2
            ("POST", {**ok, "Origin": "http://evil.example"}, sent(s[1], 1)),        # 3
            ("GET", ok, None),                                                      # 4
            ("POST", {**ok, "Content-Type": "text/plain"}, sent(s[1], 1)),          # 5
            ("POST", ok, sent(s[2], 4)),                                            # 6 gone
            ("POST", ok, sent(s[2], 1)),                                            # 7 a symlink
            ("POST", ok, sent(s[2], 2)),                                            # 8 a ".." part
            ("POST", ok, json.dumps({"path": str(d / "secret.txt")})),             # 9 a path is not taken
            ("POST", ok, json.dumps({"sent": {"agentId": "/etc/passwd", "off": 0, "n": 0}})),   # 10
            ("POST", ok, att("../../etc/passwd", "txt")),                          # 11
            ("POST", ok, att("0" * 16, "txt")),                                    # 12 no such attachment: gone
            ("POST", ok, json.dumps({"attach": {"sessionId": "../x", "id": fid, "ext": ext}})),   # 13
        ]
    got = _serve(world, calls)
    assert [g[0] for g in got] == [200, 200, 401, 403, 405, 415, 200, 403, 403, 400, 404, 400, 200, 200], [g[0] for g in got]
    assert json.loads(got[0][1]) == {"ok": True} and json.loads(got[1][1]) == {"ok": True}
    assert json.loads(got[6][1]) == {"gone": True} and json.loads(got[12][1]) == {"gone": True} and json.loads(got[13][1]) == {"gone": True}
    # only the two good ones reached `open`, each with -R and the path the server resolved (never one from the request)
    want_memo = str(tmp_path / "viz" / "uploads" / SID / f"{fid}.{ext}")
    assert opened() == [["-R", str(d / "notes.md")], ["-R", want_memo]]


def test_not_on_macos_nothing_is_run(tmp_path, opened, monkeypatch):
    d = _files(tmp_path)
    p, s = _transcript(tmp_path, d)
    world = World(VizState())
    world.history_reader = H.reader(tmp_path / ".claude" / "projects")
    world.apply_hook({"hook_event_name": "SessionStart", "session_id": SID, "cwd": CWD, "transcript_path": str(p)}, 1)
    monkeypatch.setattr(srv.sys, "platform", "linux")
    got = _serve(world, lambda own: [("POST", _ok_headers(own), json.dumps({"sent": {"agentId": SID, "off": s[1], "n": 1}}))])
    assert got[0][0] == 501 and opened() == []


def _tool(name, inp, use_id, ts="2026-10-20T09:20:00Z", cwd=CWD):
    return {"type": "assistant", "timestamp": ts, "cwd": cwd, "message": {"id": f"m-{use_id}", "role": "assistant", "content": [
        {"type": "tool_use", "id": use_id, "name": name, "input": inp}]}}


def test_a_file_tools_path_is_named_by_its_call_and_shown_by_the_rule_of_a_sent_file(tmp_path):
    """Read / Edit / Write / NotebookEdit (the ruling of 10-21): the row carries the file's name and the call's line, never the
    path; the server takes the path from that call's input by its id, resolved as a sent file's (.., relative from cwd,
    a symlink or a folder refused); any other tool, or an id that is not there, is nothing."""
    d = _files(tmp_path)
    recs = [_tool("Read", {"file_path": str(d / "notes.md")}, "r1"), _tool("Edit", {"file_path": str(d / "secret.txt"), "old_string": "a", "new_string": "b"}, "e1"),
            _tool("Write", {"file_path": "sent/notes.md", "content": "x"}, "w1", cwd=str(tmp_path)),
            _tool("NotebookEdit", {"notebook_path": str(d / "gone.ipynb"), "new_source": ""}, "n1"),
            _tool("Read", {"file_path": str(d / "link.png")}, "r2"), _tool("Read", {"file_path": f"{d}/../sent/notes.md"}, "r3"),
            _tool("Bash", {"command": f"cat {d / 'secret.txt'}"}, "b1")]
    p = _write(tmp_path / "t.jsonl", recs)
    starts = [0]
    for line in p.read_bytes().split(b"\n")[:-1]:
        starts.append(starts[-1] + len(line) + 1)
    items = []
    for off, line in zip(starts, p.read_bytes().split(b"\n")[:-1]):
        items += H.items_of(json.loads(line), {}, off)
    tools = [i for i in items if i["kind"] == "tool"]
    assert [t.get("file") for t in tools] == [{"name": "notes.md", "off": starts[0]}, {"name": "secret.txt", "off": starts[1]}, {"name": "notes.md", "off": starts[2]},
                                               {"name": "gone.ipynb", "off": starts[3]}, {"name": "link.png", "off": starts[4]}, {"name": "notes.md", "off": starts[5]}, None]
    assert str(d) not in json.dumps([t["file"] for t in tools if t.get("file")])
    fd = os.open(p, os.O_RDONLY)
    try:
        assert H.tool_file_reveal_at(fd, starts[0], "r1") == (200, str(d / "notes.md"))
        assert H.tool_file_reveal_at(fd, starts[1], "e1") == (200, str(d / "secret.txt"))
        assert H.tool_file_reveal_at(fd, starts[2], "w1") == (200, os.path.join(str(tmp_path), "sent/notes.md"))
        assert H.tool_file_reveal_at(fd, starts[3], "n1") == (404, "gone")
        assert H.tool_file_reveal_at(fd, starts[4], "r2")[0] == 403     # a symlink last
        assert H.tool_file_reveal_at(fd, starts[5], "r3")[0] == 403     # a ".." part
        assert H.tool_file_reveal_at(fd, starts[6], "b1")[0] == 404     # a Bash call names no file
        assert H.tool_file_reveal_at(fd, starts[0], "e1")[0] == 404     # another call's id on this line
        assert H.tool_file_reveal_at(fd, starts[0] + 2, "r1")[0] == 404  # not the start of a line
    finally:
        os.close(fd)


def test_the_route_shows_a_file_tools_file_by_the_call_and_never_a_path(tmp_path, opened):
    d = _files(tmp_path)
    recs = [_tool("Read", {"file_path": str(d / "notes.md")}, "r1"), _tool("Read", {"file_path": str(d / "gone.md")}, "r2")]
    p = _write(tmp_path / ".claude" / "projects" / "-work-sent-app" / f"{SID}.jsonl", recs)
    world = World(VizState())
    world.history_reader = H.reader(tmp_path / ".claude" / "projects")
    world.apply_hook({"hook_event_name": "SessionStart", "session_id": SID, "cwd": CWD, "transcript_path": str(p)}, 1)
    second = len(p.read_bytes().split(b"\n")[0]) + 1
    tool = lambda off, i, **kw: json.dumps({"tool": {"agentId": SID, "off": off, "id": i, **kw}})   # noqa: E731
    got = _serve(world, lambda own: [("POST", _ok_headers(own), tool(0, "r1")), ("POST", _ok_headers(own), tool(second, "r2")),
                                     ("POST", _ok_headers(own), tool(0, "r1", path=str(d / "secret.txt"))), ("POST", _ok_headers(own), tool(0, "nope"))])
    assert [g[0] for g in got] == [200, 200, 200, 404], [g[0] for g in got]
    assert json.loads(got[0][1]) == {"ok": True} and json.loads(got[1][1]) == {"gone": True}
    assert opened() == [["-R", str(d / "notes.md")], ["-R", str(d / "notes.md")]]   # the extra path key is not read
