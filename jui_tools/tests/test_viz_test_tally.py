"""Test results by the checkout they ran in, and done counting every branch (ticket 2026-10-23-viz-test-tally-and-worktrees).

The requester: 「テストの集計もおかしい気がする / 多分ワークツリーで流してて反映されてないとかかな？」. Measured on the
real results (3919 rows): a session in a worktree of bar made that worktree a room of its own holding the same test
file, so a saved result (a run this server did not see) found two owners and was tied to neither: the room's bar
specs with results went from 15 to 11 and instagram_import_settings from 2/2 passed to 0.

- A saved result this server did not see run is the main checkout's: tied to the room's own app, never to a linked
  worktree (a room that is a worktree, or the room's app@branch). A run it saw is tied by the checkout its command
  ran in: the room's own app, or the worktree's app@branch the room shows.
- Done is every test case and as many as the spec's branches passed (requester 10-23: 「分岐も全部で完了」): a spec
  with 2 of 2 cases passed and 3 branches is not done; tests.needed is the count the board says.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from jui_cli.viz.ingest import World
from jui_cli.viz.sources import test_results as tr
from jui_cli.viz.state import VizState

RUN_UNSEEN = "3f2a1b4c-0d5e-4f60-8a71-92b3c4d5e6f7"
RUN_SEEN = "5f2a1b4c-0d5e-4f60-8a71-92b3c4d5e6f7"
CMD = "xcodebuild test -scheme App -destination 'platform=iOS Simulator,name=iPhone 16'"


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                   env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
                        "GIT_COMMITTER_EMAIL": "t@t", "HOME": str(cwd), "PATH": "/usr/bin:/bin:/opt/homebrew/bin"})


def _room(tmp_path: Path, branches: int = 0, config: dict | None = None) -> tuple[Path, Path]:
    """A repository: a JsonUI app at its root with Login (``branches`` branches) and a test file of two cases, committed;
    a worktree of it outside the room (feat/x). The room's root and the worktree's."""
    root = tmp_path / "room"
    for d in ("docs/screens/json", "docs/screens/layouts", "tests/screens"):
        (root / d).mkdir(parents=True)
    (root / "jui.config.json").write_text(json.dumps(config or {}))
    spec = {"metadata": {"name": "Login", "layoutFile": "login"}}
    if branches:
        spec["branchContracts"] = {"methods": {"onAppear": {"branches": [{"when": {"k": i}, "then": {"v": i}} for i in range(branches)]}}}
    (root / "docs/screens/json/login.spec.json").write_text(json.dumps(spec))
    (root / "docs/screens/layouts/login.json").write_text(json.dumps({"type": "View", "id": "root"}))
    (root / "tests/screens/login.test.json").write_text(json.dumps({"source": {"layout": "docs/screens/layouts/login.json"},
                                                                      "cases": [{"name": "ok"}, {"name": "ng"}]}))
    _git(root, "init", "-q", "-b", "main")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "init")
    wt = tmp_path / "scratch" / "wt"
    _git(root, "worktree", "add", "-q", "-b", "feat/x", str(wt))
    return root, wt


def _rows(run: str, cases: dict) -> list[dict]:
    data = {"format": "jsonui-test-results", "version": 1, "platform": "ios", "generatedAt": "2026-10-23T01:00:00Z",
            "run": run, "app": "com.example.AppUITests.xctrunner",
            "suites": [{"suiteName": "login", "file": "screens/login.test.json", "results": [
                {"testName": "login", "caseName": c, "status": s, "durationMs": 1} for c, s in cases.items()]}]}
    stamp = datetime.fromtimestamp(time.time(), timezone.utc).strftime("%Y%m%dT%H%M%S.%f")[:-3]
    return tr.rows(data, Path(f"/results/ios/app/{stamp}Z-{run}.json"))


def _tests(state: VizState) -> dict[str, dict]:
    """Each Login row's tests, by "<room name>:<app>"."""
    rooms = {p["id"]: p["name"] for p in state.slices["projects"]}
    return {f"{rooms[s['projectId']]}:{s['app']}": s["tests"] for s in state.slices["specs"] if s["name"] == "Login"}


def _world(root: Path, wt: Path) -> tuple[World, VizState]:
    state = VizState()
    world = World(state)
    world.apply_hook({"session_id": "main", "cwd": str(root), "hook_event_name": "SessionStart"}, 0)
    world.apply_hook({"session_id": "wt", "cwd": str(wt), "hook_event_name": "SessionStart"}, 0)
    world.tick(10)
    return world, state


def test_a_result_no_command_here_ran_is_the_main_checkouts(tmp_path):
    """The worktree's room and the room's app@branch hold the same test file: the room's own row still gets it."""
    root, wt = _room(tmp_path)
    world, state = _world(root, wt)
    world.apply_saved_results(_rows(RUN_UNSEEN, {"ok": "passed", "ng": "passed"}))
    world.tick(20)
    world.publish()
    got = {k: v["passed"] for k, v in _tests(state).items()}
    assert got == {"room/:": 2, "room/:@feat/x": 0, "wt/:": 0}, got


def test_a_run_seen_in_the_worktree_goes_to_its_app_at_branch_only(tmp_path):
    """The command's cwd a folder below the worktree's root (a robot runs tests in its app's folder): still the worktree's."""
    root, wt = _room(tmp_path)
    world, state = _world(root, wt)
    below = wt / "docs" / "screens"   # a session started there (claude started in the app's folder): its cwd is below
    world.apply_hook({"session_id": "below", "cwd": str(below), "hook_event_name": "SessionStart"}, 25)
    assert world.sessions["below"]["cwd"].endswith("scratch/wt/docs/screens")
    world.apply_hook({"session_id": "below", "cwd": str(below), "hook_event_name": "PreToolUse", "tool_name": "Bash",
                      "tool_use_id": "b", "tool_input": {"command": CMD}}, 30)
    world.tests["b"]["progressRun"] = RUN_SEEN   # its progress record named the run (test_viz_test_progress)
    world.apply_saved_results(_rows(RUN_SEEN, {"ok": "passed", "ng": "failed"}))
    world.tick(40)
    world.publish()
    got = {k: (v["passed"], v["failed"]) for k, v in _tests(state).items()}
    assert got == {"room/:": (0, 0), "room/:@feat/x": (1, 1), "wt/:": (1, 1)}, got


def test_a_run_seen_in_the_room_goes_to_the_rooms_own_row_only(tmp_path):
    root, wt = _room(tmp_path)
    world, state = _world(root, wt)
    world.apply_hook({"session_id": "main", "cwd": str(root), "hook_event_name": "PreToolUse", "tool_name": "Bash",
                      "tool_use_id": "b", "tool_input": {"command": CMD}}, 30)
    world.tests["b"]["progressRun"] = RUN_SEEN
    world.apply_saved_results(_rows(RUN_SEEN, {"ok": "passed", "ng": "passed"}))
    world.tick(40)
    world.publish()
    got = {k: v["passed"] for k, v in _tests(state).items()}
    assert got == {"room/:": 2, "room/:@feat/x": 0, "wt/:": 0}, got


def test_done_counts_every_branch_and_the_board_says_the_same_count(tmp_path):
    root, _wt = _room(tmp_path, branches=3)
    state = VizState()
    world = World(state)
    world.apply_hook({"session_id": "main", "cwd": str(root), "hook_event_name": "SessionStart"}, 0)
    world.apply_saved_results(_rows(RUN_UNSEEN, {"ok": "passed", "ng": "passed"}))
    world.tick(10)
    world.publish()
    login = next(s for s in state.slices["specs"] if s["name"] == "Login")
    assert (login["tests"]["total"], login["tests"]["needed"], login["tests"]["passed"]) == (2, 3, 2)
    assert login["bucket"] != "done"   # 2 of 2 cases, but 3 branches: not done (was done)
    os.utime(root / "tests/screens/login.test.json")
    (root / "tests/screens/login.test.json").write_text(json.dumps({"source": {"layout": "docs/screens/layouts/login.json"},
                                                                      "cases": [{"name": "ok"}, {"name": "ng"}, {"name": "more"}]}))
    world.file_changed(world.state.slices["projects"][0]["id"], str(root / "tests/screens/login.test.json"), 20)
    world.apply_saved_results(_rows(RUN_UNSEEN, {"ok": "passed", "ng": "passed", "more": "passed"}))
    world.tick(30)
    world.publish()
    login = next(s for s in state.slices["specs"] if s["name"] == "Login")
    assert (login["tests"]["needed"], login["tests"]["passed"], login["bucket"]) == (3, 3, "done")


def test_one_case_in_two_spellings_is_counted_once_beside_a_worktree(tmp_path):
    """iOS names the file screens/login.test.json, Android login.test.json: one case each. With the room's app@branch
    holding the same file, the key is still the room's own file (it was the spelling: each case counted twice)."""
    root, wt = _room(tmp_path)
    world, state = _world(root, wt)
    android = [dict(r, platform="android", file="login.test.json", path=r["path"].replace("/ios/", "/android/"))
               for r in _rows(RUN_UNSEEN, {"ok": "passed", "ng": "passed"})]
    world.apply_saved_results(_rows(RUN_UNSEEN, {"ok": "passed", "ng": "passed"}) + android)
    world.tick(20)
    world.publish()
    assert _tests(state)["room/:"]["passed"] == 2, _tests(state)


def test_a_spec_with_no_test_file_of_its_own_is_not_done(tmp_path):
    """Cases counted 0 (no test file of its own) and as many results as its branches: not done, as before."""
    root, _wt = _room(tmp_path, branches=1)
    (root / "tests/screens/login.test.json").unlink()
    state = VizState()
    world = World(state)
    world.apply_hook({"session_id": "main", "cwd": str(root), "hook_event_name": "SessionStart"}, 0)
    world.apply_hook({"session_id": "main", "cwd": str(root), "hook_event_name": "PreToolUse", "tool_name": "Bash",
                      "tool_use_id": "b", "tool_input": {"command": CMD}}, 10)
    world.tests["b"]["progressRun"] = RUN_SEEN   # a run seen here: tied by the file's name (no app has the file)
    world.apply_saved_results(_rows(RUN_SEEN, {"ok": "passed"}))
    world.tick(20)
    world.publish()
    login = next(s for s in state.slices["specs"] if s["name"] == "Login")
    assert (login["tests"]["total"], login["tests"]["needed"], login["tests"]["passed"]) == (0, 1, 1), login["tests"]
    assert login["bucket"] != "done"


def test_an_android_result_by_its_package_is_the_main_checkouts(tmp_path):
    """Hand 2: the package names the app (test.artifacts.android.appId), the same in every checkout of it: a result no
    command here ran goes to the room's own app, not the worktree's room nor its app@branch."""
    root, wt = _room(tmp_path, config={"test": {"artifacts": {"android": {"appId": "com.example.app.dev"}}}})
    world, state = _world(root, wt)
    rows = [dict(r, platform="android", app="com.example.app.dev", file="login.test.json")
            for r in _rows(RUN_UNSEEN, {"ok": "passed", "ng": "passed"})]
    world.apply_saved_results(rows)
    world.tick(20)
    world.publish()
    got = {k: v["passed"] for k, v in _tests(state).items()}
    assert got == {"room/:": 2, "room/:@feat/x": 0, "wt/:": 0}, got


def test_a_failed_case_keeps_a_spec_from_done(tmp_path):
    """Every case and every branch passed, and one failed too (two runs): not done."""
    root, _wt = _room(tmp_path, branches=2)
    state = VizState()
    world = World(state)
    world.apply_hook({"session_id": "main", "cwd": str(root), "hook_event_name": "SessionStart"}, 0)
    rows = _rows(RUN_UNSEEN, {"ok": "passed", "ng": "passed"})
    failed = [dict(r, case="extra", status="failed", path=r["path"].replace(RUN_UNSEEN, RUN_SEEN)) for r in rows[:1]]
    world.apply_saved_results(rows + failed)
    world.tick(10)
    world.publish()
    login = next(s for s in state.slices["specs"] if s["name"] == "Login")
    assert (login["tests"]["needed"], login["tests"]["passed"], login["tests"]["failed"]) == (2, 2, 1), login["tests"]
    assert login["bucket"] != "done"
