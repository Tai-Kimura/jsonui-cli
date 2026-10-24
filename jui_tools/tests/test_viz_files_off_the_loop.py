"""The live server reads the JsonUI rooms' files off the loop (ticket 2026-10-24-viz-serve-loop-stalls-in-spec-summaries-stat):
the loop stood still 10–40 s nine times on 10-24 while publish built the specs slice, every spec's Layout and folders
asked of the file system on the loop (31,798 stats for 434 specs; one stat 0.3–1 ms slower made one build 15–47 s).

With ``World.off_loop`` (serve, not a replay) one worker reads — the specs' facts, a changed spec or texts file, the
tests, a room loaded, the worktrees shown — and the loop applies what it read, in the order asked. Measured here:
nothing of it touches the file system on the loop, a slow file system leaves the loop beating, the slice settles to
the one the old way built, one build's walk is shared (B), and a file made where the last build found none belongs to
its spec from the next build on (C: one beat late, nothing else).
"""
from __future__ import annotations

import asyncio
import io
import json
import os
import subprocess
import threading
import time
from pathlib import Path

import pytest

from jui_cli.viz.ingest import World
from jui_cli.viz.sources import jsonui_project
from jui_cli.viz.sources.jsonui_project import JsonUIProject
from jui_cli.viz.state import VizState

ROBOT = "agent-1"


def _spec(name: str, layout: str | None = None, related: list[str] = ()) -> dict:
    meta = {"name": name, "displayName": name, "description": "d", "platforms": ["ios"]}
    if layout:
        meta["layoutFile"] = layout
    return {"type": "screen_spec", "metadata": meta, "relatedFiles": [{"path": p} for p in related]}


def _room(tmp_path: Path, n: int = 3, related: int = 1) -> Path:
    root = tmp_path / "room"
    specs = root / "docs" / "screens" / "json"
    layouts = root / "docs" / "screens" / "layouts"
    specs.mkdir(parents=True)
    layouts.mkdir(parents=True)
    (root / "jui.config.json").write_text("{}", encoding="utf-8")
    for i in range(n):
        name = f"s{i}"
        (specs / f"{name}.spec.json").write_text(json.dumps(_spec(name, name, [f"src/{name}_{k}.swift" for k in range(related)])), encoding="utf-8")
        if i % 2 == 0:
            (layouts / f"{name}.json").write_text(json.dumps({"type": "View", "id": "root", "child": [{"type": "Label", "id": "t"}]}), encoding="utf-8")
    tests = root / "tests" / "screens"
    tests.mkdir(parents=True)
    (tests / "s0.test.json").write_text(json.dumps({"source": {"layout": "s0"}, "cases": [{"name": "a"}]}), encoding="utf-8")
    return root


def _world(root: Path, off_loop: bool) -> tuple[World, VizState, str]:
    state = VizState()
    world = World(state)
    world.off_loop = off_loop
    world.apply_hook({"session_id": "main", "cwd": str(root), "hook_event_name": "SessionStart"}, 0)
    pid = next(p["id"] for p in world.rooms.projects.values() if p["jsonui"])
    _settle(world)
    return world, state, pid


def _settle(world: World, at: int = 100) -> None:
    """What the server's ticks do until the worker has nothing left: wait for its readings, apply them, publish."""
    for _ in range(50):
        for job, _apply in list(world._files_jobs):
            job.result(timeout=60)
        world.tick(at)
        world.publish()
        if not world._files_jobs:
            return
    raise AssertionError("the worker never settled")


def _specs(state: VizState, pid: str) -> list[dict]:
    return [{k: v for k, v in s.items() if k != "updatedAt"} for s in state.slices.get("specs", []) if s["projectId"] == pid]


class _LoopFs:
    """Counts the file system calls made on the main thread (the loop's), by name."""

    NAMES = ("stat", "lstat", "scandir", "listdir")

    def __init__(self, monkeypatch, sleep: float = 0.0):
        self.calls: dict[str, int] = {}
        main = threading.main_thread()
        for name in self.NAMES:
            real = getattr(os, name)

            def wrap(*a, _real=real, _name=name, **k):
                if threading.current_thread() is main:
                    self.calls[_name] = self.calls.get(_name, 0) + 1
                if sleep:
                    time.sleep(sleep)
                return _real(*a, **k)
            monkeypatch.setattr(os, name, wrap)
        real_open = io.open

        def opener(*a, **k):
            if threading.current_thread() is main:
                self.calls["open"] = self.calls.get("open", 0) + 1
            return real_open(*a, **k)
        monkeypatch.setattr(io, "open", opener)
        monkeypatch.setattr("builtins.open", opener)

    def total(self) -> int:
        return sum(self.calls.values())


def test_off_the_loop_the_slice_settles_to_the_one_built_on_the_spot(tmp_path):
    root = _room(tmp_path, n=6, related=2)
    (root / "src").mkdir()
    (root / "src" / "s0_0.swift").write_text("x", encoding="utf-8")
    _w1, inline, pid1 = _world(root, off_loop=False)
    _w2, off, pid2 = _world(root, off_loop=True)
    assert pid1 == pid2 and len(_specs(off, pid2)) == 6
    assert _specs(off, pid2) == _specs(inline, pid1)
    s0 = next(s for s in _specs(off, pid2) if s["name"] == "s0")
    assert s0["impl"]["related"] == {"total": 2, "done": 1} and s0["impl"]["layout"] is True and s0["tests"]["total"] == 1


def test_a_room_is_loaded_in_the_worker_and_shown_from_the_apply_on(tmp_path, monkeypatch):
    root = _room(tmp_path)
    world = World(VizState())
    world.off_loop = True
    fs = _LoopFs(monkeypatch)
    world.apply_hook({"session_id": "main", "cwd": str(root), "hook_event_name": "SessionStart"}, 0)
    pid = next(p["id"] for p in world.rooms.projects.values() if p["jsonui"])
    # the room's own walk (rooms.py, which room a cwd is in) is the hook's; the JsonUI room's files are not read
    assert not any(c in ("scandir", "listdir") for c in fs.calls), fs.calls
    assert pid not in world.jsonui and world.jsonui_project(pid, 0) is None   # being read: none yet, asked once
    assert len(world._files_jobs) == 1
    fs.calls.clear()
    _settle(world)
    assert pid in world.jsonui and world.jsonui[pid].off_loop and len(world.jsonui[pid].specs) == 3
    assert fs.calls == {}, fs.calls


def test_publish_and_a_changed_file_ask_the_loop_nothing(tmp_path, monkeypatch):
    root = _room(tmp_path, n=5, related=3)
    world, state, pid = _world(root, off_loop=True)
    fs = _LoopFs(monkeypatch)
    spec = root / "docs" / "screens" / "json" / "s1.spec.json"
    for path in (spec, root / "docs" / "screens" / "layouts" / "s0.json", root / "tests" / "screens" / "s0.test.json",
                 root / "docs" / "screens" / "json" / "s1.texts.yaml"):
        world.file_changed(pid, str(path), 50, by=ROBOT)
    world._dirty.add("specs")
    world.publish()
    world.tick(60)
    assert fs.calls == {}, fs.calls
    spec.write_text(json.dumps(_spec("s1", "s1", ["src/new.swift"])), encoding="utf-8")
    fs.calls.clear()   # the test's own write
    world.file_changed(pid, str(spec), 70, by=ROBOT)
    assert fs.calls == {}, fs.calls
    for job, _apply in list(world._files_jobs):
        job.result(timeout=60)
    world.publish()   # applies the reading; the facts asked for are read in the worker
    assert fs.calls == {}, fs.calls
    _settle(world)
    s1 = next(s for s in _specs(state, pid) if s["name"] == "s1")
    assert s1["impl"]["related"] == {"total": 1, "done": 0} and s1.get("by") == ROBOT


def test_the_loop_keeps_beating_while_a_slow_file_system_is_read(tmp_path, monkeypatch):
    """The ticket's arm: a file system where each stat takes 1 ms longer; while the worker reads every spec's facts the
    loop answers (here: a 50 ms beat that may never wait 1 s). The old way (on the loop) waits the whole reading."""
    root = _room(tmp_path, n=60, related=6)
    world, _state, pid = _world(root, off_loop=True)
    _LoopFs(monkeypatch, sleep=0.001)
    gaps: list[float] = []

    async def main() -> float:
        loop = asyncio.get_running_loop()
        stop = asyncio.Event()

        async def beat():
            last = time.monotonic()
            while not stop.is_set():
                await asyncio.sleep(0.05)
                now = time.monotonic()
                gaps.append(now - last)
                last = now

        task = asyncio.create_task(beat())
        t0 = time.monotonic()
        spec = root / "docs" / "screens" / "json" / "s3.spec.json"
        loop.call_soon(lambda: (world.file_changed(pid, str(spec), 50, by=ROBOT), world.publish()))
        while True:
            await asyncio.sleep(0.05)
            world.tick(60)
            world.publish()
            if not world._files_jobs and not world._facts_due and not world._facts_running:
                break
        took = time.monotonic() - t0
        stop.set()
        await task
        return took

    took = asyncio.run(main())
    assert took > 1.0, f"the slow reading must be long enough to show a stall ({took:.2f} s)"
    assert max(gaps) < 1.0, f"the loop stood still {max(gaps):.2f} s while the worker read for {took:.2f} s"


def test_one_build_walks_a_folder_once(tmp_path, monkeypatch):
    """B: the folders a spec's paths may be written from depend on its folder only; one build asks each path once."""
    root = _room(tmp_path, n=20, related=2)
    project = JsonUIProject(root, "p")
    project.load_all(0)
    asked: dict[str, int] = {}
    real = os.stat

    def stat(path, *a, **k):
        asked[os.fspath(path)] = asked.get(os.fspath(path), 0) + 1
        return real(path, *a, **k)
    monkeypatch.setattr(os, "stat", stat)
    project.spec_facts(project.fact_rows())
    config = str(root / "docs" / "screens" / "json" / "jui.config.json")
    assert asked.get(config) == 1, asked.get(config)
    assert max(n for p, n in asked.items() if not p.endswith((".spec.json", ".json"))) == 1


def test_a_file_made_where_the_last_build_found_none_belongs_to_its_spec_from_the_next_build(tmp_path):
    """C: off the loop, specs_touching reads the last build's facts. A Layout made under the room's root (the last
    build found it nowhere and looked for it in the layouts folder first) is not its spec's on the first edit; that
    edit marks the facts to be read again, and the next edit is the spec's (the 書いている tag one beat late)."""
    root = _room(tmp_path, n=1)
    spec = root / "docs" / "screens" / "json" / "s0.spec.json"
    spec.write_text(json.dumps(_spec("s0", "elsewhere")), encoding="utf-8")
    world, state, pid = _world(root, off_loop=True)
    project = world.jsonui[pid]
    sid = next(iter(project.specs))
    assert project.facts[sid]["layout"] == root / "docs" / "screens" / "layouts" / "elsewhere.json"
    made = root / "elsewhere.json"
    made.write_text(json.dumps({"type": "View", "id": "root"}), encoding="utf-8")
    world.file_changed(pid, str(made), 200, by=ROBOT)
    _settle(world, 200)
    first = project.specs[sid].by
    assert project.facts[sid]["layout"] == made   # the facts read again found it
    world.file_changed(pid, str(made), 300, by=ROBOT)
    _settle(world, 300)
    assert first is None and project.specs[sid].by == ROBOT
    assert next(s for s in _specs(state, pid) if s["id"] == sid).get("by") == ROBOT


def test_on_the_spot_the_same_file_belongs_to_its_spec_at_once(tmp_path):
    """The old way (tests, a replay) asks the file system at each edit: the first edit is the spec's."""
    root = _room(tmp_path, n=1)
    spec = root / "docs" / "screens" / "json" / "s0.spec.json"
    spec.write_text(json.dumps(_spec("s0", "elsewhere")), encoding="utf-8")
    world, _state, pid = _world(root, off_loop=False)
    made = root / "elsewhere.json"
    made.write_text("{}", encoding="utf-8")
    world.file_changed(pid, str(made), 200, by=ROBOT)
    assert next(iter(world.jsonui[pid].specs.values())).by == ROBOT


def test_a_test_file_changed_is_counted_in_the_worker(tmp_path, monkeypatch):
    root = _room(tmp_path)
    world, state, pid = _world(root, off_loop=True)
    fs = _LoopFs(monkeypatch)
    (root / "tests" / "screens" / "s0.test.json").write_text(json.dumps({"source": {"layout": "s0"}, "cases": [{"name": "a"}, {"name": "b"}]}), encoding="utf-8")
    fs.calls.clear()   # the test's own write
    world.file_changed(pid, str(root / "tests" / "screens" / "s0.test.json"), 50)
    assert fs.calls == {}
    _settle(world)
    assert next(s for s in _specs(state, pid) if s["name"] == "s0")["tests"]["total"] == 2


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                   env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
                        "GIT_COMMITTER_EMAIL": "t@t", "HOME": str(cwd), "PATH": "/usr/bin:/bin:/opt/homebrew/bin"})


def test_a_worktree_is_shown_from_the_workers_reading(tmp_path, monkeypatch):
    root = _room(tmp_path, n=2)
    _git(root, "init", "-q", "-b", "main")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "init")
    wt = tmp_path / "scratch" / "wt"
    _git(root, "worktree", "add", "-q", "-b", "feat/x", str(wt))
    (wt / "docs" / "screens" / "json" / "orders.spec.json").write_text(json.dumps(_spec("orders")), encoding="utf-8")
    world, state, pid = _world(root, off_loop=True)
    watched = []
    world.on_sources_changed = lambda project: watched.append(project.project_id)
    fs = _LoopFs(monkeypatch)
    world.apply_hook({"session_id": "wt", "cwd": str(wt), "hook_event_name": "SessionStart"}, 10)
    calls_from_the_hook = dict(fs.calls)
    world.tick(20)
    world.publish()
    assert fs.calls == calls_from_the_hook   # the tick's look at the worktrees is the worker's
    _settle(world, 30)
    ids = sorted(s["id"] for s in _specs(state, pid))
    assert f"{pid}:@feat/x/orders.spec.json" in ids and f"{pid}:@feat/x/s0.spec.json" in ids and watched == [pid]


@pytest.mark.parametrize("off_loop", [False, True])
def test_a_spec_deleted_leaves_the_slice(tmp_path, off_loop):
    root = _room(tmp_path)
    world, state, pid = _world(root, off_loop=off_loop)
    spec = root / "docs" / "screens" / "json" / "s2.spec.json"
    spec.unlink()
    world.file_changed(pid, str(spec), 50)
    _settle(world)
    assert sorted(s["name"] for s in _specs(state, pid)) == ["s0", "s1"]


def test_serve_reads_off_the_loop_and_a_replay_on_the_spot():
    source = Path(jsonui_project.__file__).parents[2].joinpath("commands", "viz_cmd.py").read_text(encoding="utf-8")
    assert "world.off_loop = not replay" in source
