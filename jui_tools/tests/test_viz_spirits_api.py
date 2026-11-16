"""The skill spirits the page is given (ticket 2026-10-21-jui-viz-skill-spirit): POST /api/spirits lists the models the
checks pass (the bundled originals and the person's own under <viz home>/spirits), POST /api/spirit-file hands one .glb
of a listed model, matched by id and file name against a scan made now. Both under the checks of /api/prompt; never a
path from the page. Everything runs on 127.0.0.1 with a temporary HOME.
"""
from __future__ import annotations

import asyncio
import json
import shutil
import socket

import pytest
from aiohttp.test_utils import TestClient, TestServer

from jui_cli.viz import paths, spirits
from jui_cli.viz.config import VizConfig
from jui_cli.viz.ingest import World
from jui_cli.viz.server import ServerContext, make_app
from jui_cli.viz.state import VizState

TOKEN = "t" * 43


@pytest.fixture()
def home(tmp_path, monkeypatch):
    for k in ("JUI_VIZ_HOME", "XDG_STATE_HOME"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    own = paths.viz_home() / "spirits"
    own.mkdir(parents=True)
    shutil.copytree(spirits.bundled_dir() / "ink-scholar", own / "mine")          # a good one of the person's
    broken = own / "broken"
    broken.mkdir()
    (broken / "spirit.glb").write_bytes(b"not a glb at all")                     # read, refused, never listed
    (own / "bad name!").mkdir()                                                    # not read
    return own


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _serve(calls):
    port = _free_port()
    own = f"127.0.0.1:{port}"
    world = World(VizState())

    async def run():
        ctx = ServerContext(config=VizConfig(pushIntervalMs=50), port=port, token=TOKEN, state=world.state, world=world,
                            publish=world.publish)
        client = TestClient(TestServer(make_app(ctx), host="127.0.0.1", port=port))
        await client.start_server()
        out = []
        try:
            for method, route, headers, body in calls(own):
                r = await client.request(method, route, headers=headers, data=body)
                out.append((r.status, r.headers.get("Content-Type", ""), await r.read(), dict(r.headers)))
        finally:
            await client.close()
        return out
    return asyncio.run(run())


def _ok(own):
    return {"Host": own, "Origin": f"http://{own}", "X-Jui-Viz-Token": TOKEN, "Content-Type": "application/json"}


def test_the_list_holds_the_models_that_pass_and_what_the_page_needs_of_them(home):
    (status, ctype, body, headers), = _serve(lambda own: [("POST", "/api/spirits", _ok(own), "{}")])
    assert status == 200 and ctype.startswith("application/json") and headers["Cache-Control"] == "no-store"
    models = {m["id"]: m for m in json.loads(body)["models"]}
    assert set(models) == {"bundled/gear-giant", "bundled/ink-scholar", "own/mine"}   # broken and "bad name!" left out
    mine = models["own/mine"]
    assert mine["source"] == "own" and set(mine["files"]) == {"spirit.glb", "robot-glasses.glb", "prop-scroll.glb"}
    assert mine["spec"]["version"] == 1 and "bubble" in mine["spec"] and isinstance(mine["weight"], (int, float))
    assert "dir" not in mine and str(home) not in body.decode()   # no path goes to the page


def test_a_listed_file_is_given_and_nothing_else_is(home):
    want = (home / "mine" / "spirit.glb").read_bytes()

    def calls(own):
        ok = _ok(own)
        ask = lambda model, file: ("POST", "/api/spirit-file", ok, json.dumps({"id": model, "file": file}))  # noqa: E731
        return [ask("own/mine", "spirit.glb"), ask("bundled/gear-giant", "robot-goggles.glb"),
                ask("own/mine", "spirit.json"), ask("own/mine", "../mine/spirit.glb"), ask("own/../own/mine", "spirit.glb"),
                ask("own/broken", "spirit.glb"), ask("elsewhere/mine", "spirit.glb"), ask("own/nope", "spirit.glb"),
                ("POST", "/api/spirit-file", ok, json.dumps({"id": "own/mine"}))]
    got = _serve(calls)
    status, ctype, body, headers = got[0]
    assert (status, ctype, body) == (200, "model/gltf-binary", want)
    assert headers["X-Content-Type-Options"] == "nosniff" and headers["Cache-Control"] == "no-store"
    assert got[1][0] == 200 and got[1][2][:4] == b"glTF"
    assert [g[0] for g in got[2:]] == [404, 404, 404, 404, 404, 404, 400]


def test_both_routes_refuse_what_api_prompt_refuses(home):
    def calls(own):
        ok = _ok(own)
        out = []
        for route, body in (("/api/spirits", "{}"), ("/api/spirit-file", json.dumps({"id": "own/mine", "file": "spirit.glb"}))):
            out += [("POST", route, {**ok, "X-Jui-Viz-Token": "x" * 43}, body),
                    ("POST", route, {k: v for k, v in ok.items() if k != "X-Jui-Viz-Token"}, body),
                    ("POST", route, {**ok, "Origin": "http://evil.example"}, body),
                    ("GET", route, ok, None),
                    ("POST", route, ok, "{" * 10)]
        return out
    got = _serve(calls)
    assert all(400 <= g[0] < 500 for g in got), [g[0] for g in got]
    assert not any(g[2][:4] == b"glTF" or b'"models"' in g[2] for g in got)
