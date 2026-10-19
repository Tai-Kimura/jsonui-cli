"""POST /api/call-command (the call button, 2.3.5): a real `jui viz start` in a temporary HOME on a free port. The route
makes the line and runs nothing; the line the page would show, run in zsh and bash with a shell function in place of
the CLI, hands over exactly the project's folder and the four arguments. Every check of /api/prompt refuses on its own."""
from __future__ import annotations

import json
import os
import subprocess

import pytest

from jui_cli.viz import callcmd as C
from tests.test_viz_clock_out import DROP, Viz

CALL_MAX_BODY = 32_768   # written out so a change of the constant shows


@pytest.fixture()
def viz(tmp_path, monkeypatch):
    home = tmp_path / "home"
    for k in (*DROP, "JUI_VIZ_MANAGED_SETTINGS"):
        monkeypatch.delenv(k, raising=False)
    settings = tmp_path / "managed-settings.json"
    settings.write_text(json.dumps({"channelsEnabled": True, "allowedChannelPlugins": ["jui-viz@jsonui"]}))
    monkeypatch.setenv("JUI_VIZ_MANAGED_SETTINGS", str(settings))
    monkeypatch.setenv("HOME", str(home))
    v = Viz(home)
    v.settings = settings
    try:
        yield v
    finally:
        v.stop()


def _project(viz, folder) -> str:
    folder.mkdir(parents=True, exist_ok=True)
    status, _ = viz.local("POST", "/hook", {"hook_event_name": "SessionStart", "session_id": "c2000000-0000-4000-8000-000000000001",
                                             "cwd": str(folder), "source": "startup"})
    assert status in (200, 204)
    viz.wait(lambda: viz.snapshot()["slices"].get("projects"), "the project")
    return viz.snapshot()["slices"]["projects"][0]["id"]


def _call(viz, body: dict | bytes, method="POST", **over):
    data = body if isinstance(body, bytes) else json.dumps(body).encode()
    status, text = viz.raw(method, "/api/call-command", viz.page_headers(**over), data)
    return status, (json.loads(text) if text.strip().startswith("{") else text)


def _argv(shell, line, tmp_path) -> list[str]:
    out = tmp_path / "argv.bin"
    out.unlink(missing_ok=True)
    defs = f"claude() {{ printf '%s\\0' \"$PWD\" \"$@\" > {C.sh_quote(str(out))}; }}"
    base = [shell, "-f"] if shell.endswith("zsh") else [shell, "--norc", "--noprofile"]
    subprocess.run(base + ["-c", defs + "\n" + line], env={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path)}, capture_output=True, timeout=20)
    return out.read_bytes().decode("utf-8").split("\0")[:-1]


@pytest.mark.parametrize("shell", [s for s in ("/bin/zsh", "/bin/bash") if os.path.exists(s)])
def test_the_line_hands_over_the_folder_and_four_arguments(viz, tmp_path, shell):
    folder = tmp_path / "work" / "my app's \"$(touch PWNED)\" !x"
    pid = _project(viz, folder)
    name, role = "-n'; touch PWNED; '", "$(touch PWNED)\nline two"
    status, res = _call(viz, {"projectId": pid, "name": name, "role": role})
    assert status == 200 and res["ok"] and res["flag"] == "--channels", res
    assert res["root"] == str(folder)
    got = _argv(shell, res["command"], tmp_path)
    assert got == [os.path.realpath(folder), "--channels", "plugin:jui-viz@jsonui", f"--name={name}", C.prompt_of(name, role)]
    assert not list(tmp_path.rglob("PWNED"))


def test_the_flag_follows_the_managed_settings_read_each_time(viz, tmp_path):
    pid = _project(viz, tmp_path / "work" / "app")
    viz.settings.write_text(json.dumps({"channelsEnabled": False, "allowedChannelPlugins": ["jui-viz@jsonui"]}))
    status, res = _call(viz, {"projectId": pid, "name": "n", "role": ""})
    assert status == 200 and res["flag"] == "--dangerously-load-development-channels"
    viz.settings.unlink()
    assert _call(viz, {"projectId": pid, "name": "n", "role": ""})[1]["flag"] == "--dangerously-load-development-channels"


def test_what_cannot_make_a_line_says_why(viz, tmp_path):
    pid = _project(viz, tmp_path / "work" / "app")
    for name, role, why in [("", "", "担当名"), ("a\0b", "", "NUL"), ("two\nlines", "", "1 行"), ("a", "r\0", "NUL")]:
        status, res = _call(viz, {"projectId": pid, "name": name, "role": role})
        assert status == 400 and not res["ok"] and why in res["why"] and "command" not in res
    assert _call(viz, {"projectId": "nope", "name": "n", "role": ""})[0] == 404
    assert _call(viz, {"name": "n"})[0] == 400


def test_every_check_of_the_page_route_refuses(viz, tmp_path):
    pid = _project(viz, tmp_path / "work" / "app")
    ok = {"projectId": pid, "name": "n", "role": ""}
    assert _call(viz, ok, **{"X-Jui-Viz-Token": None})[0] == 401
    assert _call(viz, ok, **{"X-Jui-Viz-Token": "x" * 43})[0] == 401
    for origin in ("http://evil.example", f"http://localhost:{viz.port}", "null", None):
        assert _call(viz, ok, Origin=origin)[0] == 403
    assert _call(viz, ok, Host=f"localhost:{viz.port}")[0] == 403
    for method in ("GET", "PUT"):
        assert _call(viz, ok, method=method)[0] == 405
    for ctype in ("text/plain", "application/x-www-form-urlencoded", None):
        assert _call(viz, ok, **{"Content-Type": ctype})[0] == 415
    big = json.dumps({**ok, "role": "x" * CALL_MAX_BODY}).encode()
    assert _call(viz, big)[0] == 413
    assert _call(viz, ok)[0] == 200


def test_it_starts_nothing_and_writes_nothing(tmp_path, monkeypatch):
    """In process (no pollers run): while the route answers, every way to start a process raises, and no file appears
    anywhere under the test's folder, the project's folder included."""
    import asyncio
    import socket

    from aiohttp.test_utils import TestClient, TestServer

    from jui_cli.viz.config import VizConfig
    from jui_cli.viz.ingest import World
    from jui_cli.viz.server import ServerContext, make_app
    from jui_cli.viz.state import VizState

    folder = tmp_path / "work" / "app"
    folder.mkdir(parents=True)
    monkeypatch.setenv("JUI_VIZ_MANAGED_SETTINGS", str(tmp_path / "none.json"))
    world = World(VizState())
    world.apply_hook({"hook_event_name": "SessionStart", "session_id": "c2000000-0000-4000-8000-000000000002", "cwd": str(folder),
                      "source": "startup"}, 1)
    world.publish()
    pid = world.state.snapshot()["slices"]["projects"][0]["id"]
    with socket.socket() as so:
        so.bind(("127.0.0.1", 0))
        port = so.getsockname()[1]
    own, token = f"127.0.0.1:{port}", "t" * 43
    started = []

    def refuse(*a, **k):
        started.append(a[:1])
        raise AssertionError("the call route started a process")
    for mod, name in ((subprocess, "Popen"), (os, "system"), (os, "posix_spawn"), (os, "posix_spawnp"), (os, "fork"),
                      (asyncio, "create_subprocess_exec"), (asyncio, "create_subprocess_shell")):
        monkeypatch.setattr(mod, name, refuse)
    before = sorted(p.as_posix() for p in tmp_path.rglob("*"))

    async def run():
        ctx = ServerContext(config=VizConfig(), port=port, token=token, state=world.state, world=world, publish=world.publish)
        client = TestClient(TestServer(make_app(ctx), host="127.0.0.1", port=port))
        await client.start_server()
        try:
            out = []
            for _ in range(5):
                r = await client.post("/api/call-command", headers={"Host": own, "Origin": f"http://{own}", "X-Jui-Viz-Token": token,
                                      "Content-Type": "application/json"}, data=json.dumps({"projectId": pid, "name": "n'; touch PWNED; '", "role": "$(touch PWNED)"}))
                out.append((r.status, await r.json()))
            return out
        finally:
            await client.close()
    got = asyncio.run(run())
    assert all(st == 200 and body["ok"] for st, body in got), got
    assert started == []
    assert sorted(p.as_posix() for p in tmp_path.rglob("*")) == before
