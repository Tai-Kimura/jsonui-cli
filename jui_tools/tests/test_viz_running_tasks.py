"""What each session runs in the background (ticket 2026-11-25-viz-show-running-tasks-of-local-sessions, viz/running.py).

The transcripts here are written by the test in the shapes measured on a live machine (11-25): a tool's result record
starts a task, a <task-notification> (a queue-operation record, then the user record) or TaskStop ends it.

Stop's background_tasks, raw payload: not yet captured (shell seen indirectly in a live viz's snapshot); a monitor is
never closed by Stop (not yet seen in the list).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from jui_cli.viz import running
from jui_cli.viz.ingest import World
from jui_cli.viz.running import Parser, Running
from jui_cli.viz.state import VizState

SID = "0f0f0f0f-1111-2222-3333-444444444444"
CWD = "/work/shop-app"
PID = 4242
T0 = 1_800_000_000_000
SHELL = "/bin/zsh -c source ~/.claude/shell-snapshots/snapshot-zsh-1800000000-abcd.sh && eval 'sleep 600'"


def iso(ms: int) -> str:
    from datetime import datetime, timezone
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def call(use: str, name: str, inp: dict, at: int) -> dict:
    return {"type": "assistant", "timestamp": iso(at), "message": {"content": [{"type": "tool_use", "id": use, "name": name, "input": inp}]}}


def result(use: str, r, at: int) -> dict:
    return {"type": "user", "timestamp": iso(at), "toolUseResult": r,
            "message": {"content": [{"type": "tool_result", "tool_use_id": use, "content": "ok"}]}}


def notice(tid: str, at: int, status: str | None = "completed", summary: str = "done", event: str | None = None,
           queued: bool = True) -> dict:
    body = f"<task-id>{tid}</task-id>\n" + (f"<status>{status}</status>\n" if status else "") + f"<summary>{summary}</summary>\n"
    if event is not None:
        body += f"<event>{event}</event>\n"
    text = f"<task-notification>\n{body}</task-notification>"
    if queued:
        return {"type": "queue-operation", "operation": "enqueue", "timestamp": iso(at), "content": text}
    return {"type": "user", "timestamp": iso(at), "message": {"content": text}}


def bash_start(tid: str, at: int, desc: str = "Run the suites", command: str = "make test TOKEN=s3cr3t") -> list[dict]:
    use = f"u-{tid}"
    return [call(use, "Bash", {"command": command, "description": desc, "run_in_background": True}, at),
            result(use, {"stdout": "", "stderr": "", "interrupted": False, "backgroundTaskId": tid}, at)]


def agent_start(aid: str, at: int, desc: str = "Write the login tests") -> list[dict]:
    use = f"u-{aid}"
    return [call(use, "Agent", {"description": desc, "prompt": "...", "run_in_background": True}, at),
            result(use, {"isAsync": True, "status": "async_launched", "agentId": aid, "description": desc}, at)]


def monitor_start(tid: str, at: int, timeout: int = 1_800_000, persistent: bool = False) -> list[dict]:
    use = f"u-{tid}"
    return [call(use, "Monitor", {"description": "watch the build log", "command": "tail -f build.log"}, at),
            result(use, {"taskId": tid, "timeoutMs": timeout, "persistent": persistent}, at)]


def workflow_start(tid: str, at: int) -> list[dict]:
    use = f"u-{tid}"
    return [call(use, "Workflow", {"script": "..."}, at),
            result(use, {"status": "async_launched", "taskId": tid, "taskType": "local_workflow",
                         "workflowName": "review-changes", "runId": "wf_0000"}, at)]


def task_stop(tid: str, at: int) -> list[dict]:
    use = f"u-stop-{tid}"
    return [call(use, "TaskStop", {"task_id": tid}, at),
            result(use, {"message": "stopped", "task_id": tid, "task_type": "local_bash", "command": "x"}, at)]


def parse(recs: list[dict]) -> list[tuple]:
    p, out = Parser(), []
    for r in recs:
        out.extend(p.feed(json.dumps(r, separators=(",", ":")).encode()))   # compact, as Claude Code writes
    return out


def book(recs: list[dict], at: int = T0) -> Running:
    b = Running()
    b.tail(SID, parse(recs), at)
    return b


def states(b: Running) -> dict[str, str]:
    return {t["id"]: t["state"] for (s, _), t in b.tasks.items() if s == SID}


# --------------------------------------------------------------------------- the transcript's records

def test_each_kind_starts_and_its_notice_ends_it():
    recs = [*bash_start("b1", T0), *agent_start("a1", T0 + 1), *monitor_start("m1", T0 + 2), *workflow_start("w1", T0 + 3)]
    b = book(recs)
    assert {t["id"]: t["kind"] for t in b.open_of(SID)} == {"b1": "bash", "a1": "agent", "m1": "monitor", "w1": "workflow"}
    b.tail(SID, parse([notice("b1", T0 + 10), notice("a1", T0 + 11, status="failed"), notice("w1", T0 + 12, status="killed")]), T0 + 20)
    assert states(b) == {"b1": "done", "a1": "done", "m1": "running", "w1": "done"}
    assert b.tasks[(SID, "a1")]["status"] == "failed"


def test_task_stop_ends_and_the_user_record_of_a_notice_ends_too():
    b = book([*bash_start("b1", T0), *bash_start("b2", T0)])
    b.tail(SID, parse(task_stop("b1", T0 + 5) + [notice("b2", T0 + 6, queued=False)]), T0 + 6)
    assert states(b) == {"b1": "done", "b2": "done"}
    assert b.tasks[(SID, "b1")]["status"] == "stopped"


def test_a_monitor_event_is_not_its_end_stream_ended_and_expired_are():
    b = book([*monitor_start("m1", T0), *monitor_start("m2", T0)])
    b.tail(SID, parse([notice("m1", T0 + 1, status=None, summary='Monitor event: "watch"', event="line 1: expired token refreshed")]), T0 + 1)
    assert states(b) == {"m1": "running", "m2": "running"}
    b.tail(SID, parse([notice("m1", T0 + 2, status="completed", summary='Monitor "watch" stream ended', event="done"),
                       notice("m2", T0 + 3, status=None, summary='Monitor event: "watch"',
                              event="[Monitor expired after 30m with no events delivered.]")]), T0 + 3)
    assert states(b) == {"m1": "done", "m2": "done"}


def test_an_agent_waiting_on_its_own_background_work_is_not_over():
    b = book(agent_start("a1", T0))
    b.tail(SID, parse([notice("a1", T0 + 5, summary='Agent "x" is waiting on its own background work')]), T0 + 5)
    assert states(b) == {"a1": "running"}
    assert b.tasks[(SID, "a1")]["waiting"] is True
    b.tail(SID, parse([notice("a1", T0 + 9, summary='Agent "x" completed')]), T0 + 9)
    assert states(b) == {"a1": "done"}


def test_the_command_line_is_never_shown_only_the_description():
    b = book(bash_start("b1", T0, desc="", command="deploy --password=hunter2"))
    row = b.slice_of(SID)[0]
    assert row["desc"] == ""
    assert "hunter2" not in json.dumps(b.slice_of(SID))


def test_a_line_without_any_marker_is_not_parsed():
    p = Parser()
    assert p.feed(b'{"type":"assistant","message":{"content":"plain"}}') == []
    assert p.feed(b"not json backgroundTaskId") == []


# --------------------------------------------------------------------------- the net and the limits

def test_no_shell_under_the_session_for_a_while_closes_bash_and_monitor():
    b = book([*bash_start("b1", T0), *monitor_start("m1", T0), *agent_start("a1", T0)])
    at = T0 + running.SHELL_GONE_MS
    assert b.shells(SID, 2, at) is False           # shells still there
    assert b.shells(SID, 0, at + 1_000) is False   # none: counted from now
    assert b.shells(SID, 0, at + running.SHELL_GONE_MS - 1) is False
    assert b.shells(SID, 0, at + running.SHELL_GONE_MS + 1_000) is True
    assert states(b) == {"b1": "done", "m1": "done", "a1": "running"}
    assert b.tasks[(SID, "b1")]["status"] == "gone"


def test_a_bash_started_just_now_is_not_closed_by_a_ps_taken_before_its_shell():
    b = Running()
    b.shells(SID, 0, T0)
    b.tail(SID, parse(bash_start("b1", T0 + running.SHELL_GONE_MS)), T0 + running.SHELL_GONE_MS)
    assert b.shells(SID, 0, T0 + running.SHELL_GONE_MS + 1_000) is False
    assert states(b) == {"b1": "running"}


def test_the_process_gone_closes_its_shells_at_once():
    b = book(bash_start("b1", T0))
    assert b.shells(SID, None, T0 + 1) is True
    assert states(b) == {"b1": "done"}


def test_limits_close_what_would_stay_open():
    b = book([*monitor_start("m1", T0, timeout=60_000), *monitor_start("m2", T0, timeout=60_000, persistent=True),
              *agent_start("a1", T0), *workflow_start("w1", T0)])
    b.caps(T0 + 60_000 + running.MONITOR_GRACE_MS, lambda s, a: T0)
    assert states(b) == {"m1": "done", "m2": "running", "a1": "running", "w1": "running"}
    b.caps(T0 + running.AGENT_QUIET_MS, lambda s, a: T0 + running.AGENT_QUIET_MS - 1_000)   # its transcript moved
    assert states(b)["a1"] == "running"
    b.caps(T0 + 2 * running.AGENT_QUIET_MS, lambda s, a: T0 + running.AGENT_QUIET_MS - 1_000)
    assert states(b)["a1"] == "done"
    b.caps(T0 + running.OPEN_CAP_MS, None)
    assert states(b) == {"m2": "done", "w1": "done"}   # m1 and a1 dropped: done longer than DONE_KEEP_MS


def test_an_ended_task_stays_a_minute_then_goes():
    b = book(bash_start("b1", T0))
    b.tail(SID, parse([notice("b1", T0 + 1)]), T0 + 1)
    assert b.caps(T0 + 1 + running.DONE_KEEP_MS - 1) == set()
    assert b.slice_of(SID)[0]["state"] == "done"
    assert b.caps(T0 + 1 + running.DONE_KEEP_MS) == {SID}
    assert b.slice_of(SID) == []


# --------------------------------------------------------------------------- Stop's background_tasks

def test_stop_without_the_key_closes_nothing():
    b = book([*bash_start("b1", T0), *agent_start("a1", T0)])
    assert b.stop_listed(SID, None, T0 + 1) is False
    assert states(b) == {"b1": "running", "a1": "running"}


def test_stop_closes_what_it_does_not_list_but_never_a_monitor():
    b = book([*bash_start("b1", T0), *bash_start("b2", T0), *agent_start("a1", T0), *monitor_start("m1", T0),
              *workflow_start("w1", T0)])
    assert b.stop_listed(SID, [{"id": "b2", "type": "shell", "status": "running"}], T0 + 1) is True
    assert states(b) == {"b1": "done", "b2": "running", "a1": "done", "m1": "running", "w1": "done"}
    assert b.stop_listed(SID, [], T0 + 2) is True   # empty: nothing in flight (but the monitor)
    assert states(b)["b2"] == "done" and states(b)["m1"] == "running"


def test_stop_naming_none_of_ours_closes_nothing():
    b = book([*bash_start("b1", T0), *agent_start("a1", T0)])
    assert b.stop_listed(SID, [{"id": "other-1", "type": "shell"}], T0 + 1) is False
    assert states(b) == {"b1": "running", "a1": "running"}


# --------------------------------------------------------------------------- what a subagent starts

def test_a_subagent_s_own_task_shows_while_it_runs_and_goes_with_it():
    b = book(agent_start("a1", T0))
    b.tail(SID, parse(bash_start("c1", T0 + 1)), T0 + 1, parent="a1")
    assert [(r["id"], r["parent"]) for r in b.slice_of(SID)] == [("a1", None), ("c1", "a1")]
    b.agent_stopped(SID, "a1", T0 + 5)
    assert [(r["id"], r["state"]) for r in b.slice_of(SID)] == [("a1", "done")]


# --------------------------------------------------------------------------- the past, read once

def _write(path: Path, recs: list[dict]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        for r in recs:
            fh.write(json.dumps(r, separators=(",", ":")) + "\n")
    return path.stat().st_size


def test_backscan_reads_up_to_where_the_tail_began_and_an_end_seen_since_wins(tmp_path):
    path = tmp_path / "t.jsonl"
    end = _write(path, [*bash_start("b1", T0), *bash_start("b2", T0), *agent_start("a1", T0), notice("a1", T0 + 1)])
    _write(path, bash_start("b3", T0 + 2))   # after the tail began: the tail reads it, the backscan does not
    b = Running()
    b.tail(SID, parse([notice("b2", T0 + 3)]), T0 + 3)
    b.backscan_done(SID, running.backscan(path, end), T0 + 4)
    assert states(b) == {"b1": "running"}   # a1 and b2 were over: not shown at all


def test_backscan_never_reads_through_a_symlink(tmp_path):
    real = tmp_path / "real.jsonl"
    end = _write(real, bash_start("b1", T0))
    link = tmp_path / "link.jsonl"
    os.symlink(real, link)
    assert running.backscan(link, end) == []
    assert running.backscan(real, end)[0][1] == "b1"


def test_meta_finished_is_read_only_from_a_small_regular_file(tmp_path):
    meta = tmp_path / "agent-a1.meta.json"
    meta.write_text(json.dumps({"description": "x"}))
    assert running.agent_finished(meta) is False
    meta.write_text(json.dumps({"description": "x", "finished": True}))
    assert running.agent_finished(meta) is True
    link = tmp_path / "agent-a2.meta.json"
    os.symlink(meta, link)
    assert running.agent_finished(link) is False


# --------------------------------------------------------------------------- through the server's World

def _world(tmp_path):
    projects = tmp_path / "projects"
    main = projects / "-work-shop-app" / f"{SID}.jsonl"
    world = World(VizState(), tool_input_max=50)

    def find(sid, cwd, given, agent_id=None, agent_given=None):
        if agent_id:
            return projects / "-work-shop-app" / sid / "subagents" / f"agent-{agent_id}.jsonl"
        return main if main.exists() else None
    world.transcript_path = find
    world.apply_session_file({"pid": PID, "sessionId": SID, "cwd": CWD, "status": "idle", "name": "lane-a"}, T0)
    return world, main


def _rows(world) -> list[tuple]:
    return [(r["id"], r["kind"], r["state"]) for r in world.sessions[SID].get("running", [])]


def test_world_shows_what_runs_from_the_past_and_the_tail(tmp_path):
    world, main = _world(tmp_path)
    _write(main, [*bash_start("b1", T0 - 60_000), *bash_start("b0", T0 - 60_000), notice("b0", T0 - 30_000)])
    world.poll_usage(T0)                              # first read: the past (backscan) — b1 still runs
    assert _rows(world) == [("b1", "bash", "running")]
    _write(main, [*monitor_start("m1", T0 + 1_000), notice("b1", T0 + 2_000)])
    world.poll_usage(T0 + 2_000)
    assert _rows(world) == [("m1", "monitor", "running"), ("b1", "bash", "done")]
    world.publish()
    sess = {s["id"]: s for s in world.state.slices["sessions"]}[SID]
    assert sess["running"][0]["desc"] == "watch the build log"
    world.tick(T0 + 2_000 + running.DONE_KEEP_MS)
    assert _rows(world) == [("m1", "monitor", "running")]


def test_world_stop_hook_and_session_end(tmp_path):
    world, main = _world(tmp_path)
    _write(main, [*bash_start("b1", T0), *monitor_start("m1", T0), *agent_start("a1", T0)])
    world.poll_usage(T0)
    world.apply_hook({"hook_event_name": "Stop", "session_id": SID, "cwd": CWD}, T0 + 1)   # no key
    assert {r[0] for r in _rows(world) if r[2] == "running"} == {"b1", "m1", "a1"}
    world.apply_hook({"hook_event_name": "Stop", "session_id": SID, "cwd": CWD,
                      "background_tasks": [{"id": "b1", "type": "shell", "status": "running"}]}, T0 + 2)
    assert {r[0] for r in _rows(world) if r[2] == "running"} == {"b1", "m1"}
    world.apply_hook({"hook_event_name": "SessionEnd", "session_id": SID, "cwd": CWD, "reason": "exit"}, T0 + 3)
    assert {r[0] for r in _rows(world) if r[2] == "running"} == set()


def test_world_subagent_stop_and_its_meta_file(tmp_path):
    world, main = _world(tmp_path)
    _write(main, [*agent_start("a1", T0), *agent_start("a2", T0)])
    world.poll_usage(T0)
    world.apply_hook({"hook_event_name": "SubagentStop", "session_id": SID, "cwd": CWD, "agent_id": "a1",
                      "agent_type": "general-purpose"}, T0 + 1)
    meta = main.parent / SID / "subagents" / "agent-a2.meta.json"
    meta.parent.mkdir(parents=True)
    meta.write_text(json.dumps({"finished": True}))
    world.tick(T0 + 1 + 30_000)
    assert {r[0]: r[2] for r in _rows(world)} == {"a1": "done", "a2": "done"}


def test_world_ps_net_closes_a_bash_whose_shell_is_gone(tmp_path):
    world, main = _world(tmp_path)
    _write(main, bash_start("b1", T0 - running.SHELL_GONE_MS))
    world.poll_usage(T0)
    assert PID in world.background_pids().values()          # the server's ps loop now looks at this session
    world.check_background([(PID, 1, "claude"), (PID + 1, PID, SHELL)], T0)
    assert _rows(world)[0][2] == "running"
    world.check_background([(PID, 1, "claude")], T0 + 1_000)
    world.check_background([(PID, 1, "claude")], T0 + 1_000 + running.SHELL_GONE_MS)
    assert _rows(world)[0][2] == "done"
