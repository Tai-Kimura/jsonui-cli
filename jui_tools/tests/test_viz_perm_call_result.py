"""A permission card that no hook settles is settled by its call's tool_result in the transcript (ticket
2026-10-29-viz-perm-card-stays-after-safety-check-denial).

The built-in safety check's prompt that nobody answers times out after about 120 s: no PostToolUse, no
PermissionDenied, and the turn goes on, so no Stop either. The card stayed 許可待ち while the session worked on. The
transcript has the call's result in every case (refused, timed out, or ran): the card is settled by that result's
tool_use_id, never by the order of the calls, since a parallel call may end while this one still waits. Nothing here
starts claude.
"""
from __future__ import annotations

import asyncio
import json

from jui_cli.viz.ingest import World
from jui_cli.viz.permissions import PermissionBook, outcome_of
from jui_cli.viz.sources.transcripts import UsageTail, results_of
from jui_cli.viz.state import VizState

SID = "e2e00000-0000-4000-8000-00000000d001"
SUB = "a5ub0000000000001"
#: The safety check's result as the incident's transcript has it (10-29 07:15:48Z), shortened after its first sentence
SAFETY = ("Permission for this command was denied by a built-in Claude Code safety check, not by the user. The check stops "
          "removals that can delete far more than intended. Only a person may approve such a removal, and no person did "
          "(the permission prompt timed out, or none was shown). The command was NOT run; do not claim it succeeded.")
USER_NO = ("The user doesn't want to proceed with this tool use. The tool use was rejected (eg. if it was a file edit, the "
           "new_string was NOT written to the file). STOP what you are doing and wait for the user to tell you how to proceed.")
CLASSIFIER = ("Permission for this action was denied by the Claude Code auto mode classifier. Reason: [Modify Shared "
              "Resources]. If you have other tasks that don't depend on this action, continue working on those.")
RM = 'FILES=(${(f)"$(git diff --name-only)"}) && git add -- $FILES && (cd web && rm -rf .next)'


def _hook(kind, **fields):
    return {"hook_event_name": kind, "session_id": SID, "cwd": "/work/app", **fields}


def _world():
    state = VizState()
    w = World(state)
    w.apply_hook(_hook("SessionStart"), 0)
    return w, state


def _cards(w, state):
    w.publish()
    return state.slices["perms"]


def _asks(w, use_id, cmd, at, **extra):
    """PreToolUse then PermissionRequest of one Bash call (the PermissionRequest carries no tool_use_id)."""
    w.apply_hook(_hook("PreToolUse", tool_name="Bash", tool_use_id=use_id, tool_input={"command": cmd}, **extra), at)
    w.apply_hook(_hook("PermissionRequest", tool_name="Bash", tool_input={"command": cmd}, **extra), at + 1)


def _result(w, use_id, cmd, text, is_error, at, aid=SID):
    w._call_results(SID, aid, [(use_id, "Bash", {"command": cmd}, is_error, text[:300], at)], at)


# ---------------------------------------------------------------- the pieces


def test_every_tool_result_is_read_with_its_call(tmp_path):
    path = tmp_path / "t.jsonl"
    path.write_text("")
    tail = UsageTail(path)
    tail.read()   # first sight: from the end
    recs = [
        {"type": "assistant", "timestamp": "2026-10-29T07:13:48Z", "message": {"id": "m1", "role": "assistant", "content": [
            {"type": "tool_use", "id": "toolu_A", "name": "Bash", "input": {"command": RM}},
            {"type": "tool_use", "id": "toolu_B", "name": "Read", "input": {"file_path": "/w/a"}}]}},
        {"type": "user", "timestamp": "2026-10-29T07:13:49Z", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "toolu_B", "content": [{"type": "text", "text": "1\tline"}]}]}},
        {"type": "user", "timestamp": "2026-10-29T07:15:48Z", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "toolu_A", "content": SAFETY, "is_error": True}]}},
    ]
    with open(path, "a") as f:
        for rec in recs:
            f.write(json.dumps(rec) + "\n")
    got = tail.read()["results"]
    assert [(u, n, i, e, h[:30]) for u, n, i, e, h, _ in got] == [
        ("toolu_B", "Read", {"file_path": "/w/a"}, False, "1\tline"),
        ("toolu_A", "Bash", {"command": RM}, True, SAFETY[:30])]
    assert got[1][5] == 1793258148000
    assert results_of({"type": "assistant", "message": {"content": [{"type": "tool_result", "tool_use_id": "x"}]}}) == []


def test_how_a_call_ended_is_told_by_its_results_start():
    assert outcome_of(True, SAFETY) == "timed_out"
    assert outcome_of(True, USER_NO) == "refused"
    assert outcome_of(True, CLASSIFIER) == "refused"
    assert outcome_of(True, "Exit code 1\nboom") == "ran"          # it ran and failed: allowed
    assert outcome_of(False, SAFETY) == "ran"                       # the text alone, without is_error, is output
    assert outcome_of(False, "") == "ran"


# ---------------------------------------------------------------- the incident


def test_the_safety_checks_timed_out_prompt_closes_its_card():
    """16:13:48 the card, 16:15:48 the refusal, the next Bash in the same turn: before the fix the card stayed
    pending (no hook settles it), and the header's 許可待ち 1 disagreed with the sessions' 許可待ち 0."""
    w, state = _world()
    _asks(w, "toolu_A", RM, 1_000)
    assert [c["status"] for c in _cards(w, state)] == ["pending"]
    w.apply_hook(_hook("PreToolUse", tool_name="Bash", tool_use_id="toolu_N", tool_input={"command": "git log -1"}), 121_000)
    assert [c["status"] for c in _cards(w, state)] == ["pending"], "the next call alone settles nothing"
    _result(w, "toolu_A", RM, SAFETY, True, 121_100)
    (card,) = _cards(w, state)
    assert card["status"] == "expired" and card["decidedAt"] == 121_100 and "decidedBy" not in card


def test_refused_or_run_results_settle_as_the_hooks_would():
    w, state = _world()
    _asks(w, "toolu_U", "rm a", 1_000)
    _result(w, "toolu_U", "rm a", USER_NO, True, 2_000)
    _asks(w, "toolu_R", "make", 3_000)
    _result(w, "toolu_R", "make", "Exit code 2\nmake: *** [all] Error 1", True, 4_000)
    a, b = _cards(w, state)
    assert (a["status"], a["terminalBehavior"]) == ("answered_in_terminal", "deny")
    assert (b["status"], b["terminalBehavior"]) == ("answered_in_terminal", "allow")


def test_the_hook_first_then_the_transcript_changes_nothing():
    w, state = _world()
    _asks(w, "toolu_A", "ls", 1_000)
    w.apply_hook(_hook("PostToolUse", tool_name="Bash", tool_use_id="toolu_A", tool_input={"command": "ls"}), 1_500)
    before = dict(_cards(w, state)[0])
    _result(w, "toolu_A", "ls", "a\nb", False, 3_000)
    assert _cards(w, state)[0] == before


# ---------------------------------------------------------------- parallel calls


def test_a_parallel_call_that_ends_does_not_close_the_waiting_card():
    """Measured 10-29: a Bash waited 795 s for the person while another Bash of the same message ran. The card was
    tied to the newest open Bash before; now to the open call with the same input, and only that call's result settles it."""
    w, state = _world()
    w.apply_hook(_hook("PreToolUse", tool_name="Bash", tool_use_id="toolu_W", tool_input={"command": "rm -rf build"}), 1_000)
    w.apply_hook(_hook("PreToolUse", tool_name="Bash", tool_use_id="toolu_P", tool_input={"command": "git status"}), 1_001)
    w.apply_hook(_hook("PermissionRequest", tool_name="Bash", tool_input={"command": "rm -rf build"}), 1_002)
    w.apply_hook(_hook("PostToolUse", tool_name="Bash", tool_use_id="toolu_P", tool_input={"command": "git status"}), 2_000)
    _result(w, "toolu_P", "git status", "clean", False, 2_100)
    assert [c["status"] for c in _cards(w, state)] == ["pending"], "the other call ran: this one still waits"
    _result(w, "toolu_W", "rm -rf build", USER_NO, True, 796_000)
    (card,) = _cards(w, state)
    assert (card["status"], card["terminalBehavior"]) == ("answered_in_terminal", "deny")


def test_a_card_without_its_id_is_taken_only_when_it_is_the_one_with_that_input():
    book = PermissionBook()
    a = book.from_hook(SID, SID, "Bash", {"command": "rm x"}, None, None, 1_000)
    b = book.from_hook(SID, SID, "Bash", {"command": "rm x"}, None, None, 5_000)   # past DEDUPE_MS: a second card
    assert a is not b
    assert book.call_result(SID, SID, "toolu_1", "Bash", {"command": "rm x"}, "timed_out", 9_000) is None   # two: no guess
    assert book.call_result(SID, SID, "toolu_1", "Bash", {"command": "rm y"}, "timed_out", 9_000) is None
    book._resolve(b, "answered_in_terminal", 9_500)
    assert book.call_result(SID, SID, "toolu_1", "Bash", {"command": "rm x"}, "timed_out", 10_000) is a
    assert a["status"] == "expired"
    c = book.from_hook(SID, SUB, "Bash", {"command": "rm z"}, None, None, 11_000)
    assert book.call_result(SID, SID, "toolu_2", "Bash", {"command": "rm z"}, "ran", 12_000) is None   # another agent's
    assert c["status"] == "pending"


# ---------------------------------------------------------------- the kinds of card


def test_a_subagents_card_is_settled_by_its_own_transcript():
    w, state = _world()
    extra = {"agent_id": SUB, "agent_type": "general-purpose"}
    _asks(w, "toolu_S", RM, 1_000, **extra)
    w.apply_hook(_hook("PreToolUse", tool_name="Bash", tool_use_id="toolu_S2", tool_input={"command": "ls"}, **extra), 121_000)
    _result(w, "toolu_S", RM, SAFETY, True, 121_100, aid=SUB)
    (card,) = _cards(w, state)
    assert card["agentId"] == SUB and card["status"] == "expired"


def test_a_sent_card_and_a_waiting_decide_hook_are_settled_too():
    book = PermissionBook()
    sent = book.from_hook(SID, SID, "Bash", {"command": "make"}, "toolu_1", None, 1_000)
    sent.update(status="sent", sentBehavior="allow")
    assert book.call_result(SID, SID, "toolu_1", "Bash", {"command": "make"}, "ran", 2_000) is sent
    assert (sent["status"], sent["decidedBy"]) == ("allow", "browser")
    sent2 = book.from_hook(SID, SID, "Bash", {"command": RM}, "toolu_2", None, 3_000)
    sent2.update(status="sent", sentBehavior="allow")
    book.call_result(SID, SID, "toolu_2", "Bash", {"command": RM}, "timed_out", 4_000)
    assert sent2["status"] == "expired", "the page's allow did not run it: the check still wanted a person"

    loop = asyncio.new_event_loop()
    try:
        waiting = book.from_hook(SID, SID, "Bash", {"command": "rm q"}, "toolu_3", None, 5_000, source="decide")
        future = loop.create_future()
        book.hook_waiting(waiting, future)
        book.call_result(SID, SID, "toolu_3", "Bash", {"command": "rm q"}, "timed_out", 6_000)
        assert waiting["status"] == "expired" and future.done() and future.result() == {}   # the hook prints nothing
    finally:
        loop.close()


def test_the_transcript_poll_closes_the_card(tmp_path):
    """The whole path: World.poll_usage reads the session's transcript every 2 s (viz_cmd) and the card goes."""
    path = tmp_path / f"{SID}.jsonl"
    path.write_text("")
    w, state = _world()
    w.transcript_path = lambda sid, cwd, given, *rest: path if sid == SID else None
    w.poll_usage(500)   # first sight: from the end
    _asks(w, "toolu_A", RM, 1_000)
    with open(path, "a") as f:
        f.write(json.dumps({"type": "assistant", "timestamp": "2026-10-29T07:13:48Z", "message": {"id": "m1", "role": "assistant",
                            "content": [{"type": "tool_use", "id": "toolu_A", "name": "Bash", "input": {"command": RM}}]}}) + "\n")
        f.write(json.dumps({"type": "user", "timestamp": "2026-10-29T07:15:48Z", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "toolu_A", "content": SAFETY, "is_error": True}]}}) + "\n")
    assert [c["status"] for c in _cards(w, state)] == ["pending"]
    w.poll_usage(121_000)
    assert [c["status"] for c in _cards(w, state)] == ["expired"]
