"""A test run reaches its spec on the layouts real projects have (10-18 ticket
2026-10-18-jui-viz-tests-never-reach-a-spec-on-real-layouts).

Until 2.3.0 every arm used one shape — tests/screens/login.test.json, the driver
naming it `screens/login.test.json`, one run per command — and on the three
measured consumers nothing reached a spec: test files in a folder per screen
were not read, a test folder outside the app was not found, each driver spells
`file` its own way, and only a command's first run was tied to it. Each of those
shapes is a specimen here.
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

from jui_cli.viz.ingest import World
from jui_cli.viz.sources import test_results as tr
from jui_cli.viz.sources.jsonui_project import test_dirs as jsonui_test_rules
from jui_cli.viz.state import VizState


def _spec(root: Path, name: str) -> None:
    (root / "docs/screens/json").mkdir(parents=True, exist_ok=True)
    (root / "docs/screens/layouts").mkdir(parents=True, exist_ok=True)
    (root / f"docs/screens/json/{name}.spec.json").write_text(json.dumps({"metadata": {"name": name, "layoutFile": name}}))
    (root / f"docs/screens/layouts/{name}.json").write_text(json.dumps({"type": "View", "id": "root"}))


def _test(path: Path, layout: str, cases: list[str], test: str | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"source": {"layout": f"docs/screens/layouts/{layout}.json"}, "cases": [{"name": c} for c in cases]}
    if test:
        data["metadata"] = {"name": test}
    path.write_text(json.dumps(data))


def _world(*roots: Path) -> tuple[World, VizState]:
    state = VizState()
    world = World(state)
    for i, root in enumerate(roots):
        world.apply_hook({"session_id": f"s{i}", "cwd": str(root), "hook_event_name": "SessionStart"}, 0)
    world.publish()
    return world, state


def _tests(state: VizState, name: str) -> dict:
    return next(s["tests"] for s in state.slices["specs"] if s["name"] == name)


def _command(world: World, root: Path, platform: str, at: int) -> None:
    command = {"ios": "xcodebuild test", "android": "./gradlew connectedAndroidTest", "web": "npx playwright test"}[platform]
    world.apply_hook({"session_id": "s0", "cwd": str(root), "hook_event_name": "PreToolUse", "tool_name": "Bash",
                      "tool_use_id": f"b-{at}", "tool_input": {"command": command}}, at)


def _run(world: World, platform: str, file: str, test: str, cases: dict, at: int) -> str:
    """One driver run (one test file): run_start, a case_end per case, run_end."""
    run = str(uuid.uuid4())

    def rec(event, **kw):
        return {"v": 1, "t": at, "platform": platform, "run": run, "event": event, **kw}

    world.apply_progress(rec("run_start", files=1), platform, None, at)
    for case, status in cases.items():
        world.apply_progress(rec("case_end", file=file, test=test, case=case, attempt=1, status=status, durationMs=1), platform, None, at)
    world.apply_progress(rec("run_end", passed=sum(s == "passed" for s in cases.values()),
                             failed=sum(s == "failed" for s in cases.values()), skipped=0), platform, None, at)
    return run


# ---------------------------------------------------------------- the rule itself (jsonui-test's own module)


def test_the_tail_match_takes_any_drivers_spelling_and_refuses_a_tie():
    rules = jsonui_test_rules()
    keys = ["screens/forgot_password/forgot_submit_success.test.json", "screens/login/login_smoke.test.json",
            "flows/settings/app_info.test.json", "screens/app_info/app_info.test.json"]
    assert rules.match_test_file("forgot_submit_success.test.json", keys) == keys[0]                       # iOS
    assert rules.match_test_file("tests/forgot_submit_success.test.json", keys) == keys[0]                 # Android
    assert rules.match_test_file("../tests/web-app/screens/login/login_smoke.test.json", keys) == keys[1]     # Web
    assert rules.match_test_file("app_info.test.json", keys) is None                                       # two files: no guess
    assert rules.match_test_file("flows/settings/app_info.test.json", keys) == keys[2]                     # longer tail decides
    assert rules.match_test_file("inline", keys) is None and rules.match_test_file("", keys) is None


# ---------------------------------------------------------------- the consumer shapes


def test_a_folder_per_screen_is_read_and_each_platforms_spelling_reaches_the_spec(tmp_path):
    root = tmp_path / "app_a"
    root.mkdir()
    (root / "jui.config.json").write_text("{}")
    _spec(root, "forgot_password")
    _test(root / "tests/screens/forgot_password/forgot_submit_success.test.json", "forgot_password", ["ok", "ng"])
    _test(root / "tests/screens/forgot_password/forgot_phase2_toggles.test.json", "forgot_password", ["toggle"])
    world, state = _world(root)
    assert _tests(state, "forgot_password")["total"] == 3

    at = int(time.time() * 1000)
    for i, (platform, file) in enumerate([("ios", "forgot_submit_success.test.json"),
                                          ("android", "tests/forgot_submit_success.test.json")]):
        _command(world, root, platform, at + i * 10_000)
        _run(world, platform, file, "forgot_submit_success", {"ok": "passed", "ng": "failed"}, at + i * 10_000 + 1)
        world.publish()
        assert (_tests(state, "forgot_password")["passed"], _tests(state, "forgot_password")["failed"]) == (1, 1), platform


def test_a_test_folder_outside_the_app_declared_by_testDir_is_read(tmp_path):
    repo = tmp_path / "repo"
    app = repo / "web-app"
    app.mkdir(parents=True)
    (app / "jui.config.json").write_text(json.dumps({"test": {"testDir": "../tests/web-app"}}))
    _spec(app, "item_detail")
    _test(repo / "tests/web-app/screens/item_detail.test.json", "item_detail", ["shows", "books"])
    world, state = _world(app)
    assert _tests(state, "item_detail")["total"] == 2
    at = int(time.time() * 1000)
    _command(world, app, "web", at)
    _run(world, "web", "../tests/web-app/screens/item_detail.test.json", "item_detail", {"shows": "passed", "books": "passed"}, at + 1)
    world.publish()
    assert _tests(state, "item_detail")["passed"] == 2


def test_every_run_of_one_command_reaches_its_spec(tmp_path):
    root = tmp_path / "web"
    root.mkdir()
    (root / "jui.config.json").write_text("{}")
    for name in ("a", "b", "c"):
        _spec(root, name)
        _test(root / f"tests/screens/{name}/{name}_basic.test.json", name, ["ok"])
    world, state = _world(root)
    at = int(time.time() * 1000)
    _command(world, root, "web", at)
    runs = [_run(world, "web", f"tests/screens/{n}/{n}_basic.test.json", f"{n}_basic", {"ok": "passed"}, at + 1 + i) for i, n in enumerate("abc")]
    world.publish()
    assert [_tests(state, n)["passed"] for n in "abc"] == [1, 1, 1]
    command = next(iter(world.tests.values()))
    assert command["progressRuns"] == runs and command["progressRun"] == runs[0]
    assert len(command["cases"]) == 3 and command["summary"] == "3 passed, 0 failed"
    assert "progressRuns" not in json.dumps(state.slices["tests"])


def test_the_same_test_and_case_names_in_two_files_are_two_cases(tmp_path):
    root = tmp_path / "dup"
    root.mkdir()
    (root / "jui.config.json").write_text("{}")
    _spec(root, "login")
    _test(root / "tests/screens/login/login_a.test.json", "login", ["renders"], test="login")
    _test(root / "tests/screens/login/login_b.test.json", "login", ["renders"], test="login")
    world, state = _world(root)
    at = int(time.time() * 1000)
    _command(world, root, "ios", at)
    _run(world, "ios", "login_a.test.json", "login", {"renders": "passed"}, at + 1)
    _run(world, "ios", "login_b.test.json", "login", {"renders": "failed"}, at + 2)
    world.publish()
    tests = _tests(state, "login")
    assert (tests["total"], tests["passed"], tests["failed"]) == (2, 1, 1)


def test_a_saved_result_with_a_bare_file_name_reaches_the_one_room_that_has_it_and_never_two(tmp_path):
    room_b = tmp_path / "room_b"
    room_a = tmp_path / "room_a"
    for root, test in ((room_b, "b_only"), (room_a, "shared")):
        root.mkdir()
        (root / "jui.config.json").write_text("{}")
        _spec(root, "login")
        _test(root / f"tests/screens/login/{test}.test.json", "login", ["ok"])
    _test(room_a / "tests/screens/login/a_only.test.json", "login", ["ok"])
    _test(room_b / "tests/screens/login/shared.test.json", "login", ["ok"])
    world, state = _world(room_b, room_a)
    shelf = tmp_path / "shelf"
    now = time.time()
    for i, file in enumerate(("a_only.test.json", "shared.test.json")):   # iOS spells the bare name
        run = str(uuid.uuid4())
        folder = shelf / "ios/x.xctrunner"
        folder.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%dT%H%M%S", time.gmtime(now + i)) + ".000Z"
        (folder / f"{stamp}-{run}.json").write_text(json.dumps({
            "format": "jsonui-test-results", "version": 1, "platform": "ios", "run": run, "app": "x.xctrunner",
            "suites": [{"suiteName": "t", "file": file, "results": [{"testName": "t", "caseName": "ok", "status": "passed", "durationMs": 1}]}]}))
    world.apply_saved_results(tr.ResultShelf(shelf).scan())
    world.publish()
    passed = {world.rooms.root_of(s["projectId"]): s["tests"]["passed"] for s in state.slices["specs"]}
    assert passed == {str(room_a): 1, str(room_b): 0}  # a_only reaches room_a; shared is in both rooms: nobody
