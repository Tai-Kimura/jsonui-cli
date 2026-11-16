"""A robot's test runs with the saved results (the robot card's テスト実行, 10-18; the rows are B's, test_results.py).

A saved row joins a test command's run only by its run id — a run this server saw start. Per case the newer
outcome wins, so a case seen live and then saved counts once; a saved run from before the server started is
nobody's run here (it still counts for its spec, which is B's arm).
"""
from __future__ import annotations

import uuid

from jui_cli.viz.ingest import World
from jui_cli.viz.state import VizState

SID = "11111111-2222-4333-8444-555555555555"
CWD = "/work/runs-app"
T0 = 1_792_314_000_000


def _hook(kind, **fields):
    return {"hook_event_name": kind, "session_id": SID, "cwd": CWD, **fields}


def _progress(world, run, event, t, **fields):
    rec = {"v": 1, "t": t, "platform": "web", "run": run, "event": event, **fields}
    assert world.apply_progress(rec, "web", None, t)


def _row(run, case, status, t, file="tests/a.test.json"):
    return {"platform": "web", "run": run, "app": "app", "file": file, "test": "a", "case": case, "status": status,
            "t": t, "path": f"/x/{run}.json"}


def _live_run(world):
    """Robot SID runs a test command; its progress shows c1 passed and c2 still running."""
    world.apply_hook(_hook("PreToolUse", tool_name="Bash", tool_use_id="t1", tool_input={"command": "npx playwright test"}), T0)
    run = str(uuid.uuid4())
    _progress(world, run, "run_start", T0 + 100, files=1)
    for case, status in (("c1", "passed"), ("c2", None)):
        _progress(world, run, "case_start", T0 + 200, file="tests/a.test.json", test="a", case=case, attempt=1)
        if status:
            _progress(world, run, "case_end", T0 + 300, file="tests/a.test.json", test="a", case=case, attempt=1,
                      status=status, durationMs=1)
    world.tick(T0 + 400)  # a command's cases are rebuilt at the tick, not per record (serve ticks every 0.5 s)
    return run


def test_the_saved_result_of_a_run_this_server_saw_joins_its_robots_run_case_by_case():
    world = World(VizState())
    run = _live_run(world)
    t = world.tests["t1"]
    assert [(c["name"], c["status"]) for c in t["cases"]] == [("c1", "passed"), ("c2", "running")]
    rows = [_row(run, "c1", "passed", T0 + 5_000), _row(run, "c2", "failed", T0 + 5_000), _row(run, "c3", "failed", T0 + 5_000)]
    world.apply_saved_results(rows)
    world.apply_saved_results(rows)                                  # the shelf re-reads every 5 s: still once each
    assert [(c["name"], c["status"]) for c in t["cases"]] == [("c1", "passed"), ("c2", "failed"), ("c3", "failed")]
    assert t["summary"] == "1 passed, 2 failed" and t["savedAt"] == T0 + 5_000
    assert t["agentId"] == SID                                       # still the robot that ran it


def test_an_older_saved_outcome_does_not_overwrite_a_newer_live_one():
    world = World(VizState())
    run = _live_run(world)
    world.apply_saved_results([_row(run, "c1", "failed", T0 + 50)])  # older than the live case_end at T0+300
    assert dict((c["name"], c["status"]) for c in world.tests["t1"]["cases"])["c1"] == "passed"


def test_a_saved_run_from_before_the_server_started_is_no_robots_run():
    world = World(VizState())
    run = _live_run(world)
    before = str(uuid.uuid4())                                       # a run this server never saw start
    world.apply_saved_results([_row(before, "old", "failed", T0 - 60_000), _row(run, "c2", "passed", T0 + 5_000)])
    assert [t["id"] for t in world.tests.values()] == ["t1"]          # no run made up for it
    names = [c["name"] for t in world.tests.values() for c in t.get("cases", [])]
    assert "old" not in names and names == ["c1", "c2"]
    world.publish()
    slice_tests = world.state.slices["tests"]
    assert all("progressRun" not in t and "progressRuns" not in t for t in slice_tests)


def test_a_row_without_a_run_id_joins_no_run():
    world = World(VizState())
    _live_run(world)
    world.apply_saved_results([{**_row("x", "loose", "failed", T0 + 5_000), "run": None}])
    assert "loose" not in [c["name"] for c in world.tests["t1"]["cases"]]
