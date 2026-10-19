"""Pictures in the 応答の履歴 (2.3.4, requester 10-19: "画像ファイルが履歴にある場合はサムネイル表示とクリックで拡大表示").

history.py names a picture (the byte offset of its record's line, which picture of the record, its media type) and never
carries its base64; POST /api/history-image hands one picture's bytes to the page under the same checks as
/api/prompt. A fake projects folder under tmp_path; nothing reads the real ~/.claude.
"""
from __future__ import annotations

import asyncio
import base64
import json
import socket
import struct
import zlib

import pytest
from aiohttp.test_utils import TestClient, TestServer

from jui_cli.viz import export_demo
from jui_cli.viz.config import VizConfig
from jui_cli.viz.ingest import World
from jui_cli.viz.server import ServerContext, make_app
from jui_cli.viz.sources import history as H
from jui_cli.viz.sources.transcripts import project_dir_name
from jui_cli.viz.state import VizState

SID = "11111111-2222-4333-8444-555555555555"
SID2 = "22222222-3333-4444-8555-666666666666"
CWD = "/work/img-app"
CWD2 = "/work/img-other"
TOKEN = "t" * 43


def png(w=4, h=3, rgb=(200, 40, 40)) -> bytes:
    """A real PNG (stdlib only)."""
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + bytes(rgb) * w for _ in range(h))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


GIF = base64.b64decode("R0lGODlhAQABAIAAAP///wAAACH5BAEAAAAALAAAAAABAAEAAAICRAEAOw==")
PNG = png()
B64 = base64.b64encode(PNG).decode()


def img(data: bytes, media: str) -> dict:
    return {"type": "image", "source": {"type": "base64", "media_type": media, "data": base64.b64encode(data).decode()}}


def _user(content, ts="2026-10-19T09:00:00Z"):
    return {"type": "user", "timestamp": ts, "message": {"role": "user", "content": content}}


RECORDS = [
    _user("最初の指示"),
    _user([img(PNG, "image/png"), img(GIF, "image/gif"),
           {"type": "text", "text": "[Image: source: /nonexistent-viz-test/images/1.png, original 640x480]\nこの画面を見て"}]),
    {"type": "assistant", "timestamp": "2026-10-19T09:00:01Z", "message": {"id": "m1", "role": "assistant", "content": [
        {"type": "tool_use", "id": "tu1", "name": "Read", "input": {"file_path": "/x/shot.png"}}]}},
    _user([{"type": "tool_result", "tool_use_id": "tu1", "content": [img(PNG, "image/png")]}]),
    _user([img(b"<svg xmlns='http://www.w3.org/2000/svg'/>", "image/svg+xml"), img(GIF, "image/png")]),
]


def _write(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records))
    return path


def _path(tmp_path, sid=SID, cwd=CWD):
    return tmp_path / ".claude" / "projects" / project_dir_name(cwd) / f"{sid}.jsonl"


def _world(tmp_path):
    world = World(VizState())
    world.history_reader = H.reader(tmp_path / ".claude" / "projects")
    p1 = _write(_path(tmp_path), RECORDS)
    p2 = _write(_path(tmp_path, SID2, CWD2), [_user("別のセッション"), _user([img(png(rgb=(0, 0, 255)), "image/png")])])
    world.apply_hook({"hook_event_name": "SessionStart", "session_id": SID, "cwd": CWD, "transcript_path": str(p1)}, 1)
    world.apply_hook({"hook_event_name": "SessionStart", "session_id": SID2, "cwd": CWD2, "transcript_path": str(p2)}, 2)
    return world


def _line_starts(path):
    out, o = [], 0
    for line in path.read_bytes().split(b"\n")[:-1]:
        out.append(o)
        o += len(line) + 1
    return out


def test_a_picture_is_named_by_its_place_and_its_base64_is_never_in_the_items(tmp_path):
    world = _world(tmp_path)
    got = world.history(SID)
    starts = _line_starts(_path(tmp_path))
    imgs = [i for i in got["items"] if i["kind"] == "image"]
    assert [i.get("img") for i in imgs] == [{"off": starts[1], "n": 0, "type": "image/png"}, {"off": starts[1], "n": 1, "type": "image/gif"},
                                            None, {"off": starts[4], "n": 1, "type": "image/png"}]   # svg: a mark, no picture to ask for
    tool = next(i for i in got["items"] if i["kind"] == "tool")
    assert tool["imgs"] == [{"off": starts[3], "n": 0, "type": "image/png"}]
    dumped = json.dumps(got, ensure_ascii=False)
    assert B64 not in dumped and B64[:40] not in dumped
    user = next(i for i in got["items"] if i["kind"] == "user" and "この画面" in i["text"])
    assert user["gone"] == ["/nonexistent-viz-test/images/1.png"]


def test_a_picture_file_that_still_exists_is_not_marked_gone(tmp_path):
    f = tmp_path / "shot.png"
    f.write_bytes(PNG)
    assert H.gone_images(f"[Image: source: {f}, original 4x3] [Image: source: /nonexistent-viz-test/2.png]") == ["/nonexistent-viz-test/2.png"]
    assert H.gone_images("[Image: source: relative/x.png]") == []


def test_image_at_returns_the_bytes_and_refuses_everything_else(tmp_path):
    world = _world(tmp_path)
    s = _line_starts(_path(tmp_path))
    assert world.history_image(SID, s[1], 0) == (200, ("image/png", PNG))
    assert world.history_image(SID, s[1], 1) == (200, ("image/gif", GIF))
    assert world.history_image(SID, s[3], 0) == (200, ("image/png", PNG))              # inside a tool result
    assert world.history_image(SID, s[1], 2)[0] == 404                                  # no third picture
    assert world.history_image(SID, s[1] + 1, 0)[0] == 404                              # not the start of a line
    assert world.history_image(SID, s[0], 0)[0] == 404                                  # a line without pictures
    assert world.history_image(SID, s[2], 0)[0] == 404                                  # an assistant record
    assert world.history_image(SID, 10 ** 12, 0)[0] == 404                              # past the end
    assert world.history_image(SID, -1, 0)[0] == 404
    assert world.history_image(SID, s[4], 0)[0] == 415                                  # svg: not allowed
    assert world.history_image(SID, s[4], 1)[0] == 415                                  # says png, is a gif
    assert world.history_image("../../etc/passwd", 0, 0)[0] == 404                       # a path is not a robot
    assert world.history_image("nobody", s[1], 0)[0] == 404
    other = _line_starts(_path(tmp_path, SID2, CWD2))
    assert world.history_image(SID2, other[1], 0)[0] == 200
    got = world.history_image(SID, other[1], 0)                                          # the other session's place, asked of this robot
    assert got[0] != 200 or got[1] != world.history_image(SID2, other[1], 0)[1]


def test_a_picture_over_the_cap_is_refused(tmp_path, monkeypatch):
    world = _world(tmp_path)
    s = _line_starts(_path(tmp_path))
    monkeypatch.setattr(H, "IMAGE_MAX", 10)
    assert world.history_image(SID, s[1], 0)[0] == 413
    monkeypatch.setattr(H, "IMAGE_LINE_MAX", 20)
    assert world.history_image(SID, s[1], 0)[0] == 413


def test_the_snapshot_and_the_export_carry_no_picture(tmp_path):
    world = _world(tmp_path)
    assert world.history(SID)["items"]
    world.publish()
    assert B64[:40] not in json.dumps(world.state.snapshot(), ensure_ascii=False)
    out = tmp_path / "export"
    export_demo.export(out)
    assert [p for p in out.rglob("*") if p.is_file() and B64[:40].encode() in p.read_bytes()] == []


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _serve(world, calls):
    port = _free_port()
    own = f"127.0.0.1:{port}"

    async def run():
        ctx = ServerContext(config=VizConfig(pushIntervalMs=50), port=port, token=TOKEN, state=world.state, world=world,
                            publish=world.publish)
        client = TestClient(TestServer(make_app(ctx), host="127.0.0.1", port=port))
        await client.start_server()
        out = []
        try:
            for method, headers, body in calls(own):
                r = await client.request(method, "/api/history-image", headers=headers, data=body)
                out.append((r.status, r.headers.get("Content-Type", ""), await r.read(), dict(r.headers)))
        finally:
            await client.close()
        return out
    return asyncio.run(run())


def _ok_headers(own):
    return {"Host": own, "Origin": f"http://{own}", "X-Jui-Viz-Token": TOKEN, "Content-Type": "application/json"}


def test_the_route_gives_one_picture_to_the_page_and_nothing_to_anyone_else(tmp_path):
    world = _world(tmp_path)
    s = _line_starts(_path(tmp_path))
    good = json.dumps({"agentId": SID, "off": s[1], "n": 0})

    def calls(own):
        ok = _ok_headers(own)
        return [
            ("POST", ok, good),
            ("POST", {**ok, "X-Jui-Viz-Token": "x" * 43}, good),
            ("POST", {k: v for k, v in ok.items() if k != "X-Jui-Viz-Token"}, good),
            ("POST", {**ok, "Origin": "http://evil.example"}, good),
            ("POST", {k: v for k, v in ok.items() if k != "Origin"}, good),
            ("POST", {**ok, "Origin": f"http://localhost:{own.split(':')[1]}"}, good),
            ("POST", {**ok, "Host": f"localhost:{own.split(':')[1]}"}, good),
            ("GET", ok, None),
            ("POST", {**ok, "Content-Type": "text/plain"}, good),
            ("POST", ok, json.dumps({"agentId": SID, "off": str(s[1]), "n": 0})),
            ("POST", ok, json.dumps({"agentId": SID, "off": s[1], "n": True})),
            ("POST", ok, json.dumps({"agentId": SID, "off": s[1], "n": 9})),
            ("POST", ok, json.dumps({"agentId": SID, "off": s[1] + 3, "n": 0})),
            ("POST", ok, json.dumps({"agentId": "/etc/passwd", "off": 0, "n": 0})),
            ("POST", ok, json.dumps({"agentId": SID, "off": s[4], "n": 0})),
            ("POST", ok, json.dumps({"agentId": SID, "path": "/etc/passwd", "off": 0, "n": 0})),
            ("POST", ok, "x" * 9000),
        ]
    got = _serve(world, calls)
    status = [g[0] for g in got]
    assert status == [200, 401, 401, 403, 403, 403, 403, 405, 415, 400, 400, 404, 404, 404, 415, 404, 413], status
    assert got[0][1] == "image/png" and got[0][2] == PNG
    assert got[0][3].get("X-Content-Type-Options") == "nosniff" and got[0][3].get("Cache-Control") == "no-store"
    for st, _ct, body, _h in got[1:]:
        assert PNG not in body and b"PNG" not in body                                     # a refusal carries no picture


@pytest.mark.parametrize("media", ["image/png", "image/jpeg", "image/gif", "image/webp"])
def test_the_allowed_types_are_these_four(media):
    assert media in H.IMAGE_TYPES
    assert set(H.IMAGE_TYPES) == {"image/png", "image/jpeg", "image/gif", "image/webp"}
