"""A storm of file changes does not hold the server (the ENOSPC night of 2026-11-09; ticket
2026-11-06-viz-e2e-full-run-red-under-load, its section 「ENOSPC の serve の読み」).

That night the live serve stopped answering /health for over a minute: its loop was in specs_touching (each file
change compared with every spec, relatedFile and root), each change was one call on the loop with its own publish, the
rooms' watchers were started again on folders the old ones still held ("already scheduled"), and a session its hooks
kept bringing back was ended again at every poll. Measured on 2.5.16 with these arms' shapes: 10 000 changes in a room
of 300 specs held the loop 45.8 s (2 000: 9.3 s); the session was ended 10 times in 10 polls.

(a) specs_touching looks the path up in a table built from the specs and the last build's facts, and answers as the
comparison did. (b) ChangeBatch hands the changes to the loop in batches, one publish each. (c) Watchers keeps a
room's watcher while its folders are the same, and joins one it replaces. (d) a session ended as vanished has its
process forgotten, so its hooks bringing it back do not end it again; one that is really gone still ends.
"""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

import pytest

from jui_cli.viz.change_batch import ChangeBatch, Watchers
from jui_cli.viz.ingest import World
from jui_cli.viz.state import VizState

from tests.test_viz_files_off_the_loop import _room, _settle, _world

#: what 10 000 changes may hold the loop for (2.5.16: 45.8 s; the table: about 0.05 s)
STORM_BOUND_SEC = 3.0


# ---------------------------------------------------------------- (a) specs_touching looked up


def test_a_storm_of_changes_holds_the_loop_briefly(tmp_path):
    root = _room(tmp_path, n=300, related=5)
    world, _state, pid = _world(root, off_loop=True)
    layouts = root / "docs" / "screens" / "layouts"
    for i in range(10_000):   # what the watcher hands over: .json files under a watched folder, none a spec's
        world.file_changed(pid, str(layouts / f"churn/f{i}.json"), 200)
    for job, _ in list(world._files_jobs):
        job.result(timeout=120)
    start = time.perf_counter()
    world._files_apply()
    took = time.perf_counter() - start
    assert not world._files_jobs
    assert took < STORM_BOUND_SEC, f"10 000 changes held the loop {took:.2f} s"


def _compared(project, file_path: str) -> list[str]:
    """specs_touching as 2.5.16 answered it off the loop: every spec compared."""
    target = Path(file_path)
    hits = []
    for sid, entry in project.specs.items():
        if target == entry.path:
            hits.append(sid)
            continue
        facts = project.facts.get(sid)
        if facts is None:
            continue
        lp, roots = facts["layout"], facts["roots"]
        declared = [Path(item["path"]) for item in (entry.data or {}).get("relatedFiles") or []
                    if isinstance(item, dict) and isinstance(item.get("path"), str)]
        if (lp and target == lp) or any(target == (d if d.is_absolute() else r / d) for d in declared for r in roots):
            hits.append(sid)
    return hits


def test_the_table_answers_as_the_comparison_did(tmp_path):
    root = _room(tmp_path, n=12, related=3)
    world, _state, pid = _world(root, off_loop=True)
    project = world.jsonui[pid]
    paths = [str(e.path) for e in project.specs.values()]
    for facts in project.facts.values():
        if facts["layout"]:
            paths.append(str(facts["layout"]))
        for r in facts["roots"]:
            paths += [str(r / f"src/s{i}_{k}.swift") for i in range(12) for k in range(3)]
    paths += [str(root / "docs/screens/layouts/none.json"), str(root / "src/other.swift"), "/elsewhere/x.json"]
    asked = 0
    for p in paths:
        assert project.specs_touching(p) == _compared(project, p), p
        asked += 1
    assert asked > 100 and any(project.specs_touching(p) for p in paths)   # the table answers something, the same
    # a spec read again is in the table from then on (the table is built again when the specs change)
    spec = next(iter(project.specs.values())).path
    world.file_changed(pid, str(spec), 300)
    _settle(world, 300)
    assert project.specs_touching(str(spec)) == _compared(project, str(spec)) != []


# ---------------------------------------------------------------- (b) the changes in batches


def test_changes_from_the_watchers_thread_reach_the_loop_in_batches():
    asked: list = []
    applied: list = []
    published: list = []
    batch = ChangeBatch(asked.append, lambda pid, path: applied.append((pid, path)), lambda: published.append(1))

    def watcher():
        for i in range(10_000):
            batch.add("room-a" if i % 2 else "room-b", f"/w/f{i % 5000}.json")   # each path twice

    t = threading.Thread(target=watcher)
    t.start()
    t.join()
    assert len(asked) == 1, "one call on the loop for the whole storm"
    assert asked[0]() == 10_000 // 2 and len(published) == 1
    assert len(set(applied)) == len(applied) == 5000          # each path once per room
    assert [p for r, p in applied if r == "room-b"][:2] == ["/w/f0.json", "/w/f2.json"]   # in the order they came
    batch.add("room-a", "/w/late.json")                       # a change after the batch: the next one
    assert len(asked) == 2 and asked[1]() == 1 and len(published) == 2
    assert asked[1]() == 0 and len(published) == 2            # nothing left: no publish


# ---------------------------------------------------------------- (c) a room's watcher kept


class _Observer:
    def __init__(self, log, n):
        self.log, self.n = log, n

    def stop(self):
        self.log.append(("stop", self.n))

    def join(self, timeout=None):
        self.log.append(("join", self.n))


class _Room:
    project_id = "room"


def test_the_same_folders_keep_their_watcher_and_one_replaced_is_joined_first():
    log: list = []
    folders = [Path("/r/specs"), Path("/r/layouts")]
    started: list = []

    def start(project):
        o = _Observer(log, len([e for e in log if e[0] == "start"]))
        log.append(("start", o.n))
        return o

    w = Watchers(lambda p: list(folders), start, started)
    assert w.watch(_Room()) is True
    for _ in range(20):                       # the room's apps read again and again, the same folders
        assert w.watch(_Room()) is False
    w.settle(5)
    assert log == [("start", 0)] and len(started) == 1
    folders.append(Path("/r/tests"))          # a folder came: watched again, the old one let go first
    assert w.watch(_Room()) is True
    w.settle(5)
    assert log == [("start", 0), ("stop", 0), ("join", 0), ("start", 1)]
    assert [o.n for o in started] == [1]


class _HeldObserver(_Observer):
    """Its stop (or its start) waits until let go, 20 s at most: FSEvents' stop and start took 20 to 68 s when
    fseventsd was busy (ticket 2026-11-12-viz-loop-stalls-on-watcher-stop)."""

    def __init__(self, log, n, go):
        super().__init__(log, n)
        self.go = go

    def stop(self):
        self.log.append(("stop", self.n))
        self.go.wait(20)


@pytest.mark.parametrize("held", ["the old one's stop", "the new one's start"])
def test_a_watcher_held_in_its_stop_or_start_does_not_hold_the_caller(held):
    """Watchers.watch runs on the loop's thread (a room's worktrees changed): it hands the stop, the join and the start
    to its worker and returns at once. Until 2.5.31 it called them itself, and the loop answered nothing for 20 to 68 s.
    The order stays: the old one stopped and joined before the new one starts (the ENOSPC night of 2026-11-09)."""
    log: list = []
    go = threading.Event()
    folders = [Path("/r/specs")]
    started: list = []

    def start(project):
        n = len([e for e in log if e[0] == "start"])
        if held == "the new one's start" and n == 1:
            log.append(("start", n))
            go.wait(20)
            return _Observer(log, n)
        log.append(("start", n))
        return _HeldObserver(log, n, go) if held == "the old one's stop" else _Observer(log, n)

    w = Watchers(lambda p: list(folders), start, started)
    try:
        assert w.watch(_Room()) is True
        w.settle(5)
        folders.append(Path("/r/tests"))
        t0 = time.monotonic()
        assert w.watch(_Room()) is True
        assert w.watch(_Room()) is False      # the same folders again while the swap is under way: no second swap
        took = time.monotonic() - t0
        assert took < 1.0, f"watch waited {took:.1f} s on {held}"
    finally:
        go.set()
    w.settle(5)
    assert log == [("start", 0), ("stop", 0), ("join", 0), ("start", 1)]
    assert [o.n for o in started] == [1]


def test_watchers_closed_hand_back_the_running_ones_and_start_no_more():
    log: list = []
    folders = [Path("/r/specs")]
    w = Watchers(lambda p: list(folders), lambda p: _Observer(log, 0), [])
    w.watch(_Room())
    w.settle(5)
    running = w.close()
    assert [o.n for o in running] == [0] and w.started == []
    folders.append(Path("/r/tests"))
    assert w.watch(_Room()) is False          # closed: nothing more is started


# ---------------------------------------------------------------- (d) a session its hooks bring back


def _hook(world: World, sid: str, at: int) -> None:
    world.apply_hook({"session_id": sid, "cwd": "/work/x", "hook_event_name": "PreToolUse", "tool_name": "Read",
                      "tool_input": {"file_path": "/work/x/a"}}, at)


def _known(world: World, sid: str, pid: int, at: int) -> None:
    world.apply_session_file({"pid": pid, "sessionId": sid, "cwd": "/work/x", "entrypoint": "cli", "status": "idle",
                              "procStart": "Thu Oct 29 00:00:00 2026"}, at)


def test_a_session_its_hooks_bring_back_is_ended_once_not_at_every_poll():
    w = World(VizState(100))
    _known(w, "s-back", 11, 1000)
    ended = []
    for i in range(10):                       # gone from the list and the registry, its hooks still coming
        at = 2000 + i * 3000
        ended += w.end_vanished(set(), set(), at)
        _hook(w, "s-back", at + 1000)
    assert ended == ["s-back"], ended         # 2.5.16: ended 10 times in 10 polls
    assert w.sessions["s-back"]["status"] != "ended"
    assert len([e for e in w.state.recent_events() if e["kind"] == "SessionEnd"]) == 1


def test_a_session_really_gone_still_ends_and_one_known_again_can_end_again():
    w = World(VizState(100))
    _known(w, "s-dead", 21, 1000)
    _known(w, "s-alive", 22, 1000)
    assert w.end_vanished({"s-alive"}, set(), 2000) == ["s-dead"]
    assert w.sessions["s-dead"]["status"] == "ended" and w.sessions["s-alive"]["status"] != "ended"
    assert w.end_vanished({"s-alive"}, set(), 5000) == []          # ended once
    # it comes back with a process (a resumed session's entry): known again, and ended again once it is gone
    _known(w, "s-dead", 23, 6000)
    _hook(w, "s-dead", 6500)
    assert w.end_vanished({"s-dead", "s-alive"}, set(), 8000) == []
    assert w.end_vanished({"s-alive"}, set(), 11000) == ["s-dead"]


def test_a_room_whose_watcher_did_not_start_is_tried_again_after_a_while():
    """FSEvents would not start (fs_watch gave None): the room is without a watcher, and tried again on a watch at least
    RETRY_SEC later, not at every one (fseventsd in trouble is not asked over and over)."""
    log: list = []
    folders = [Path("/r/specs")]

    def start(project):
        log.append("start")
        return None

    w = Watchers(lambda p: list(folders), start, [])
    w.RETRY_SEC = 0.3
    assert w.watch(_Room()) is True
    w.settle(5)
    assert w.watch(_Room()) is False          # too soon
    time.sleep(0.4)
    assert w.watch(_Room()) is True           # tried again
    w.settle(5)
    assert log == ["start", "start"]


# ---------------------------------------------------------------- (e) a stream FSEvents would not start


@pytest.mark.skipif(sys.platform != "darwin", reason="FSEvents is macOS's")
def test_a_stream_fsevents_did_not_start_is_let_go_without_stopping_it(tmp_path, monkeypatch):
    """After fseventsd was restarted its streams would not start ("Cannot start fsevents stream"); the stream stays
    registered unstarted, and stopping the observer called FSEventStreamStop on it: SIGSEGV (2026-11-12 16:36). The
    observer is let go without that call, and the caller is told it has no watcher. The FSEvents calls are stand-ins
    here, so the case cannot end the process."""
    import _watchdog_fsevents as native
    from watchdog.events import FileSystemEventHandler
    from jui_cli.viz.sources import fs_watch

    calls: list = []

    def add_watch(*a):
        calls.append("add_watch")
        raise SystemError("Cannot start fsevents stream. Use a kqueue or polling observer instead.")

    monkeypatch.setattr(native, "add_watch", add_watch)
    monkeypatch.setattr(native, "remove_watch", lambda *a: calls.append("remove_watch"))
    monkeypatch.setattr(native, "stop", lambda *a: calls.append("stop"))
    obs = fs_watch.observer()
    obs.schedule(FileSystemEventHandler(), str(tmp_path), recursive=True)
    obs.daemon = True
    obs.start()
    assert fs_watch.kept_or_none(obs, "a test folder") is None
    assert calls == ["add_watch"], calls      # never stopped through FSEvents


@pytest.mark.skipif(sys.platform != "darwin", reason="FSEvents is macOS's")
def test_a_stream_that_started_is_kept_and_stopped_as_before(tmp_path):
    """The control: FSEvents as it is; the watcher is kept, sees a file written, and stops."""
    from watchdog.events import FileSystemEventHandler
    from jui_cli.viz.sources import fs_watch

    seen = threading.Event()

    class Handler(FileSystemEventHandler):
        def on_any_event(self, event):
            if event.src_path.endswith("a.json"):
                seen.set()

    obs = fs_watch.observer()
    obs.schedule(Handler(), str(tmp_path), recursive=True)
    obs.daemon = True
    obs.start()
    try:
        assert fs_watch.kept_or_none(obs, "a test folder") is obs
        (tmp_path / "a.json").write_text("{}")
        assert seen.wait(10), "no event from FSEvents"
    finally:
        obs.stop()
        obs.join(timeout=5)
    assert not obs.is_alive()
