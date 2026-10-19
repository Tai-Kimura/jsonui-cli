"""A robot's act stops saying it waits once the wait is over, and says so while it is on
(ticket 2026-10-19-jui-viz-act-stays-question-waiting-after-answer).

Seen: a question answered on the page, then PostToolUse (AskUserQuestion, with the answers): the robot went idle and
its badge said 待機, but its act — the session row's second line — still said 「質問に回答待ち 選択」. PostToolUse took
「許可待ち 」 off the act and nothing else, and only when no other call of the robot was open. Every way a wait ends is
a row here (the family table in the ticket), each with the act and the state while waiting and after.
"""
from __future__ import annotations

import asyncio

import pytest

from jui_cli.viz.ingest import World
from jui_cli.viz.state import VizState

S, CWD = "s-act", "/work/act"
Q = {"questions": [{"question": "どれにする?", "header": "選択", "options": [{"label": "A"}, {"label": "B"}], "multiSelect": False}]}
ANSWERED = {**Q, "answers": {"どれにする?": "A"}}
CMD = {"command": "npm publish"}
WAIT_WORDS = ("回答待ち", "許可待ち")


def _world() -> World:
    w = World(VizState(100))
    w.apply_hook({"hook_event_name": "SessionStart", "session_id": S, "cwd": CWD, "source": "startup"}, 1)
    return w


def _h(w: World, at: int, **payload) -> None:
    w.apply_hook({"session_id": S, "cwd": CWD, **payload}, at)


def ask(w):
    _h(w, 10, hook_event_name="PreToolUse", tool_name="AskUserQuestion", tool_input=Q, tool_use_id="q1")


def perm(w):
    _h(w, 10, hook_event_name="PreToolUse", tool_name="Bash", tool_input=CMD, tool_use_id="b1")
    _h(w, 11, hook_event_name="PermissionRequest", tool_name="Bash", tool_input=CMD)


def other_open(w):
    _h(w, 9, hook_event_name="PreToolUse", tool_name="Read", tool_input={"file_path": "/work/act/a.txt"}, tool_use_id="r1")


def _answer_on_page(w):
    """What the page's answer does: the --ask hook waits on the card (a future), the page answers it."""
    card = next(iter(w.questions.cards.values()))
    loop = asyncio.new_event_loop()
    try:
        w.question_waiting(card, loop.create_future(), 10_000, 300_000)
        assert w.answer_question(card["id"], {"どれにする?": {"labels": ["A"]}}, 20) is None
    finally:
        loop.close()


def answer_on_page(w):
    _answer_on_page(w)
    _h(w, 21, hook_event_name="PostToolUse", tool_name="AskUserQuestion", tool_input=ANSWERED, tool_use_id="q1")


def q_post(w):
    _h(w, 21, hook_event_name="PostToolUse", tool_name="AskUserQuestion", tool_input=ANSWERED, tool_use_id="q1")


def b_post(w, kind="PostToolUse"):
    _h(w, 21, hook_event_name=kind, tool_name="Bash", tool_input=CMD, tool_use_id="b1")


def next_pre(w):
    _h(w, 21, hook_event_name="PreToolUse", tool_name="Read", tool_input={"file_path": "/work/act/b.txt"}, tool_use_id="r2")


END = {
    "Stop": lambda w: _h(w, 21, hook_event_name="Stop"),
    "UserPromptSubmit": lambda w: _h(w, 21, hook_event_name="UserPromptSubmit", prompt="次"),
    "idle_prompt": lambda w: _h(w, 21, hook_event_name="Notification", notification_type="idle_prompt", message="x"),
    "SessionEnd": lambda w: _h(w, 21, hook_event_name="SessionEnd", reason="other"),
}

# (row, start, end, act after or None for "any act without a wait word")
ROWS = [
    ("question answered on the page, then PostToolUse", ask, answer_on_page, "質問の回答を受けた"),
    ("question answered in the terminal: PostToolUse", ask, q_post, "質問の回答を受けた"),
    ("question declined in the terminal: PostToolUseFailure", ask,
     lambda w: _h(w, 21, hook_event_name="PostToolUseFailure", tool_name="AskUserQuestion", tool_input=Q, tool_use_id="q1"), "質問に回答なし"),
    ("question answered while another call is open", lambda w: (other_open(w), ask(w)), q_post, "質問の回答を受けた"),
    ("question, then the next PreToolUse", ask, next_pre, "Read b.txt"),
    ("permission allowed (page or terminal): PostToolUse", perm, b_post, "Bash npm publish"),
    ("permission allowed, the call failed: PostToolUseFailure", perm, lambda w: b_post(w, "PostToolUseFailure"), "Bash npm publish"),
    ("permission denied: PermissionDenied", perm, lambda w: _h(w, 21, hook_event_name="PermissionDenied", tool_name="Bash", tool_input=CMD, tool_use_id="b1"), "拒否 Bash"),
    ("permission denied with no event, then the next PreToolUse", perm, next_pre, "Read b.txt"),
    ("permission allowed while another call is open", lambda w: (other_open(w), perm(w)), b_post, "Bash npm publish"),
] + [(f"{what}, then {end}", start, END[end], None) for what, start in (("question", ask), ("permission", perm)) for end in END]


@pytest.mark.parametrize("row,start,end,after", ROWS, ids=[r[0] for r in ROWS])
def test_the_act_says_it_waits_while_it_waits_and_not_after(row, start, end, after):
    w = _world()
    start(w)
    a = w.agents[S]
    assert a["state"] == "waiting" and any(x in a["act"] for x in WAIT_WORDS), (row, a["state"], a["act"])
    end(w)
    a = w.agents[S]
    assert a["state"] != "waiting" and not any(x in a["act"] for x in WAIT_WORDS), (row, a["state"], a["act"])
    if after is not None:
        assert a["act"] == after


@pytest.mark.parametrize("start", [ask, perm], ids=["question", "permission"])
def test_another_calls_end_does_not_end_the_wait(start):
    """The wait is still on when another call of the robot finishes: the act and the state keep saying so."""
    w = _world()
    other_open(w)
    start(w)
    before = dict(w.agents[S])
    _h(w, 21, hook_event_name="PostToolUse", tool_name="Read", tool_input={"file_path": "/work/act/a.txt"}, tool_use_id="r1")
    a = w.agents[S]
    assert (a["state"], a["act"]) == (before["state"], before["act"]) and a["state"] == "waiting"


def test_a_question_answered_on_the_page_keeps_waiting_until_its_post_tool_use():
    """The page's answer goes to the session through the hook; until the session's PostToolUse the call is still open."""
    w = _world()
    ask(w)
    _answer_on_page(w)
    a = w.agents[S]
    assert a["state"] == "waiting" and a["act"].startswith("質問に回答待ち")
