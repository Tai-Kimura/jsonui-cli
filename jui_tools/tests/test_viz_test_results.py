"""Saved test results (sources/test_results.py): the drivers write one results file per run to a default
folder, jui viz reads them, so a run's pass / fail survives a server restart and runs the server never saw
show up (10-18, requester: "the drivers write, viz reads").

HOME is a temporary folder in every test that starts a server, with a config.json naming a free port, and
JUI_VIZ_HOME / XDG_STATE_HOME / JSONUI_TEST_RESULTS_DIR / JSONUI_TEST_PROGRESS_DIR (a plugin session carries it) are
removed from the child's environment: nothing
here reads the real results folder or reaches the server on the default port.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import pytest

from jui_cli.viz.ingest import World
from jui_cli.viz.sources import test_results as tr
from jui_cli.viz.state import VizState

REPO = Path(__file__).resolve().parents[2]
JUI = REPO / "jui_tools" / "bin" / "jui"
RUN_A = "3f2a1b4c-0d5e-4f60-8a71-92b3c4d5e6f7"
RUN_B = "4f2a1b4c-0d5e-4f60-8a71-92b3c4d5e6f7"


def _name(at: float, run: str) -> str:
    stamp = datetime.fromtimestamp(at, timezone.utc).strftime("%Y%m%dT%H%M%S.%f")[:-3]
    return f"{stamp}Z-{run}.json"


def _results(platform: str, run: str, app: str, file: str, cases: dict, test: str = "login") -> dict:
    return {"format": "jsonui-test-results", "version": 1, "platform": platform, "generatedAt": "2026-10-18T09:00:00Z",
            "run": run, "app": app,
            "suites": [{"suiteName": test, "file": file, "results": [
                {"testName": test, "caseName": c, "status": s, "durationMs": 1} for c, s in cases.items()]}]}


def _put(folder: Path, at: float, data: dict) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / _name(at, data["run"])
    path.write_text(json.dumps(data))
    return path


def _project(root: Path, config: dict | None = None, test: str = "login") -> Path:
    (root / "docs/screens/json").mkdir(parents=True)
    (root / "docs/screens/layouts").mkdir(parents=True)
    (root / "tests/screens").mkdir(parents=True)
    (root / "jui.config.json").write_text(json.dumps(config or {}))
    (root / "docs/screens/json/login.spec.json").write_text(json.dumps({"metadata": {"name": "Login", "layoutFile": "login"}}))
    (root / "docs/screens/layouts/login.json").write_text(json.dumps({"type": "View", "id": "root"}))
    (root / "tests/screens/login.test.json").write_text(json.dumps({"source": {"layout": "docs/screens/layouts/login.json"},
                                                                      "cases": [{"name": "ok"}, {"name": "ng"}]}))
    old = time.time() - 3600  # the spec and layout were written an hour ago
    for f in ("docs/screens/json/login.spec.json", "docs/screens/layouts/login.json"):
        os.utime(root / f, (old, old))
    return root


def _world(*roots: Path) -> tuple[World, VizState]:
    state = VizState()
    world = World(state)
    for i, root in enumerate(roots):
        world.apply_hook({"session_id": f"s{i}", "cwd": str(root), "hook_event_name": "SessionStart"}, 0)
    world.publish()
    return world, state


def _login(state: VizState, project_root: Path | None = None) -> dict:
    specs = [s for s in state.slices["specs"] if s["name"] == "Login"]
    if project_root is not None:
        specs = [s for s in specs if s["projectId"].endswith(project_root.name) or True]
    return specs[0]["tests"]


# ---------------------------------------------------------------- where


def test_results_base_follows_only_an_absolute_override(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv(tr.BASE_ENV, raising=False)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "xdg"))  # deliberately not followed: the simulator cannot see it
    assert tr.results_base() == tmp_path / ".local/state/jsonui-test/results"
    monkeypatch.setenv(tr.BASE_ENV, "relative/dir")
    assert tr.results_base() == tmp_path / ".local/state/jsonui-test/results"
    monkeypatch.setenv(tr.BASE_ENV, str(tmp_path / "elsewhere"))
    assert tr.results_base() == tmp_path / "elsewhere"


def test_the_name_rule_and_the_time_in_it():
    at = datetime(2026, 10, 18, 9, 0, 0, 123000, timezone.utc).timestamp()
    name = _name(at, RUN_A)
    assert name == f"20261018T090000.123Z-{RUN_A}.json"
    assert tr.name_time(name) == pytest.approx(at)
    for bad in (f".{name}.tmp", name.upper(), f"x{name}", name.replace(".json", ".jsonl"), "results.json"):
        assert tr.name_time(bad) is None
    assert tr.sanitize("com.example.app") == "com.example.app"
    assert tr.sanitize("a/b c") == "a_b_c" and tr.sanitize("..") == "unknown" and tr.sanitize("") == "unknown"


def test_the_shelf_reads_every_app_folder_and_only_files_it_can_trust(tmp_path):
    now = time.time()
    _put(tmp_path / "ios/dev.app.UITests.xctrunner", now, _results("ios", RUN_A, "dev.app.UITests.xctrunner", "screens/login.test.json", {"ok": "passed"}))
    _put(tmp_path / "web/my-web", now, _results("web", RUN_B, "my-web", "screens/login.test.json", {"ng": "failed"}))
    _put(tmp_path / "android/emulator-5554/com.example.app", now, _results("android", RUN_A, "com.example.app", "screens/login.test.json", {"ok": "skipped"}))
    (tmp_path / "web/my-web/results.json").write_text("{}")                     # not the driver's name: never read
    (tmp_path / "web/my-web" / _name(now, "5f2a1b4c-0d5e-4f60-8a71-92b3c4d5e6f7")).write_text("{half")   # unreadable
    (tmp_path / "ios/dev.app.UITests.xctrunner" / _name(now, "6f2a1b4c-0d5e-4f60-8a71-92b3c4d5e6f7")).write_text(json.dumps({"format": "other"}))
    shelf = tr.ResultShelf(tmp_path)
    rows = shelf.scan()
    assert sorted((r["platform"], r["case"], r["status"]) for r in rows) == [
        ("android", "ok", "skipped"), ("ios", "ok", "passed"), ("web", "ng", "failed")]
    assert shelf.bad == 2
    assert {r["file"] for r in rows} == {"screens/login.test.json"}
    assert shelf.scan() == rows  # unchanged files are not read again, and give the same rows


def test_pruning_keeps_the_newest_500_drops_the_old_and_touches_nothing_else(tmp_path):
    folder = tmp_path / "web/app"
    sibling = tmp_path / "web/other"
    now = time.time()
    names = [_put(folder, now - i, _results("web", f"{i:08x}-0d5e-4f60-8a71-92b3c4d5e6f7", "app", "f", {})).name for i in range(503)]
    old = _put(folder, now - 15 * 86400, _results("web", RUN_A, "app", "f", {})).name
    (folder / "notes.json").write_text("{}")
    (folder / f".{names[0]}.tmp").write_text("{}")
    keep_sibling = _put(sibling, now - 30 * 86400, _results("web", RUN_B, "other", "f", {}))
    assert tr.prune(folder, now) == 4
    left = sorted(p.name for p in folder.iterdir())
    assert old not in left and "notes.json" in left and f".{names[0]}.tmp" in left
    assert sorted(n for n in left if tr.NAME.match(n)) == sorted(names[:500])
    assert keep_sibling.exists()


# ---------------------------------------------------------------- tied to a spec


def test_a_saved_result_shows_before_any_progress_and_says_when_it_may_be_stale(tmp_path):
    root = _project(tmp_path / "app")
    world, state = _world(root)
    assert _login(state) == {"total": 2, "needed": 2, "passed": 0, "failed": 0, "running": False}
    shelf = tmp_path / "shelf"
    saved = time.time()
    _put(shelf / "web/app", saved, _results("web", RUN_A, "app", "screens/login.test.json", {"ok": "passed", "ng": "failed"}))
    world.apply_saved_results(tr.ResultShelf(shelf).scan())
    world.publish()
    tests = _login(state)
    assert (tests["passed"], tests["failed"]) == (1, 1) and "maybeStale" not in tests
    # the layout changed after the run (or a checkout moved it): a second later, said outright. Not utime(path, None):
    # Linux stamps a file from its coarse clock, a tick behind time.time() (up to 1.75 ms measured), so "now" can read
    # as before the result's own millisecond (ticket 2026-10-24-viz-test-results-maybestale-arm-flaky-on-ci)
    os.utime(root / "docs/screens/layouts/login.json", (saved + 1, saved + 1))
    world.apply_saved_results(tr.ResultShelf(shelf).scan())
    world._dirty.add("specs")
    world.publish()
    assert _login(state)["maybeStale"] is True


def test_may_be_stale_only_for_a_change_after_the_results_millisecond(tmp_path):
    """The rule at its edge: a result's time is its file name's millisecond; the spec or layout changed in that same
    millisecond is not after it, one millisecond later is (and a millisecond before is not)."""
    root = _project(tmp_path / "app")
    world, state = _world(root)
    saved = int(time.time()) - 100 + 0.25            # a whole millisecond: the name says .250
    at_ns = int(round(saved * 1000)) * 1_000_000
    shelf = tmp_path / "shelf"
    _put(shelf / "web/app", saved, _results("web", RUN_A, "app", "screens/login.test.json", {"ok": "passed"}))
    layout = root / "docs/screens/layouts/login.json"
    got = {}
    for name, ns in (("same", at_ns), ("later", at_ns + 1_000_000), ("earlier", at_ns - 1_000_000), ("a µs later", at_ns + 1000)):
        os.utime(layout, ns=(ns, ns))
        world.apply_saved_results(tr.ResultShelf(shelf).scan())
        world._dirty.add("specs")
        world.publish()
        got[name] = _login(state).get("maybeStale", False)
    assert got == {"same": False, "later": True, "earlier": False, "a µs later": True}, got


def test_a_run_seen_live_and_then_saved_is_counted_once_and_newest_wins(tmp_path):
    root = _project(tmp_path / "app")
    world, state = _world(root)
    cmd = "npx playwright test"
    world.apply_hook({"session_id": "s0", "cwd": str(root), "hook_event_name": "PreToolUse", "tool_name": "Bash",
                      "tool_use_id": "b", "tool_input": {"command": cmd}}, 100)
    t0 = int(time.time() * 1000)

    def rec(event, t, **kw):
        return {"v": 1, "t": t, "platform": "web", "run": RUN_A, "event": event, **kw}

    # An older saved failure of the same case, from before this run: the live pass is newer and wins.
    early = tmp_path / "early"
    _put(early / "web/app", t0 / 1000 - 60, _results("web", RUN_B, "app", "screens/login.test.json", {"ok": "failed"}))
    world.apply_saved_results(tr.ResultShelf(early).scan())
    for r in (rec("run_start", t0, files=1),
              rec("case_start", t0 + 1, file="screens/login.test.json", test="login", case="ok", attempt=1),
              rec("case_end", t0 + 2, file="screens/login.test.json", test="login", case="ok", attempt=1, status="passed", durationMs=1)):
        world.apply_progress(r, "web", None, t0)
    shelf = tmp_path / "shelf"
    _put(shelf / "web/app", t0 / 1000 + 1, _results("web", RUN_A, "app", "screens/login.test.json", {"ok": "passed"}))
    world.apply_saved_results(tr.ResultShelf(shelf).scan())
    world.publish()
    assert (_login(state)["passed"], _login(state)["failed"]) == (1, 0)
    # A later run of the same case failed: the newest outcome is the one shown.
    _put(shelf / "web/app", t0 / 1000 + 60, _results("web", RUN_B, "app", "screens/login.test.json", {"ok": "failed"}))
    world.apply_saved_results(tr.ResultShelf(shelf).scan())
    world.publish()
    assert (_login(state)["passed"], _login(state)["failed"]) == (0, 1)


def test_a_test_file_two_apps_have_is_not_guessed_but_an_android_package_ties_it(tmp_path):
    bar = _project(tmp_path / "bar", {"test": {"artifacts": {"android": {"appId": "com.example.bar"}}}})
    client = _project(tmp_path / "client", {"test": {"artifacts": {"android": {"appId": "com.example.client"}}}})
    world, state = _world(bar, client)
    shelf = tmp_path / "shelf"
    _put(shelf / "web/x", time.time(), _results("web", RUN_A, "x", "screens/login.test.json", {"ok": "passed"}))
    _put(shelf / "ios/x.xctrunner", time.time(), _results("ios", RUN_B, "x.xctrunner", "screens/login.test.json", {"ok": "passed"}))
    world.apply_saved_results(tr.ResultShelf(shelf).scan())
    world.publish()
    by_root = {s["projectId"]: s["tests"] for s in state.slices["specs"]}
    assert all(t["passed"] == 0 for t in by_root.values()), "two apps have screens/login.test.json: neither may take it"

    _put(shelf / "android/emulator-5554/com.example.client", time.time(),
         _results("android", "7f2a1b4c-0d5e-4f60-8a71-92b3c4d5e6f7", "com.example.client", "screens/login.test.json", {"ok": "passed", "ng": "passed"}))
    world.apply_saved_results(tr.ResultShelf(shelf).scan())
    world.publish()
    passed = {world.rooms.root_of(s["projectId"]): s["tests"]["passed"] for s in state.slices["specs"]}
    assert passed == {str(client): 2, str(bar): 0}


def test_a_run_this_server_saw_start_goes_to_that_rooms_app_even_when_the_file_is_shared(tmp_path):
    bar = _project(tmp_path / "bar")
    client = _project(tmp_path / "client")
    world, state = _world(bar, client)
    # The client session starts a web test; its run_start ties RUN_A to that command (hand 1).
    world.apply_hook({"session_id": "s1", "cwd": str(client), "hook_event_name": "PreToolUse", "tool_name": "Bash",
                      "tool_use_id": "b", "tool_input": {"command": "npx playwright test"}}, 100)
    t0 = int(time.time() * 1000)
    assert world.apply_progress({"v": 1, "t": t0, "platform": "web", "run": RUN_A, "event": "run_start", "files": 1}, "web", None, t0)
    shelf = tmp_path / "shelf"
    _put(shelf / "web/x", time.time(), _results("web", RUN_A, "x", "screens/login.test.json", {"ok": "passed", "ng": "passed"}))
    world.apply_saved_results(tr.ResultShelf(shelf).scan())
    world.publish()
    passed = {world.rooms.root_of(s["projectId"]): s["tests"]["passed"] for s in state.slices["specs"]}
    assert passed == {str(client): 2, str(bar): 0}


# ---------------------------------------------------------------- the Android copy


def _fake_adb(tmp_path: Path, body: str) -> str:
    adb = tmp_path / "adb"
    adb.write_text("#!/bin/sh\n" + body)
    adb.chmod(0o755)
    return str(adb)


def test_pull_copies_the_device_folders_and_prunes_the_copy(tmp_path):
    name = _name(time.time() - 20 * 86400, RUN_A)
    # adb -s <serial> pull <remote>/. <dest>: lay out what a real pull leaves behind.
    adb = _fake_adb(tmp_path, f'mkdir -p "$5/com.example.app" && echo {{}} > "$5/com.example.app/{name}" '
                              f'&& echo {{}} > "$5/com.example.app/keep.txt" && [ "$1 $2 $3 $4" = "-s emu-1 pull {tr.DEVICE_DIR}/." ]\n')
    base = tmp_path / "base"
    assert asyncio.run(tr.pull(adb, "emu-1", base)) is True
    folder = base / "android/emu-1/com.example.app"
    assert sorted(p.name for p in folder.iterdir()) == ["keep.txt"]  # the 20-day-old file pruned, nothing else


def test_pull_gives_up_at_its_timeout_and_a_missing_adb_is_quiet(tmp_path):
    adb = _fake_adb(tmp_path, "sleep 30\n")
    started = time.monotonic()
    assert asyncio.run(tr.pull(adb, "emu-1", tmp_path / "base", timeout=0.5)) is False
    assert time.monotonic() - started < 5
    assert asyncio.run(tr.pull(str(tmp_path / "no-adb"), "emu-1", tmp_path / "base")) is False


# ---------------------------------------------------------------- a real server, restarted


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _env(home: Path) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in ("JUI_VIZ_HOME", "XDG_STATE_HOME", tr.BASE_ENV, "JSONUI_TEST_PROGRESS_DIR")}
    env.update(HOME=str(home), PYTHONUNBUFFERED="1")
    return env


def _jui(home: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(JUI), *args], env=_env(home), capture_output=True, text=True, timeout=40)


def _call(port: int, token: str, path: str, body: dict | None = None):
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data,
                                     headers={"X-Jui-Viz-Token": token, "Content-Type": "application/json"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    raw = opener.open(request, timeout=5).read()
    return json.loads(raw) if raw else None


def _until(predicate, seconds: float = 15.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            if predicate():
                return True
        except OSError:
            pass
        time.sleep(0.2)
    return predicate()


def test_a_restarted_server_still_shows_the_runs_from_before_it_started(tmp_path):
    home = tmp_path / "home"
    state_dir = home / ".local/state/jui-viz"
    state_dir.mkdir(parents=True)
    port = _free_port()
    (state_dir / "config.json").write_text(json.dumps({"port": port}))
    root = _project(tmp_path / "app")
    # A run from before any server: the driver wrote it to the default folder.
    _put(home / ".local/state/jsonui-test/results/web/app", time.time(),
         _results("web", RUN_A, "app", "screens/login.test.json", {"ok": "passed", "ng": "passed"}))
    doctor = _jui(home, "viz", "doctor")
    assert f"where test results are read: {home}/.local/state/jsonui-test/results" in doctor.stdout

    def login_passed() -> int:
        info = json.loads((state_dir / "server.json").read_text())
        _call(info["port"], info["token"], "/hook", {"session_id": "s1", "cwd": str(root), "hook_event_name": "SessionStart"})
        specs = _call(info["port"], info["token"], "/api/snapshot")["slices"].get("specs") or []
        return next((s["tests"]["passed"] for s in specs if s["name"] == "Login"), -1)

    for attempt in range(2):  # start, read; stop; start again, read the same
        started = _jui(home, "viz", "start", "--json")
        assert started.returncode == 0, started.stderr
        pid = json.loads(started.stdout)["pid"]
        try:
            assert f":{port}" in json.dumps(json.loads(started.stdout)), started.stdout  # this HOME's own port
            assert _until(lambda: login_passed() == 2), f"start {attempt + 1}: the saved run did not reach the spec"
        finally:
            _jui(home, "viz", "stop")
            if _until(lambda: not _alive(pid), 10) is False:
                os.kill(pid, signal.SIGTERM)  # the server this test started


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


# ---------------------------------------------------------------- the drivers' rule: the latest of every test file stays (2.3.1)
# tests/fixtures/viz/results-prune.json is a byte copy of jsonui-test-runner specs/vectors/results-prune.json.

VECTOR = Path(__file__).resolve().parent / "fixtures" / "viz" / "results-prune.json"


def _keyed(at: float, i: int, file: str) -> str:
    key = hashlib.sha256(file.encode("utf-8")).hexdigest()[:8]
    return _name(at, f"{i:08x}-0000-4000-8000-{i:012x}").replace(".json", f"-{key}.json")


def test_the_shared_vector_every_prune_case():
    vector = json.loads(VECTOR.read_text())
    for k in vector["fileKeys"]:
        assert hashlib.sha256(k["key"].encode("utf-8")).hexdigest()[:8] == k["fileKey8"]
    assert len(vector["prune"]) == 5
    for c in vector["prune"]:
        got = tr.to_prune(c["names"], c["now"] / 1000, c["maxFiles"], c["maxAgeDays"])
        assert (c["name"], got) == (c["name"], c["pruned"])


def test_a_rerun_file_does_not_take_the_others_latest_and_a_long_round_prunes_none_of_itself():
    now = time.time()
    names = [_keyed(now - 86400 + i / 1000, i, f"s{i}.test.json") for i in range(122)]
    names += [_keyed(now - 43200 + n, 1000 + n, "s0.test.json") for n in range(500)]
    left = set(names) - set(tr.to_prune(names, now))
    assert len(left) == tr.KEEP_FILES and len({tr.NAME.match(n).group(1) for n in left}) == 122
    one_round = [_keyed(now - 60 + i / 1000, i, f"s{i}.test.json") for i in range(600)]
    assert tr.to_prune(one_round, now) == []
    only = _keyed(now - 20 * 86400, 1, "a.test.json")
    replaced, latest = _keyed(now - 20 * 86400, 2, "b.test.json"), _keyed(now - 1, 3, "b.test.json")
    assert tr.to_prune([only, replaced, latest], now) == [replaced]


def test_the_vector_is_a_byte_copy_of_jsonui_test_runners():
    """Compared when the source is at hand: $JSONUI_TEST_RUNNER_DIR or a sibling checkout. CI checks out this repo
    alone, so there it is skipped, and says so."""
    roots = [os.environ.get("JSONUI_TEST_RUNNER_DIR"), str(Path(__file__).resolve().parents[2].parent / "jsonui-test-runner")]
    source = next((Path(r) / "specs/vectors/results-prune.json" for r in roots if r and (Path(r) / "specs/vectors/results-prune.json").is_file()), None)
    if source is None:
        pytest.skip("jsonui-test-runner specs/vectors not found: the copy is not compared here")
    assert source.read_bytes() == VECTOR.read_bytes()
