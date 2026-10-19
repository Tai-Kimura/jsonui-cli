"""Merging test results into the specs at the size real rooms have (10-19 ticket
2026-10-19-jui-viz-merge-results-per-progress-record-freezes-the-server).

2.3.1 merged every room's saved rows again for each progress record and for each
5-second scan, and tied each row by matching it against every test file of every
room: a consumer's 1602 records froze the server for minutes (1216 rows, 696 test
files: 1.5 s a merge). A record now marks its room and tick merges it once; a
scan that found the same rows does nothing; where a row goes is remembered until
a room loads or a spec / test file changes, and when the runs tied to commands
change.
"""
from __future__ import annotations

import json
import statistics
import time
import uuid
from pathlib import Path

from jui_cli.viz.ingest import World
from jui_cli.viz.state import VizState

ROOMS = {"a": 330, "b": 330, "c": 36}     # test files per room: 696, as measured
ROWS_PER_FILE = 2                         # saved rows of a room's own files (a and c: 732 rows)
RUNS, CASES = 200, 8                      # live: 200 runs x 8 cases = 1600 case records (plus run_start / run_end)


def _room(root: Path, prefix: str, n: int) -> None:
    (root / "docs/screens/json").mkdir(parents=True)
    (root / "jui.config.json").write_text("{}")
    (root / "docs/screens/layouts").mkdir(parents=True)
    for i in range(n):
        name = f"{prefix}{i:03d}"
        (root / f"docs/screens/json/{name}.spec.json").write_text(json.dumps({"metadata": {"name": name, "layoutFile": name}}))
        (root / f"docs/screens/layouts/{name}.json").write_text(json.dumps({"type": "View", "id": "root"}))
        folder = root / f"tests/screens/{name}"
        folder.mkdir(parents=True)
        (folder / f"{name}.test.json").write_text(json.dumps({
            "source": {"layout": f"docs/screens/layouts/{name}.json"}, "cases": [{"name": f"c{k}"} for k in range(CASES)]}))


def _world(tmp_path: Path) -> tuple[World, VizState, dict[str, Path]]:
    roots = {}
    for prefix, n in ROOMS.items():
        roots[prefix] = tmp_path / f"room_{prefix}"
        _room(roots[prefix], prefix, n)
    state = VizState()
    world = World(state)
    for i, root in enumerate(roots.values()):
        world.apply_hook({"session_id": f"s{i}", "cwd": str(root), "hook_event_name": "SessionStart"}, 0)
        world.jsonui_project(world.rooms.project_for(str(root))["id"], 0)
    world.publish()
    return world, state, roots


def _rows(prefixes: str = "ac") -> list[dict]:
    """Saved rows of runs this server never saw: iOS spells the bare file name (hand 3 of _saved_specs)."""
    rows = []
    for prefix in prefixes:
        for i in range(ROOMS[prefix]):
            name = f"{prefix}{i:03d}"
            for k in range(ROWS_PER_FILE):
                rows.append({"platform": "ios", "app": "x.xctrunner", "run": f"{name}-saved", "file": f"{name}.test.json",
                             "test": name, "case": f"c{k}", "status": "passed" if k else "failed", "t": 1_000 + i})
    return rows


def _records(at: int):
    """A web command's runs in room b: one per test file, as playwright does."""
    for r in range(RUNS):
        run, name = str(uuid.uuid4()), f"b{r % ROOMS['b']:03d}"

        def rec(event, **kw):
            return {"v": 1, "t": at + r, "platform": "web", "run": run, "event": event, **kw}

        yield rec("run_start", files=1)
        for k in range(CASES):
            yield rec("case_end", file=f"tests/screens/{name}/{name}.test.json", test=name, case=f"c{k}", attempt=1,
                      status="passed", durationMs=1)
        yield rec("run_end", passed=CASES, failed=0, skipped=0)


def _command(world: World, root: Path, at: int) -> None:
    world.apply_hook({"session_id": "s1", "cwd": str(root), "hook_event_name": "PreToolUse", "tool_name": "Bash",
                      "tool_use_id": f"b-{at}", "tool_input": {"command": "npx playwright test"}}, at)


def _passed(state: VizState, prefix: str) -> tuple[int, int]:
    specs = [s for s in state.slices["specs"] if s["name"].startswith(prefix)]
    return sum(s["tests"]["passed"] for s in specs), sum(s["tests"]["failed"] for s in specs)


def _drive(world: World, rows: list[dict], at: int, ticks_every: int = 60) -> None:
    """What serve does: the tail's records then a tick (every 0.5 s), and the shelf's scan every 5 s."""
    world.apply_saved_results(rows)
    for n, rec in enumerate(_records(at), 1):
        world.apply_progress(rec, "web", None, at + 1)
        if n % ticks_every == 0:
            world.tick(at + n)
            if n % (ticks_every * 10) == 0:
                world.apply_saved_results([dict(r) for r in rows])   # a fresh scan that found the same files
    world.tick(at + 10_000)
    world.publish()


#: The merge's cost, in units of REFERENCE's CPU time on the same machine at the same moment. Measured 10-19 (load 90-100):
#: clean 14; 2.3.1's merge for every record 34; ties not remembered 325. Under 25 keeps the guard of the old "under a
#: second" (the clean merge took about 0.5 s of CPU) without the clock of the wall: on a busy machine the wall time grew
#: to 1.4 s (the process waiting for a core and for the disk) while the CPU time stayed 0.50 s.
UNITS_MAX = 25


def _reference_cpu() -> float:
    """CPU seconds of a fixed piece of plain Python (dict updates and str work, as the merge does), on this machine now."""
    t0 = time.process_time()
    d: dict[int, int] = {}
    n = 0
    for i in range(300_000):
        d[i % 997] = d.get(i % 997, 0) + i
        n += len(str(i))
    assert n
    return time.process_time() - t0


def test_a_large_run_against_large_rooms_merges_in_well_under_a_second(tmp_path):
    """Not quadratic, not accidentally slow (ticket 2026-10-19-jui-viz-merge-at-scale-timing-under-load): the merge's CPU
    time (time.process_time: this process only, so other processes on a loaded machine do not count) against a reference
    workload timed on either side of it (so a slower machine or a slower moment scales both)."""
    world, state, roots = _world(tmp_path)
    rows = _rows()
    at = int(time.time() * 1000)
    _command(world, roots["b"], at)
    ref = [_reference_cpu() for _ in range(3)]
    w0, c0 = time.perf_counter(), time.process_time()
    _drive(world, rows, at)
    cpu, wall = time.process_time() - c0, time.perf_counter() - w0
    ref += [_reference_cpu() for _ in range(3)]
    units = cpu / statistics.median(ref)
    assert units < UNITS_MAX, (f"{units:.1f} units (CPU {cpu:.2f} s, reference {statistics.median(ref):.3f} s, wall {wall:.2f} s) "
                               f"for {len(rows)} rows and {RUNS * (CASES + 2)} records")
    # What the merge says is what it said before (counted from the specimen, not from the code):
    assert _passed(state, "a") == (ROOMS["a"] * (ROWS_PER_FILE - 1), ROOMS["a"])
    assert _passed(state, "c") == (ROOMS["c"] * (ROWS_PER_FILE - 1), ROOMS["c"])
    assert _passed(state, "b") == (min(RUNS, ROOMS["b"]) * CASES, 0)


def test_records_merge_and_rebuild_the_commands_cases_at_the_tick_and_a_same_scan_does_nothing(tmp_path, monkeypatch):
    world, state, roots = _world(tmp_path)
    rows = _rows()
    at = int(time.time() * 1000)
    _command(world, roots["b"], at)
    world.apply_saved_results(rows)
    world.tick(at)
    merges, rebuilds = [], []
    original, rebuild = World._merge_results, World._run_cases
    monkeypatch.setattr(World, "_merge_results", lambda self, project: (merges.append(project.project_id), original(self, project)))
    monkeypatch.setattr(World, "_run_cases", lambda self, target: (rebuilds.append(target["id"]), rebuild(self, target)))
    records = list(_records(at))
    for rec in records:
        world.apply_progress(rec, "web", None, at + 1)
    assert merges == [] and rebuilds == []                        # not one per record
    world.tick(at + 1)
    assert 1 <= len(merges) <= len(ROOMS)                         # once per room at most, at the tick
    assert len(rebuilds) == 1                                     # the one command's cases, once
    assert world.tests[f"b-{at}"]["summary"] == f"{RUNS * CASES} passed, 0 failed"
    merges.clear(); rebuilds.clear()
    world.apply_saved_results([dict(r) for r in rows])
    world.tick(at + 2)
    assert merges == [] and rebuilds == []                        # the same scan: nothing


def test_a_room_that_gains_the_same_test_file_unties_the_row_and_a_new_spec_is_reached_too(tmp_path):
    world, state, roots = _world(tmp_path)
    world.apply_saved_results(_rows("c"))
    world.publish()
    assert _passed(state, "c000") == (1, 1)
    # Room a now has c000.test.json too: the bare name is in two rooms, so the row reaches nobody (hand 3).
    twin = roots["a"] / "tests/screens/c000/c000.test.json"
    twin.parent.mkdir(parents=True)
    twin.write_text((roots["c"] / "tests/screens/c000/c000.test.json").read_text())
    world.file_changed(world.rooms.project_for(str(roots["a"]))["id"], str(twin), 1)
    world.tick(1)
    world.publish()
    assert _passed(state, "c000") == (0, 0)
    twin.unlink()
    world.file_changed(world.rooms.project_for(str(roots["a"]))["id"], str(twin), 2)
    world.tick(2)
    world.publish()
    assert _passed(state, "c000") == (1, 1)
    # A new spec names c000's layout: the test file reaches it too (where a row goes is worked out again).
    spec = roots["c"] / "docs/screens/json/z000.spec.json"
    spec.write_text(json.dumps({"metadata": {"name": "z000", "layoutFile": "c000"}}))
    world.file_changed(world.rooms.project_for(str(roots["c"]))["id"], str(spec), 3)
    world.tick(3)
    world.publish()
    assert _passed(state, "z000") == (1, 1)


def test_a_saved_run_that_a_command_turns_out_to_own_moves_to_that_commands_room(tmp_path):
    """Hand 1 of _saved_specs: a row whose run a command in room b started goes to room b, even when its
    bare file name is room a's only (hand 3 would send it there)."""
    world, state, roots = _world(tmp_path)
    run = str(uuid.uuid4())
    row = {"platform": "web", "app": "x", "run": run, "file": "a000.test.json", "test": "a000", "case": "c0",
           "status": "passed", "t": 5}
    world.apply_saved_results([row])
    world.tick(1)
    world.publish()
    assert _passed(state, "a000") == (1, 0)
    at = int(time.time() * 1000)
    _command(world, roots["b"], at)
    world.apply_progress({"v": 1, "t": at, "platform": "web", "run": run, "event": "run_start", "files": 1}, "web", None, at)
    world.tick(at + 1)
    world.publish()
    assert _passed(state, "a000") == (0, 0)                       # room b has no a000 spec: the row left room a


def test_a_row_is_matched_against_the_test_files_of_its_name_only(tmp_path, monkeypatch):
    """The match rule needs the file name to agree, so a row is compared with the files of that name, not with
    every room's 696 files (2.3.1: 1.5 s for the first merge of the real shelf; with the names, 0.006 s)."""
    from jui_cli.viz.sources.jsonui_project import test_dirs
    rules = test_dirs()
    world, state, roots = _world(tmp_path)
    sizes = []
    original = rules.match_test_file
    monkeypatch.setattr(rules, "match_test_file", lambda name, keys: (sizes.append(len(list(keys))), original(name, list(keys)))[1])
    world.apply_saved_results(_rows())
    world.publish()
    assert sizes and max(sizes) <= 1, max(sizes)
    assert _passed(state, "a") == (ROOMS["a"] * (ROWS_PER_FILE - 1), ROOMS["a"])
