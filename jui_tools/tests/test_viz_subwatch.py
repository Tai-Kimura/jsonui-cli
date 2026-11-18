"""A subagent that stopped moving (jui_cli/viz/subwatch.py, ingest.World._subwatch_tick; ticket
2026-11-18-viz-notify-main-when-a-subagent-quiets): told to its main session once per stretch of quiet, shown on the
page, never for one that stopped or whose main took its result."""
from __future__ import annotations

import os
import types

from jui_cli.viz import i18n
from jui_cli.viz.ingest import World
from jui_cli.viz.state import VizState
from jui_cli.viz.subwatch import CHECK_EVERY_MS, NOTICES_MAX, TIMEOUT_GRACE_MS, SubagentWatch

MIN = 60_000
T = 1_800_000_000_000
SID = "11111111-2222-4333-8444-555555555555"
AID = "a1b2c3d4e5f60718"


class FakeStat:
    """stat() of the transcripts by path: (size, mtime in s); a missing path raises."""
    def __init__(self):
        self.files: dict[str, tuple[int, float]] = {}
        self.calls = 0

    def __call__(self, path):
        self.calls += 1
        if path not in self.files:
            raise FileNotFoundError(path)
        size, mtime = self.files[path]
        return types.SimpleNamespace(st_size=size, st_mtime=mtime)


def watch(**kw):
    stat = FakeStat()
    return SubagentWatch(stat=stat, **kw), stat


def run(w, until, start=T):
    """Every check from start to until (once a minute, as the tick would): the notices and the moved, in order."""
    notices, moved, at = [], [], start
    while at <= until:
        if w.due(at):
            n, m = w.check(at)
            notices += n
            moved += m
        at += 30_000
    return notices, moved


# ---------------------------------------------------------------- the watch alone

def test_quiet_is_told_at_20_minutes_not_before():
    w, _ = watch()
    w.hook(AID, SID, T, "PreToolUse", tool="Read", tool_input={"file_path": "/a/b.py"}, use_id="u1")
    w.hook(AID, SID, T, "PostToolUse", tool="Read", use_id="u1")
    assert run(w, T + 19 * MIN + 59_000)[0] == []
    w.next_check = 0
    n, _ = w.check(T + 20 * MIN)
    assert [(x["kind"], x["since"], x["minutes"], x["tool"], x["head"]) for x in n] == [("quiet", T, 20, "Read", "/a/b.py")]


def test_told_once_per_stretch_again_after_it_moved_and_at_most_three_times():
    w, _ = watch()
    w.hook(AID, SID, T, "SubagentStart", agent_type="Explore")
    assert len(run(w, T + 60 * MIN)[0]) == 1                       # one stretch: one notice, however long
    t = T + 61 * MIN
    for i in range(NOTICES_MAX + 1):
        ended_a_told_stretch = i < NOTICES_MAX                         # the 4th quiet stretch is never told
        assert w.hook(AID, SID, t, "PreToolUse", tool="Bash", tool_input={"command": "ls"}, use_id=f"u{i}") is ended_a_told_stretch
        w.hook(AID, SID, t, "PostToolUse", tool="Bash", use_id=f"u{i}")
        n, _ = run(w, t + 21 * MIN, start=t)
        assert len(n) == (1 if i < NOTICES_MAX - 1 else 0), i      # the first, then two more: three in all
        t += 22 * MIN


def test_a_growing_transcript_is_moving():
    w, stat = watch()
    stat.files["/t/agent.jsonl"] = (100, T / 1000)
    w.hook(AID, SID, T, "SubagentStart", path="/t/agent.jsonl")
    assert run(w, T + 15 * MIN)[0] == []
    stat.files["/t/agent.jsonl"] = (900, (T + 15 * MIN) / 1000)   # the model wrote at 15 min
    assert run(w, T + 34 * MIN, start=T + 15 * MIN)[0] == []      # 19 min after that: still nothing
    n, _ = run(w, T + 36 * MIN, start=T + 34 * MIN)
    assert [x["since"] for x in n] == [T + 15 * MIN]
    stat.files["/t/agent.jsonl"] = (1200, (T + 37 * MIN) / 1000)
    w.next_check = 0
    assert w.check(T + 38 * MIN) == ([], [AID])                    # it moved again: the page's mark goes


def test_the_file_is_only_stated_once_a_minute_and_only_while_watched():
    w, stat = watch()
    assert not w.due(T)
    stat.files["/t/a.jsonl"] = (1, T / 1000)
    w.hook(AID, SID, T, "SubagentStart", path="/t/a.jsonl")
    run(w, T + 10 * MIN - 1)
    assert stat.calls == 10                                        # 0, 1, … 9 min
    w.drop(AID)
    assert not w.due(T + 11 * MIN) and w.watched == {}


def test_a_call_with_a_longer_timeout_of_its_own_is_given_it():
    w, _ = watch()
    w.hook(AID, SID, T, "PreToolUse", tool="Bash", tool_input={"command": "make e2e", "timeout": 25 * MIN}, use_id="u1")
    assert run(w, T + 30 * MIN - 1)[0] == []
    w.next_check = 0
    assert [x["kind"] for x in w.check(T + 25 * MIN + TIMEOUT_GRACE_MS)[0]] == ["quiet"]


def test_a_permission_unanswered_for_5_minutes_is_a_wait_and_not_also_quiet():
    w, _ = watch()
    w.hook(AID, SID, T, "PreToolUse", tool="Write", tool_input={"file_path": "/x/y.txt"}, use_id="u1")
    w.hook(AID, SID, T + 1000, "PermissionRequest", tool="Write", tool_input={"file_path": "/x/y.txt"})
    w.hook(AID, SID, T + 2000, "Notification")                    # its own notification: still waits
    n, _ = run(w, T + 60 * MIN)
    assert [(x["kind"], x["since"], x["tool"], x["head"]) for x in n] == [("wait", T + 1000, "Write", "/x/y.txt")]
    assert w.hook(AID, SID, T + 61 * MIN, "PostToolUse", tool="Write", use_id="u1") is True   # answered: moved


def test_a_question_waits_from_its_pre_tool_use():
    w, _ = watch()
    w.hook(AID, SID, T, "PreToolUse", tool="AskUserQuestion", tool_input={}, use_id="q1", question=True)
    n, _ = run(w, T + 6 * MIN)
    assert [x["kind"] for x in n] == ["wait"]


def test_zero_minutes_turns_a_kind_off():
    w, _ = watch(quiet_min=0, perm_min=0)
    w.hook(AID, SID, T, "SubagentStart")
    assert w.watched == {}
    w.configure(0, 5)
    w.hook(AID, SID, T, "PermissionRequest", tool="Bash", tool_input={"command": "rm x"})
    assert [x["kind"] for x in run(w, T + 120 * MIN)[0]] == ["wait"]


def test_drop_session_forgets_its_subagents_only():
    w, _ = watch()
    w.hook("a1", SID, T, "SubagentStart")
    w.hook("a2", "other", T, "SubagentStart")
    assert w.drop_session(SID) == ["a1"] and list(w.watched) == ["a2"]


# ---------------------------------------------------------------- in the world

class Channel:
    def __init__(self):
        self.inbox: list[dict] = []


def world_with(tmp_path, channel=True):
    world = World(VizState())
    stat = FakeStat()
    world.subwatch = SubagentWatch(stat=stat)
    ch = Channel()
    world.prompt_refusal = lambda sid: None if channel else (409, "no channel")
    world.perms.prompt_channel = lambda sid: ch if channel else None
    return world, ch, stat


def hook(world, kind, at, **fields):
    world.apply_hook({"hook_event_name": kind, "session_id": SID, "cwd": "/work/shop-app", **fields}, at)


def tick_to(world, until, start):
    at = start
    while at <= until:
        world.tick(at)
        at += 30_000


def test_the_main_session_is_told_once_and_the_page_shows_it(tmp_path):
    world, ch, stat = world_with(tmp_path)
    stat.files["/t/agent-a.jsonl"] = (10, T / 1000)
    hook(world, "UserPromptSubmit", T, prompt="go")
    hook(world, "SubagentStart", T, agent_id=AID, agent_type="general-purpose", agent_transcript_path="/t/agent-a.jsonl")
    hook(world, "PreToolUse", T + 1000, agent_id=AID, tool_name="Bash", tool_input={"command": "npm test"}, tool_use_id="u1")
    hook(world, "PostToolUse", T + 2000, agent_id=AID, tool_name="Bash", tool_input={"command": "npm test"}, tool_use_id="u1")
    tick_to(world, T + 25 * MIN, T)
    assert len(ch.inbox) == 1
    text = ch.inbox[0]["text"]
    assert text == i18n.tl("srv.stall.quiet", type="general-purpose", id=AID[:8], minutes=20, since=world_clock(T + 2000),
                           tool="Bash", head="npm test", path="/t/agent-a.jsonl")
    assert world.agents[AID]["stall"]["kind"] == "quiet" and world.agents[AID]["stall"]["told"] is True
    ev = [e for e in world.state.events if e["kind"] == "SubagentStall"]
    assert len(ev) == 1 and ev[0]["agentId"] == AID
    assert not any(e["kind"] == "PromptSent" for e in world.state.events)   # not a prompt from the page
    # it moves again: the mark goes, nothing more is sent
    hook(world, "PreToolUse", T + 26 * MIN, agent_id=AID, tool_name="Read", tool_input={"file_path": "/a"}, tool_use_id="u2")
    assert "stall" not in world.agents[AID] and len(ch.inbox) == 1


def world_clock(ms):
    from jui_cli.viz.ingest import clock_hhmm
    return clock_hhmm(ms)


def test_a_stopped_subagent_or_a_main_that_took_the_result_is_never_told(tmp_path):
    world, ch, _ = world_with(tmp_path)
    hook(world, "UserPromptSubmit", T, prompt="go")
    hook(world, "SubagentStart", T, agent_id="s1", agent_type="Explore")
    hook(world, "SubagentStart", T, agent_id="s2", agent_type="Explore")
    hook(world, "SubagentStop", T + MIN, agent_id="s1", agent_type="Explore")
    hook(world, "Stop", T + 2 * MIN)                               # the main's turn ended, nothing in the background
    tick_to(world, T + 60 * MIN, T)
    assert ch.inbox == [] and world.subwatch.watched == {}
    assert not any(e["kind"] == "SubagentStall" for e in world.state.events)


def test_a_background_subagent_is_still_watched_after_the_main_turn_ends(tmp_path):
    world, ch, _ = world_with(tmp_path)
    hook(world, "UserPromptSubmit", T, prompt="go")
    hook(world, "SubagentStart", T, agent_id=AID, agent_type="Explore")
    hook(world, "Stop", T + MIN, background_tasks=[{"id": AID}])
    tick_to(world, T + 25 * MIN, T)
    assert len(ch.inbox) == 1


def test_the_session_ending_drops_its_subagents(tmp_path):
    world, ch, _ = world_with(tmp_path)
    hook(world, "SubagentStart", T, agent_id=AID, agent_type="Explore")
    hook(world, "SessionEnd", T + MIN, reason="exit")
    tick_to(world, T + 30 * MIN, T)
    assert ch.inbox == [] and world.subwatch.watched == {}


def test_without_a_channel_the_page_alone_shows_it(tmp_path):
    world, ch, _ = world_with(tmp_path, channel=False)
    hook(world, "SubagentStart", T, agent_id=AID, agent_type="Explore")
    tick_to(world, T + 21 * MIN, T)
    ev = [e for e in world.state.events if e["kind"] == "SubagentStall"]
    assert len(ev) == 1 and ev[0]["text"].endswith(i18n.tl("ev.stall.notTold"))
    assert world.agents[AID]["stall"]["told"] is False


def test_a_permission_wait_is_told_after_5_minutes(tmp_path):
    world, ch, _ = world_with(tmp_path)
    hook(world, "SubagentStart", T, agent_id=AID, agent_type="Explore")
    hook(world, "PreToolUse", T, agent_id=AID, tool_name="Write", tool_input={"file_path": "/w/x"}, tool_use_id="u1")
    hook(world, "PermissionRequest", T + 1000, agent_id=AID, tool_name="Write", tool_input={"file_path": "/w/x"})
    tick_to(world, T + 7 * MIN, T)
    assert len(ch.inbox) == 1 and ch.inbox[0]["text"].startswith(i18n.tl("srv.stall.wait", type="Explore", id=AID[:8],
        since=world_clock(T + 1000), tool="Write", head="/w/x", path="-").split("\n")[0])
    assert world.agents[AID]["stall"]["kind"] == "wait"


def test_the_watch_is_cheap_when_nothing_is_watched():
    w, stat = watch()
    for i in range(2 * 60 * 24):                                   # a day of half-second ticks
        if w.due(T + i * 500):
            w.check(T + i * 500)
    assert stat.calls == 0 and w.watched == {} and os.environ is not None
