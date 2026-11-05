"""A permission that has passed does not stay on the card (ticket 2026-11-05-viz-past-permission-stays-on-the-card).

The incident: a workflow's child asked for a Bash, the safety check's prompt timed out after 120 s, no hook came, the
child ended 3 minutes later, and the card stayed 許可待ち until its 10 minutes were up. The child's transcript is at
subagents/workflows/<run>/agent-<id>.jsonl, where viz did not look, and a child's end closed nothing. A card that really
waits stays: a parallel call's end, another agent's end and the main session's Stop with background work close nothing
of it. Nothing here starts claude.
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import pytest

from jui_cli.viz import i18n
from jui_cli.viz.ingest import World
from jui_cli.viz.permissions import EXPIRE_MS, HOOK_WAIT_MS, STALE_MS, PermissionBook, stale_ms
from jui_cli.viz.questions import QuestionBook
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


# ---------------------------------------------------------------- time alone closes nothing
# ticket 2026-11-05-viz-ten-minute-expiry-removes-a-permission-still-waiting


def _old(world, at=1_001):
    world.perms.tick(at + STALE_MS - 1)
    assert not world.perms.items()[0].get("stale")
    assert world.perms.tick(at + STALE_MS) is True
    assert world.perms.tick(at + STALE_MS + 1) is False, "said once"


def test_ten_minutes_say_stale_and_the_card_stays_and_can_be_answered(world):
    _asks(world, "toolu_A")
    _old(world)
    (card,) = world.perms.items()
    assert card["status"] == "pending" and card["stale"] is True
    channel = world.perms.hello(SID, 1_000)
    raw = next(iter(world.perms.perms.values()))
    raw["_channel"], raw["_requestId"], raw["can"]["allowDeny"] = channel.id, "r1", True
    channel.open["r1"] = {"request_id": "r1"}
    assert world.perms.decide(card["id"], "allow", 1_001 + STALE_MS + 2) is None, "a late answer still goes"
    assert world.perms.items()[0]["status"] == "sent"


@pytest.mark.parametrize("ending", [
    lambda w: w.apply_hook(_hook("SessionEnd"), 900_000),
    lambda w: w.apply_hook(_hook("Stop", background_tasks=[]), 900_000),
    lambda w: w.apply_hook(_hook("SubagentStop", agent_id=KID, agent_type="critic"), 900_000),
    lambda w: (_result(w.kid, "toolu_A", SAFETY), w._poll_sub_usage(900_000)),
    lambda w: (w.session_proc.__setitem__(SID, (1, None, "cli")), w.end_vanished(set(), set(), 900_000)),
], ids=["session-end", "stop", "child-end", "its-result", "process-gone"])
def test_a_stale_card_ends_as_any_card_does(world, ending):
    _asks(world, "toolu_A")
    _old(world)
    ending(world)
    assert _statuses(world) == [(KID, "expired")]


def test_a_process_still_listed_closes_nothing(world):
    _asks(world, "toolu_A")
    world.session_proc[SID] = (1, None, "cli")
    assert world.end_vanished({SID}, set(), 900_000) == [] and world.end_vanished(set(), {SID}, 900_000) == []
    assert _statuses(world) == [(KID, "pending")]


def test_a_channel_only_card_says_stale_too_and_ends_with_the_turn():
    book = PermissionBook()
    channel = book.hello("s1", 0)
    assert book.channel_request(channel.id, {"request_id": "r1", "tool_name": "Bash", "description": "x", "input_preview": "{}"}, 0)
    book.tick(HOOK_WAIT_MS)
    (card,) = book.items()
    assert card["relayOnly"] is True
    book.tick(HOOK_WAIT_MS + STALE_MS)
    assert book.items()[0]["status"] == "pending" and book.items()[0]["stale"] is True
    assert book.items()[0]["can"]["allowDeny"] is False, "its channel has been silent: no buttons, as before"
    book.session_stopped("s1", HOOK_WAIT_MS + STALE_MS + 1)
    assert book.items()[0]["status"] == "expired"


def test_a_settled_card_still_goes_after_its_keeping_time():
    book = PermissionBook()
    book.from_hook("s1", "s1", "Bash", {"command": "x"}, "u", None, 0)
    book.session_stopped("s1", 5)
    book.tick(5 + EXPIRE_MS - 1)
    assert len(book.items()) == 1
    book.tick(5 + EXPIRE_MS)
    assert book.items() == []


def test_the_test_only_override_is_read_only_under_the_e2e(monkeypatch):
    monkeypatch.setenv("JUI_VIZ_STALE_MS", "5")
    monkeypatch.delenv("JUI_VIZ_E2E", raising=False)
    assert stale_ms() == STALE_MS
    monkeypatch.setenv("JUI_VIZ_E2E", "1")
    assert stale_ms() == 5


QUESTION = {"questions": [{"question": "どちら?", "header": "H", "options": [{"label": "A", "description": ""}, {"label": "B", "description": ""}]}]}


def test_a_question_says_stale_and_stays_until_the_session_moves_on():
    book = QuestionBook()
    card = book.from_hook("s1", "s1", QUESTION, "u", 0)
    book.tick(STALE_MS - 1)
    assert not card.get("stale")
    assert book.tick(STALE_MS) is True and book.tick(STALE_MS + 1) is False
    assert card["status"] == "pending" and book.items()[0]["stale"] is True
    book.tick(46_635_000)   # the longest this machine has waited
    assert card["status"] == "pending"
    assert book.session_stopped("s1", 46_635_001) and card["status"] == "expired"


def test_a_question_a_hook_waits_on_is_not_stale():
    book = QuestionBook()
    card = book.from_hook("s1", "s1", QUESTION, "u", 0)
    card["_future"] = object()
    book.tick(STALE_MS)
    assert not card.get("stale")


# ---------------------------------------------------------------- what the question's ticket measured
# ticket 2026-11-05-viz-question-card-closes-on-stop-with-background-work: nothing to fix, no child has ever asked


def test_a_mains_open_question_ends_with_stop_as_before(world):
    world.apply_hook(_hook("PreToolUse", tool_name="AskUserQuestion", tool_use_id="q1", tool_input=QUESTION), 1_000)
    world.apply_hook(_hook("Stop", background_tasks=[{"id": "b"}]), 2_000)
    assert [c["status"] for c in world.questions.items()] == ["expired"]


# ---------------------------------------------------------------- the words


@pytest.mark.parametrize("key", ["panel.perm.stale", "panel.q.stale", "panel.count.waiting.elsewhere", "panel.chip.ask.elsewhere",
                                 "panel.card.dismiss", "panel.card.dismissed", "panel.perm.dismiss.note", "panel.q.dismiss.note",
                                 "ev.perm.dismissed", "ev.question.dismissed", "act.dismissed"])
def test_every_word_is_in_both_languages(key):
    ja, en = i18n.bundled("ja"), i18n.bundled("en")
    assert ja.get(key) and en.get(key) and ja[key] != en[key], key


# ---------------------------------------------------------------- closing an old card by hand (the requester, 11-05: 残して手で閉じる)


def test_a_card_under_ten_minutes_cannot_be_closed_and_stays(world):
    _asks(world, "toolu_A")
    (card,) = world.perms.items()
    assert world.dismiss_perm(card["id"], 2_000) == "only a card over 10 minutes old can be closed"
    assert _statuses(world) == [(KID, "pending")]
    assert world.dismiss_perm("nope", 2_000) == "unknown permission"


def test_closing_an_old_card_sends_nothing_and_a_waiting_hook_prints_nothing(world):
    _asks(world, "toolu_A")
    channel = world.perms.hello(SID, 1_000)
    raw = next(iter(world.perms.perms.values()))
    raw["_channel"], raw["_requestId"] = channel.id, "r1"
    channel.open["r1"] = {"request_id": "r1"}
    loop = asyncio.new_event_loop()
    future = raw["_future"] = loop.create_future()
    raw["stale"] = True   # the channel still polling: _old's clock would have dropped it
    assert world.dismiss_perm(raw["id"], 700_000) is None
    assert future.result() == {}, "the hook prints nothing: neither allow nor deny"
    assert world.perms.items() == [] and channel.open == {} and channel.verdicts == []
    assert world.perms.take_verdicts(channel.id, 700_001) == []
    assert world.perms.take_prompts(channel.id) == [], "no words go to the session either"
    loop.close()


def test_a_verdict_not_yet_taken_is_dropped_with_the_card(world):
    _asks(world, "toolu_A")
    channel = world.perms.hello(SID, 1_000)
    raw = next(iter(world.perms.perms.values()))
    raw["_channel"], raw["_requestId"], raw["can"]["allowDeny"] = channel.id, "r1", True
    channel.open["r1"] = {"request_id": "r1"}
    assert world.perms.decide(raw["id"], "allow", 2_000) is None
    assert len(channel.verdicts) == 1
    raw["stale"] = True
    assert world.dismiss_perm(raw["id"], 700_000) is None
    assert channel.verdicts == [] and world.perms.items() == []


def test_what_comes_after_closing_finds_no_card_and_brings_none_back(world):
    _asks(world, "toolu_A")
    _old(world)
    card = world.perms.items()[0]
    assert world.dismiss_perm(card["id"], 700_000) is None
    who = {"agent_id": KID, "agent_type": "critic"}
    _result(world.kid, "toolu_A", SAFETY)
    world._poll_sub_usage(700_001)
    world.apply_hook(_hook("PostToolUse", tool_name="Bash", tool_use_id="toolu_A", tool_input=CMD, **who), 700_002)
    world.apply_hook(_hook("PermissionDenied", tool_name="Bash", tool_use_id="toolu_A", tool_input=CMD, reason="x", **who), 700_003)
    assert world.perms.items() == []
    assert world.dismiss_perm(card["id"], 700_004) == "unknown permission", "twice: refused, nothing breaks"
    assert world.perms.decide(card["id"], "allow", 700_005) == "unknown permission", "a late answer from an old page"
    world.publish()
    assert world.state.slices["perms"] == []


def test_the_robot_stops_waiting_unless_another_card_of_its_own_is_open(world):
    _asks(world, "toolu_A")
    _asks(world, "toolu_B", tool_input={"command": "other"}, at=1_100)
    world.perms.tick(1_101 + STALE_MS)
    a, b = world.perms.items()
    assert world.agents[KID]["state"] == "waiting"
    assert world.dismiss_perm(a["id"], 700_000) is None
    assert world.agents[KID]["state"] == "waiting", "the other card still waits"
    assert world.dismiss_perm(b["id"], 700_001) is None
    assert world.agents[KID]["state"] == "idle"
    kinds = [e["kind"] for e in world.state.events]
    assert kinds.count("PermissionDismissed") == 2


def test_closing_a_childs_card_leaves_the_mains_and_the_session_waiting(world):
    _asks(world, "toolu_M", aid=None, tool_input={"command": "main"})
    _asks(world, "toolu_A", at=1_100)
    world.perms.tick(1_101 + STALE_MS)
    mine = next(c for c in world.perms.items() if c["agentId"] == KID)
    world.sessions[SID]["status"] = "waiting"
    assert world.dismiss_perm(mine["id"], 700_000) is None
    assert world.agents[SID]["state"] == "waiting" and world.sessions[SID]["status"] == "waiting"
    other = world.perms.items()[0]
    assert world.dismiss_perm(other["id"], 700_001) is None
    assert world.sessions[SID]["status"] == "busy"


def test_a_question_under_ten_minutes_or_with_a_hook_waiting_cannot_be_closed():
    book = QuestionBook()
    card = book.from_hook("s1", "s1", QUESTION, "u", 0)
    assert book.dismiss(card["id"]) == "only a card over 10 minutes old can be closed"
    card["_future"] = object()
    card["hookWaiting"] = True
    book.tick(STALE_MS)
    assert book.dismiss(card["id"]) == "a hook waits on this question" and card["status"] == "pending"
    card["stale"] = True   # even so
    assert book.dismiss(card["id"]) == "a hook waits on this question"
    del card["_future"]
    assert book.dismiss(card["id"]) == "a hook waits on this question", "hookWaiting: not given up yet"
    card["waitEnded"] = True
    assert book.dismiss(card["id"]) is None and book.items() == []


def test_an_old_question_closed_finds_nothing_later(world):
    world.apply_hook(_hook("PreToolUse", tool_name="AskUserQuestion", tool_use_id="q1", tool_input=QUESTION), 1_000)
    assert world.agents[SID]["state"] == "waiting"
    world.questions.tick(1_000 + STALE_MS)
    card = world.questions.items()[0]
    assert world.dismiss_question(card["id"], 700_000) is None
    assert world.questions.items() == [] and world.agents[SID]["state"] == "idle" and world.sessions[SID]["status"] == "busy"
    world.apply_hook(_hook("PostToolUse", tool_name="AskUserQuestion", tool_use_id="q1", tool_input={**QUESTION, "answers": {"どちら?": "A"}}), 700_001)
    assert world.questions.items() == []
    assert world.dismiss_question(card["id"], 700_002) == "unknown question"
    (event,) = [e for e in world.state.events if e["kind"] == "QuestionDismissed"]
    assert event["text"].endswith(" H") and "?" not in event["text"], event["text"]


def test_the_words_say_nothing_goes_to_the_receiver():
    ja, en = i18n.bundled("ja"), i18n.bundled("en")
    for key, ja_says, en_says in (("panel.perm.dismiss.note", ("何も送りません", "許可も拒否もしません"), ("Nothing goes to the receiver", "neither allowed nor denied")),
                                  ("panel.q.dismiss.note", ("何も送りません", "答えません"), ("Nothing goes to the receiver", "no answer is given"))):
        assert all(w in ja[key] for w in ja_says), key
        assert all(w in en[key] for w in en_says), key
