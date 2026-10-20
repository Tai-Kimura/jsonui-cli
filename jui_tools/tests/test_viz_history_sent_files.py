"""Pictures a session sent with SendUserFile, in the 応答の履歴 (ticket 2026-10-20-jui-viz-history-senduserfile-image-
no-thumb; requester: 「これがサムネイルでないからここで見れないね」).

Measured 10-20 on this machine's transcripts: SendUserFile's input holds {files: [absolute paths], caption, ...}, its
result only text — never the picture. So history.py names a sent file by (the call's line, its place among the
record's files) and POST /api/history-file reads only the path that call holds, from disk, under the checks of
/api/prompt. A fake projects folder and files under tmp_path; nothing reads the real ~/.claude.
"""
from __future__ import annotations

import asyncio
import json
import os

import pytest
from aiohttp.test_utils import TestClient, TestServer

from jui_cli.viz.config import VizConfig
from jui_cli.viz.ingest import World
from jui_cli.viz.server import ServerContext, make_app
from jui_cli.viz.sources import history as H
from jui_cli.viz.state import VizState
from tests.test_viz_history_images import GIF, PNG, TOKEN, _free_port, _line_starts, _ok_headers, _path, _user, _write, png

SID = "33333333-4444-4555-8666-777777777777"
CWD = "/work/sent-app"


def _send(files, caption=None, name="SendUserFile", ts="2026-10-20T09:10:07Z", extra=()):
    inp = {"files": files, "status": "normal", "display": "render"}
    if caption is not None:
        inp["caption"] = caption
    return {"type": "assistant", "timestamp": ts, "cwd": CWD, "message": {"id": f"m-{ts}", "role": "assistant", "content": [
        {"type": "tool_use", "id": f"tu-{ts}", "name": name, "input": inp}, *extra]}}


def _files(tmp_path):
    d = tmp_path / "sent"
    d.mkdir()
    (d / "a.png").write_bytes(PNG)
    (d / "b.gif").write_bytes(GIF)
    (d / "notes.md").write_text("# notes")
    (d / "fake.png").write_bytes(b"<html>not a png</html>")
    (d / "secret.txt").write_text("secret")
    (d / "png.txt").write_bytes(PNG)                       # a picture's bytes under another name
    os.symlink(d / "a.png", d / "link.png")
    return d


def _transcript(tmp_path, d):
    recs = [
        _user("最初の指示"),
        _send([str(d / "a.png"), str(d / "notes.md"), str(d / "b.gif"), str(d / "png.txt")], caption="見本の画像"),
        _send([str(d / "fake.png"), str(d / "link.png"), f"{d}/../sent/a.png", "sent/a.png", str(d / "gone.png")], ts="2026-10-20T09:11:00Z",
              extra=[{"type": "tool_use", "id": "tu-second", "name": "SendUserFile", "input": {"files": [str(d / "b.gif")]}}]),
        _send([str(d / "a.png")], name="Read", ts="2026-10-20T09:12:00Z"),
    ]
    p = _write(_path(tmp_path, SID, CWD), recs)
    return p, _line_starts(p)


def test_a_sent_file_is_named_by_its_call_and_place_and_its_path_is_not_in_the_item(tmp_path):
    d = _files(tmp_path)
    p, s = _transcript(tmp_path, d)
    results, items = {}, []
    for off, line in zip(s, p.read_bytes().split(b"\n")):
        items += H.items_of(json.loads(line), results, off)
    tools = [i for i in items if i["kind"] == "tool"]
    first = tools[0]
    assert first["sent"] == [{"n": 0, "name": "a.png", "image": True, "off": s[1]}, {"n": 1, "name": "notes.md", "image": False, "off": s[1]},
                             {"n": 2, "name": "b.gif", "image": True, "off": s[1]}, {"n": 3, "name": "png.txt", "image": False, "off": s[1]}]
    assert first["caption"] == "見本の画像"
    # two calls in one record: the second's files go on counting from the first's
    assert [f["n"] for f in tools[1]["sent"]] == [0, 1, 2, 3, 4] and tools[2]["sent"] == [{"n": 5, "name": "b.gif", "image": True, "off": s[2]}]
    assert "sent" not in tools[3]                                  # a Read with files: no sent file
    assert str(d) not in json.dumps([{k: v for k, v in t.items() if k not in ("in",)} for t in tools])


def test_sent_file_at_reads_only_the_path_the_call_holds_and_refuses_the_rest(tmp_path):
    d = _files(tmp_path)
    p, s = _transcript(tmp_path, d)
    fd = os.open(p, os.O_RDONLY)
    try:
        assert H.sent_file_at(fd, s[1], 0) == (200, ("image/png", PNG))
        assert H.sent_file_at(fd, s[1], 2) == (200, ("image/gif", GIF))
        assert H.sent_file_at(fd, s[1], 1)[0] == 415                     # notes.md: no picture
        assert H.sent_file_at(fd, s[1], 3)[0] == 415                     # png.txt: a picture's bytes, not a picture's name
        assert H.sent_file_at(fd, s[1], 4)[0] == 404                     # no 5th file in that call
        assert H.sent_file_at(fd, s[2], 0)[0] == 415                     # fake.png: a png's name, other bytes
        assert H.sent_file_at(fd, s[2], 1)[0] == 403                     # a symlink last
        assert H.sent_file_at(fd, s[2], 2)[0] == 403                     # a ".." part
        assert H.sent_file_at(fd, s[2], 4) == (404, "gone")              # no longer there
        assert H.sent_file_at(fd, s[2], 5) == (200, ("image/gif", GIF))  # the second call in the record
        assert H.sent_file_at(fd, s[3], 0)[0] == 404                     # a Read is no SendUserFile
        assert H.sent_file_at(fd, s[0], 0)[0] == 404                     # a user record
        assert H.sent_file_at(fd, s[1] + 3, 0)[0] == 404                 # not the start of a line
        assert H.sent_file_at(fd, s[1], -1)[0] == 404
    finally:
        os.close(fd)


def test_a_relative_path_is_read_from_the_calls_cwd(tmp_path):
    d = _files(tmp_path)
    rec = _send(["sent/a.png"])
    rec["cwd"] = str(tmp_path)
    p = _write(tmp_path / "t.jsonl", [rec])
    fd = os.open(p, os.O_RDONLY)
    try:
        assert H.sent_file_at(fd, 0, 0) == (200, ("image/png", PNG))
    finally:
        os.close(fd)
    assert (d / "a.png").exists()


def test_a_sent_file_over_the_cap_is_refused(tmp_path, monkeypatch):
    d = _files(tmp_path)
    p, s = _transcript(tmp_path, d)
    monkeypatch.setattr(H, "SENT_FILE_MAX", len(PNG) - 1)
    fd = os.open(p, os.O_RDONLY)
    try:
        assert H.sent_file_at(fd, s[1], 0)[0] == 413
    finally:
        os.close(fd)


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
                r = await client.request(method, "/api/history-file", headers=headers, data=body)
                out.append((r.status, r.headers.get("Content-Type", ""), await r.read(), dict(r.headers)))
        finally:
            await client.close()
        return out
    return asyncio.run(run())


def test_the_route_gives_a_sent_picture_to_the_page_and_says_gone_without_an_error(tmp_path):
    d = _files(tmp_path)
    p, s = _transcript(tmp_path, d)
    world = World(VizState())
    world.history_reader = H.reader(tmp_path / ".claude" / "projects")
    world.apply_hook({"hook_event_name": "SessionStart", "session_id": SID, "cwd": CWD, "transcript_path": str(p)}, 1)
    good = json.dumps({"agentId": SID, "off": s[1], "n": 0})

    def calls(own):
        ok = _ok_headers(own)
        return [
            ("POST", ok, good),
            ("POST", {**ok, "X-Jui-Viz-Token": "x" * 43}, good),
            ("POST", {**ok, "Origin": "http://evil.example"}, good),
            ("GET", ok, None),
            ("POST", {**ok, "Content-Type": "text/plain"}, good),
            ("POST", ok, json.dumps({"agentId": SID, "off": s[2], "n": 4})),        # gone
            ("POST", ok, json.dumps({"agentId": SID, "off": s[2], "n": 1})),        # a symlink
            ("POST", ok, json.dumps({"agentId": SID, "path": str(d / "secret.txt"), "off": s[1], "n": 1})),   # a path is not taken
            ("POST", ok, json.dumps({"agentId": "/etc/passwd", "off": 0, "n": 0})),
        ]
    got = _serve(world, calls)
    assert [g[0] for g in got] == [200, 401, 403, 405, 415, 200, 403, 415, 404], [g[0] for g in got]
    assert got[0][1] == "image/png" and got[0][2] == PNG and got[0][3].get("X-Content-Type-Options") == "nosniff"
    assert got[5][1].startswith("application/json") and json.loads(got[5][2]) == {"gone": True}
    for st, _ct, body, _h in got[1:]:
        assert PNG not in body and b"secret" not in body


def test_a_folder_or_a_fifo_named_png_and_a_riff_that_is_no_webp_are_refused(tmp_path):
    """dd's U1 and U2 (10-20): a path named like a picture that is a folder or a FIFO is no file to read (403, never an
    exception or a read that waits); a RIFF whose type is not WEBP (a WAVE named .webp) is no picture (415)."""
    d = tmp_path / "odd"
    d.mkdir()
    (d / "folder.png").mkdir()
    os.mkfifo(d / "pipe.png")
    (d / "sound.webp").write_bytes(b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 24)
    (d / "real.webp").write_bytes(b"RIFF\x24\x00\x00\x00WEBPVP8 " + b"\x00" * 24)
    p = _write(tmp_path / "t.jsonl", [_send([str(d / "folder.png"), str(d / "pipe.png"), str(d / "sound.webp"), str(d / "real.webp")])])
    fd = os.open(p, os.O_RDONLY)
    try:
        assert H.sent_file_at(fd, 0, 0) == (403, "not a file to read")
        assert H.sent_file_at(fd, 0, 1) == (403, "not a file to read")
        assert H.sent_file_at(fd, 0, 2) == (415, "not a picture")
        assert H.sent_file_at(fd, 0, 3)[0] == 200
    finally:
        os.close(fd)
