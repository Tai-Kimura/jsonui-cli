"""A permission that has passed does not stay on the card (ticket 2026-11-05-viz-past-permission-stays-on-the-card).

The incident: a workflow's child asked for a Bash, the safety check's prompt timed out after 120 s, no hook came, the
child ended 3 minutes later, and the card stayed 許可待ち until its 10 minutes were up. The child's transcript is at
subagents/workflows/<run>/agent-<id>.jsonl, where viz did not look, and a child's end closed nothing. A card that really
waits stays: a parallel call's end, another agent's end and the main session's Stop with background work close nothing
of it. Nothing here starts claude.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from jui_cli.viz.ingest import World
from jui_cli.viz.sources.transcripts import transcript_path
from jui_cli.viz.state import VizState
from tests.test_viz_perm_call_result import CLASSIFIER, SAFETY, USER_NO

SID = "e2e00000-0000-4000-8000-00000000e001"
KID, OTHER = "a0411e1b020482606", "a5ub0000000000002"
CWD = "/work/app"
CMD = {"command": "rm -rf \"$OUT\"/raw"}
USAGE = {"input_tokens": 10, "output_tokens": 5, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}


def _hook(kind, **fields):
    return {"hook_event_name": kind, "session_id": SID, "cwd": CWD, **fields}


def _rec(path: Path, *blocks, role="user", **extra):
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps({"type": role, "timestamp": "2026-11-05T01:59:07Z", "message": {"role": role, "content": list(blocks), **extra}}) + "\n")


def _result(path: Path, use_id: str, text: str, is_error=True):
    _rec(path, {"type": "tool_result", "tool_use_id": use_id, "content": text, "is_error": is_error})


@pytest.fixture()
def world(tmp_path):
    """A World that finds transcripts in a real projects folder; the child's file is there from its start, as the CLI's is."""
    projects = tmp_path / "projects"
    main = projects / "-work-app" / f"{SID}.jsonl"
    main.parent.mkdir(parents=True)
    main.write_text("")
    w = World(VizState())
    w.transcript_path = transcript_path(projects)
    w.apply_hook(_hook("SessionStart", transcript_path=str(main)), 0)
    w.kid = _child(main, KID)
    return w


def _child(main: Path, aid: str, run="wf_8fbca537-af2") -> Path:
    path = main.parent / SID / "subagents" / "workflows" / run / f"agent-{aid}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("")
    return path


def _asks(w, use_id, aid=KID, at=1_000, tool_input=CMD):
    fields = {"agent_id": aid, "agent_type": "critic"} if aid else {}
    w.apply_hook(_hook("PreToolUse", tool_name="Bash", tool_use_id=use_id, tool_input=tool_input, **fields), at)
    w.apply_hook(_hook("PermissionRequest", tool_name="Bash", tool_input=tool_input, **fields), at + 1)
    w._poll_sub_usage(at + 2)   # first sight of the file: read from here on


def _statuses(w):
    return [(c["agentId"], c["status"]) for c in w.perms.items()]


# ---------------------------------------------------------------- finding the child's transcript


def test_a_workflows_child_is_found_in_its_runs_folder(tmp_path):
    projects = tmp_path / "projects"
    main = projects / "-work-app" / f"{SID}.jsonl"
    main.parent.mkdir(parents=True)
    main.write_text("")
    find = transcript_path(projects)
    assert find(SID, CWD, None, KID, None) is None
    kid = _child(main, KID)
    _child(main, OTHER, run="wf_another")
    assert find(SID, CWD, None, KID, None) == kid, "no hook's path while a child works: the folder is all there is"
    plain = main.parent / SID / "subagents" / f"agent-{KID}.jsonl"
    plain.write_text("")
    assert find(SID, CWD, None, KID, None) == plain, "the plain subagent's place first"


def test_the_runs_folder_takes_no_symlink_and_no_other_name(tmp_path):
    projects = tmp_path / "projects"
    main = projects / "-work-app" / f"{SID}.jsonl"
    main.parent.mkdir(parents=True)
    main.write_text("")
    kid = _child(main, KID)
    secret = tmp_path / "secret.jsonl"
    secret.write_text("x")
    kid.unlink()
    os.symlink(secret, kid)
    find = transcript_path(projects)
    assert find(SID, CWD, None, KID, None) is None
    assert find(SID, CWD, None, "../../../secret", None) is None
    (kid.parent.parent / "outside").symlink_to(tmp_path, target_is_directory=True)
    (tmp_path / f"agent-{OTHER}.jsonl").write_text("x")
    assert find(SID, CWD, None, OTHER, None) is None, "a run's folder that leads out of the projects folder"


# ---------------------------------------------------------------- the incident, and each way a child's call ends


@pytest.mark.parametrize("text,is_error,status,by", [
    (SAFETY, True, "expired", None),                  # the incident: the prompt timed out, no hook
    (USER_NO, True, "answered_in_terminal", "deny"),  # refused in the terminal, no hook
    (CLASSIFIER, True, "answered_in_terminal", "deny"),
    ("done", False, "answered_in_terminal", "allow"),  # it ran, and no hook said so
])
def test_the_childs_result_closes_its_card_while_the_child_works_on(world, text, is_error, status, by):
    _asks(world, "toolu_A")
    assert _statuses(world) == [(KID, "pending")]
    _result(world.kid, "toolu_A", text, is_error)
    world._poll_sub_usage(2_000)
    world.publish()
    (card,) = world.state.slices["perms"]
    assert (card["status"], card.get("terminalBehavior")) == (status, by)


def test_a_parallel_calls_result_does_not_close_a_card_that_really_waits(world):
    _asks(world, "toolu_A")
    _result(world.kid, "toolu_B", "other call's output", False)
    world._poll_sub_usage(2_000)
    world.apply_hook(_hook("PostToolUse", tool_name="Bash", tool_use_id="toolu_B", tool_input={"command": "ls"}, agent_id=KID, agent_type="critic"), 2_100)
    assert _statuses(world) == [(KID, "pending")]


def test_the_childs_bills_are_read_too(world):
    _asks(world, "toolu_A")
    _rec(world.kid, {"type": "text", "text": "x"}, role="assistant", id="msg_kid", model="claude-sonnet-5-5", usage=USAGE)
    billed = []
    world._bill = lambda aid, sid, got, at: billed.extend((aid, row[0]) for row in got or [])
    world._poll_sub_usage(2_000)
    assert billed == [(KID, "msg_kid")]


# ---------------------------------------------------------------- the end of a turn


def test_a_childs_end_closes_its_cards_and_only_its_own(world):
    _asks(world, "toolu_A")
    _asks(world, "toolu_O", aid=OTHER, tool_input={"command": "other"})
    _asks(world, "toolu_M", aid=None, tool_input={"command": "main"})
    world.apply_hook(_hook("SubagentStop", agent_id=KID, agent_type="critic"), 3_000)
    assert sorted(_statuses(world)) == sorted([(KID, "expired"), (OTHER, "pending"), (SID, "pending")])


def test_a_childs_end_reads_its_last_result_first(world):
    _asks(world, "toolu_A")
    _result(world.kid, "toolu_A", USER_NO)
    world.apply_hook(_hook("SubagentStop", agent_id=KID, agent_type="critic"), 3_000)
    world.publish()
    (card,) = world.state.slices["perms"]
    assert (card["status"], card["terminalBehavior"]) == ("answered_in_terminal", "deny")


def test_a_refusal_sent_from_the_page_ends_as_that_when_the_child_ends(world):
    _asks(world, "toolu_A")
    world.publish()
    (card,) = world.perms.perms.values()
    card["status"], card["sentBehavior"] = "sent", "deny"
    world.apply_hook(_hook("SubagentStop", agent_id=KID, agent_type="critic"), 3_000)
    assert _statuses(world) == [(KID, "deny")]


def test_stop_with_background_work_leaves_a_childs_card_that_really_waits(world):
    _asks(world, "toolu_A")
    _asks(world, "toolu_M", aid=None, tool_input={"command": "main"})
    world.apply_hook(_hook("Stop", background_tasks=[{"id": "b1"}]), 3_000)
    assert sorted(_statuses(world)) == sorted([(KID, "pending"), (SID, "expired")])
    world.apply_hook(_hook("Stop", background_tasks=[]), 4_000)
    assert sorted(_statuses(world)) == sorted([(KID, "expired"), (SID, "expired")]), "no background work: the turn is over for all"


def test_session_end_closes_everything(world):
    _asks(world, "toolu_A")
    world.apply_hook(_hook("SessionEnd"), 3_000)
    assert _statuses(world) == [(KID, "expired")]


def test_the_ten_minutes_are_still_the_last_word(world):
    from jui_cli.viz.permissions import EXPIRE_MS
    _asks(world, "toolu_A")
    world.perms.tick(1_001 + EXPIRE_MS - 1)
    assert _statuses(world) == [(KID, "pending")]
    world.perms.tick(1_001 + EXPIRE_MS)
    assert _statuses(world) == [(KID, "expired")]
