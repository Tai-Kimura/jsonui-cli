"""Task cards made from what a session does (sources/tasks.py turns, ingest.py): a prompt starts a card, Stop ends it.

The task tools are off by default on newer models and ~/.claude/tasks/ stays empty, so the board was always empty
(requester, 10-18, plan 2). These arms read the tasks slice after a sequence of hook payloads.
"""
from __future__ import annotations

from jui_cli.viz.ingest import World
from jui_cli.viz.sources.tasks import TURNS_DONE_KEPT, TaskBook
from jui_cli.viz.state import VizState


def _world() -> tuple[World, VizState]:
    state = VizState()
    return World(state, tool_input_max=50), state


def _hook(kind, sid="s-aaaa", **fields):
    return {"hook_event_name": kind, "session_id": sid, "cwd": "/work/shop-app", **fields}


def _turns(state, sid="s-aaaa"):
    return [t for t in state.slices["tasks"] if t["sessionId"] == sid and t.get("source") == "turn"]


def _run(world, state, *hooks):
    for i, h in enumerate(hooks):
        world.apply_hook(h, 1000 + i * 100)
    world.publish()
    return _turns(state)


def test_a_prompt_starts_a_working_card_titled_by_its_first_line_and_stop_moves_it_to_done():
    world, state = _world()
    [card] = _run(world, state, _hook("UserPromptSubmit", prompt="ログイン画面を直して\n細かい説明はこちら"))
    assert (card["status"], card["subject"], card["owner"]) == ("in_progress", "ログイン画面を直して", "s-aaaa")
    [card] = _run(world, state, _hook("Stop"))
    assert card["status"] == "completed" and not card.get("failed")
    assert card["completedAt"] >= card["createdAt"]


def test_stop_with_background_tasks_keeps_the_card_working():
    world, state = _world()
    _run(world, state, _hook("UserPromptSubmit", prompt="テストを流して"))
    [card] = _run(world, state, _hook("Stop", background_tasks=[{"id": "b1"}]))
    assert card["status"] == "in_progress" and card.get("background") is True
    [card] = _run(world, state, _hook("Stop"))   # the background work finished: the next Stop has none
    assert card["status"] == "completed" and "background" not in card


def test_waiting_for_a_permission_marks_the_card_waiting_until_the_tool_runs():
    world, state = _world()
    _run(world, state, _hook("UserPromptSubmit", prompt="ファイルを書いて"),
         _hook("PreToolUse", tool_name="Write", tool_use_id="w1", tool_input={"file_path": "/work/shop-app/a.txt"}))
    [card] = _run(world, state, _hook("PermissionRequest", tool_name="Write", tool_input={"file_path": "/work/shop-app/a.txt"}))
    assert card["status"] == "in_progress" and card["waiting"] is True
    [card] = _run(world, state, _hook("PostToolUse", tool_name="Write", tool_use_id="w1", tool_input={"file_path": "/work/shop-app/a.txt"}))
    assert card["waiting"] is False and card["status"] == "in_progress"


def test_stop_failure_ends_the_card_marked_failed():
    world, state = _world()
    _run(world, state, _hook("UserPromptSubmit", prompt="ビルドして"))
    [card] = _run(world, state, _hook("StopFailure"))
    assert card["status"] == "completed" and card["failed"] is True


def test_a_wrapped_prompt_is_titled_by_what_is_inside_the_wrapper():
    prompt = ('<cross-session-message from="uds:/tmp/cc-socks/2991.sock" from-name="lane-4d" from-mode="prompting">\n'
              "作業の依頼です。画面を直してください\n## 要望\n…")
    world, state = _world()
    [card] = _run(world, state, _hook("UserPromptSubmit", prompt=prompt))
    assert card["subject"] == "作業の依頼です。画面を直してください"
    # the wrapper and its text on one line
    assert TaskBook.turn_title('<cross-session-message from="x">依頼の一行目\n続き</cross-session-message>') == "依頼の一行目"


def test_the_title_comes_from_the_kept_head_of_the_prompt_only():
    long_line = "あ" * 500
    assert len(TaskBook.turn_title(long_line)) <= 200
    # a first line past the kept head is never read
    assert TaskBook.turn_title("\n" * 199 + "x" * 10 + "\n本当の一行目") == "x"


def test_only_the_last_done_turns_of_a_session_stay():
    world, state = _world()
    hooks = []
    for i in range(TURNS_DONE_KEPT + 3):
        hooks += [_hook("UserPromptSubmit", prompt=f"指示 {i}"), _hook("Stop")]
    cards = _run(world, state, *hooks)
    assert [c["subject"] for c in cards] == [f"指示 {i}" for i in range(3, TURNS_DONE_KEPT + 3)]
    assert all(c["status"] == "completed" for c in cards)


def test_a_new_prompt_ends_the_turn_left_open_and_another_session_keeps_its_own_card():
    world, state = _world()
    _run(world, state, _hook("UserPromptSubmit", prompt="一つ目"),
         _hook("UserPromptSubmit", sid="s-bbbb", prompt="別のセッション"),
         _hook("UserPromptSubmit", prompt="二つ目"))
    mine = _turns(state)
    assert [(c["subject"], c["status"]) for c in mine] == [("一つ目", "completed"), ("二つ目", "in_progress")]
    assert [(c["subject"], c["status"]) for c in _turns(state, "s-bbbb")] == [("別のセッション", "in_progress")]


def test_task_tool_cards_keep_coming_and_say_where_they_came_from():
    world, state = _world()
    _run(world, state, _hook("UserPromptSubmit", prompt="計画して"),
         _hook("TaskCreated", task_id="1", task_subject="spec を書く"),
         _hook("PreToolUse", tool_name="TodoWrite", tool_use_id="t1",
               tool_input={"todos": [{"content": "画面を作る", "status": "pending"}]}))
    sources = sorted((t["subject"], t["source"]) for t in state.slices["tasks"])
    assert sources == [("spec を書く", "hook"), ("画面を作る", "todo"), ("計画して", "turn")]
