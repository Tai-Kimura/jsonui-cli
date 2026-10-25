"""The Codex sessions (sources/codex_app_server.py): the daemon's notifications read as hook payloads, the approval
cards answered through the daemon, and one connection to a fake daemon on a Unix socket. The shapes are the ones the
real daemon sent (Codex 0.164.0, macOS and Linux, 2026-10-25/26)."""
from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

from aiohttp import web

from jui_cli.viz.ingest import World
from jui_cli.viz.sources.codex_app_server import CodexLink, Translator, socket_path
from jui_cli.viz.state import VizState

ROOT = "01a1750c-564e-7711-ac44-2de86897a988"
CHILD = "01a17600-0000-7000-8000-000000000001"


def _thread(tid=ROOT, **extra):
    return {"id": tid, "cwd": "/work/app", "model": "gpt-6.1-sol", "status": {"type": "idle"}, "name": None, **extra}


def _cmd_item(iid="exec-1", status="inProgress", **extra):
    return {"type": "commandExecution", "id": iid, "command": "/bin/zsh -lc 'touch hello.txt'", "cwd": "/work/app",
            "status": status, **extra}


def test_a_thread_is_a_session_and_its_items_are_the_tools_claude_code_would_report():
    tr = Translator()
    [start] = tr.thread_seen(_thread())
    assert start == {"session_id": ROOT, "cwd": "/work/app", "cli": "codex", "hook_event_name": "SessionStart",
                     "source": "codex", "model": "gpt-6.1-sol"}
    assert tr.thread_seen(_thread()) == []   # once
    [prompt] = tr.event("item/started", {"threadId": ROOT, "item": {"type": "userMessage", "id": "u1",
                                                                     "content": [{"type": "text", "text": "hello"}]}})
    assert prompt["hook_event_name"] == "UserPromptSubmit" and prompt["prompt"] == "hello"
    [pre] = tr.event("item/started", {"threadId": ROOT, "item": _cmd_item()})
    assert (pre["hook_event_name"], pre["tool_name"], pre["tool_use_id"]) == ("PreToolUse", "Bash", "exec-1")
    assert pre["tool_input"]["command"] == "/bin/zsh -lc 'touch hello.txt'"
    [post] = tr.event("item/completed", {"threadId": ROOT, "item": _cmd_item(status="completed", aggregatedOutput="ok\n", exitCode=0)})
    assert post["hook_event_name"] == "PostToolUse" and post["tool_response"]["stdout"] == "ok\n"
    assert tr.event("item/completed", {"threadId": ROOT, "item": {"type": "agentMessage", "id": "m1", "text": "届きました。"}}) == []
    [stop] = tr.event("turn/completed", {"threadId": ROOT, "turn": {"id": "t1"}})
    assert stop["hook_event_name"] == "Stop" and stop["last_assistant_message"] == "届きました。"


def test_a_patch_is_one_write_or_edit_per_file_and_a_declined_command_fails():
    tr = Translator()
    tr.thread_seen(_thread())
    item = {"type": "fileChange", "id": "p1", "status": "inProgress",
            "changes": [{"path": "/work/app/a.txt", "kind": {"type": "add"}, "diff": ""},
                        {"path": "/work/app/b.txt", "kind": {"type": "update", "move_path": None}, "diff": ""}]}
    pre = tr.event("item/started", {"threadId": ROOT, "item": item})
    assert [(p["tool_name"], p["tool_use_id"], p["tool_input"]["file_path"]) for p in pre] == [
        ("Write", "p1", "/work/app/a.txt"), ("Edit", "p1#1", "/work/app/b.txt")]
    tr.event("item/started", {"threadId": ROOT, "item": _cmd_item("e2")})
    [failed] = tr.event("item/completed", {"threadId": ROOT, "item": _cmd_item("e2", status="declined")})
    assert failed["hook_event_name"] == "PostToolUseFailure"


def test_a_child_thread_is_a_subagent_of_its_root():
    tr = Translator()
    tr.thread_seen(_thread())
    [start] = tr.thread_seen(_thread(CHILD, parentThreadId=ROOT, agentRole="explorer"))
    assert start["hook_event_name"] == "SubagentStart" and start["session_id"] == ROOT
    assert (start["agent_id"], start["agent_type"]) == (CHILD, "explorer")
    [stop] = tr.event("turn/completed", {"threadId": CHILD, "turn": {"id": "t9"}})
    assert stop["hook_event_name"] == "SubagentStop" and stop["agent_id"] == CHILD
    assert [p["hook_event_name"] for p in tr.thread_gone(CHILD) + tr.thread_gone(ROOT)] == ["SubagentStop", "SessionEnd"]


def test_an_approval_request_becomes_a_card_and_its_answer_the_decision():
    tr = Translator()
    tr.thread_seen(_thread())
    tr.event("item/started", {"threadId": ROOT, "item": _cmd_item()})
    info = tr.approval("item/commandExecution/requestApproval", {
        "kind": "command", "threadId": ROOT, "turnId": "t1", "itemId": "exec-1", "environmentId": "local",
        "reason": "読み取り専用の制限を越えて、hello.txt を作成または更新することを許可しますか？",
        "command": "/bin/zsh -lc 'touch hello.txt'", "cwd": "/work/app",
        "proposedExecpolicyAmendment": ["touch", "hello.txt"], "availableDecisions": ["accept", "decline", "cancel"]})
    assert info["tool"] == "Bash" and info["tool_input"]["command"] == "/bin/zsh -lc 'touch hello.txt'"
    assert info["suggestions"][0]["rules"] == [{"toolName": "Bash", "ruleContent": "touch hello.txt"}]
    allow = {"hookSpecificOutput": {"decision": {"behavior": "allow"}}}
    always = {"hookSpecificOutput": {"decision": {"behavior": "allow", "updatedPermissions": info["suggestions"]}}}
    deny = {"hookSpecificOutput": {"decision": {"behavior": "deny", "message": "no"}}}
    assert Translator.decision("command", allow) == "accept"
    assert Translator.decision("command", always) == {"acceptWithExecpolicyAmendment": {"execpolicy_amendment": ["touch", "hello.txt"]}}
    assert Translator.decision("command", deny) == "decline"
    assert Translator.decision("command", {}) is None   # settled elsewhere: nothing is sent
    assert tr.approval("item/permissions/requestApproval", {"threadId": ROOT}) is None   # left to the terminal
    assert tr.approval("item/commandExecution/requestApproval", {"threadId": "unknown", "command": "x"}) is None


def test_the_world_shows_a_codex_session_and_its_card_waits_for_the_page():
    state = VizState()
    world = World(state)
    tr = Translator()
    world.apply_codex(tr.thread_seen(_thread(name="triage")), {ROOT: "triage"}, 1)
    world.apply_codex(tr.event("item/started", {"threadId": ROOT, "item": _cmd_item()}), {}, 2)
    world.publish()
    [session] = state.slices["sessions"]
    assert session["cli"] == "codex" and session["title"] == "triage" and session["status"] == "busy"
    [robot] = state.slices["agents"]
    assert robot["cli"] == "codex" and robot["state"] == "command"
    info = tr.approval("item/commandExecution/requestApproval", {"threadId": ROOT, "itemId": "exec-1",
                                                                 "command": "/bin/zsh -lc 'touch hello.txt'", "reason": "ok?"})
    card = world.codex_approval(info, 0, 3)
    future = asyncio.new_event_loop().create_future()
    world.hook_waiting(card, future)
    world.publish()
    [perm] = state.slices["perms"]
    assert perm["cli"] == "codex" and perm["status"] == "pending" and perm["can"]["allowDeny"] is True
    assert state.slices["agents"][0]["state"] == "waiting"
    assert world.decide(perm["id"], "allow", 4) is None
    assert Translator.decision("command", future.result()) == "accept"
    world.apply_codex(tr.event("item/completed", {"threadId": ROOT, "item": _cmd_item(status="completed")}), {}, 5)
    world.publish()
    assert state.slices["perms"][0]["status"] == "allow"


def test_a_card_the_terminal_answered_first_is_settled_by_resolved():
    state = VizState()
    world = World(state)
    tr = Translator()
    world.apply_codex(tr.thread_seen(_thread()), {}, 1)
    world.apply_codex(tr.event("item/started", {"threadId": ROOT, "item": _cmd_item()}), {}, 2)
    info = tr.approval("item/commandExecution/requestApproval", {"threadId": ROOT, "itemId": "exec-1", "command": "x"})
    card = world.codex_approval(info, 7, 3)
    future = asyncio.new_event_loop().create_future()
    world.hook_waiting(card, future)
    world.codex_resolved(7, 4)
    world.publish()
    assert state.slices["perms"][0]["status"] == "answered_in_terminal"
    assert future.result() == {}   # nothing goes back to the daemon
    assert state.slices["agents"][0]["state"] != "waiting"


def test_a_claude_code_session_carries_no_cli_field():
    state = VizState()
    world = World(state)
    world.apply_hook({"hook_event_name": "SessionStart", "session_id": "c1", "cwd": "/work/app"}, 1)
    world.publish()
    assert "cli" not in state.slices["sessions"][0] and "cli" not in state.slices["agents"][0]


def test_the_socket_is_under_codex_home(monkeypatch, tmp_path):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    assert socket_path() == tmp_path / "app-server-control" / "app-server-control.sock"
    monkeypatch.setenv("CODEX_HOME", "relative/dir")
    assert socket_path() == Path.home() / ".codex" / "app-server-control" / "app-server-control.sock"


class FakeDaemon:
    """A daemon with one loaded thread: it answers the calls the link makes, then sends a command, an approval
    request, and records the answer."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.answer = asyncio.get_running_loop().create_future()

    async def handler(self, request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        async for msg in ws:
            m = json.loads(msg.data)
            if "method" not in m:   # the answer to our request
                if not self.answer.done():
                    self.answer.set_result(m)
                continue
            self.calls.append(m["method"])
            if "id" not in m:
                continue
            result = {}
            if m["method"] == "thread/loaded/list":
                result = {"data": [ROOT]}
            elif m["method"] == "thread/resume":
                result = {"thread": _thread(name="triage")}
            await ws.send_str(json.dumps({"id": m["id"], "result": result}))
            if m["method"] == "thread/resume":
                await ws.send_str(json.dumps({"method": "item/started", "params": {"threadId": ROOT, "item": _cmd_item()}}))
                await ws.send_str(json.dumps({"id": 0, "method": "item/commandExecution/requestApproval", "params": {
                    "threadId": ROOT, "itemId": "exec-1", "command": "/bin/zsh -lc 'touch hello.txt'", "reason": "ok?"}}))
        return ws


class Sink:
    def __init__(self) -> None:
        self.payloads: list[dict] = []
        self.titles: dict = {}
        self.cards: list = []

    def apply(self, payloads, titles):
        self.payloads += payloads
        self.titles.update(titles)

    def approval(self, info, rid, reply):
        self.cards.append((info, rid))
        reply("accept")

    def resolved(self, rid):
        pass


def test_the_link_subscribes_to_each_loaded_thread_and_answers_through_the_socket():
    async def go():
        daemon = FakeDaemon()
        app = web.Application()
        app.router.add_get("/", daemon.handler)
        runner = web.AppRunner(app)
        await runner.setup()
        with tempfile.TemporaryDirectory(dir="/tmp") as d:   # a short path: a Unix socket's name has a length limit
            sock = Path(d) / "s.sock"
            site = web.UnixSite(runner, str(sock))
            await site.start()
            sink, statuses = Sink(), []
            link = CodexLink(sink, lambda st, err: statuses.append(st), path=sock, poll_sec=0.05, retry_sec=0.05)
            task = asyncio.create_task(link.run())
            try:
                answer = await asyncio.wait_for(daemon.answer, 5)
            finally:
                task.cancel()
                await runner.cleanup()
        return daemon, sink, statuses, answer

    daemon, sink, statuses, answer = asyncio.run(go())
    assert daemon.calls[:3] == ["initialize", "initialized", "thread/loaded/list"]
    assert daemon.calls.count("thread/resume") == 1   # one subscription per thread
    assert [p["hook_event_name"] for p in sink.payloads][:2] == ["SessionStart", "PreToolUse"]
    assert sink.titles == {ROOT: "triage"} and statuses[0] == "running"
    assert sink.cards[0][1] == 0 and answer == {"jsonrpc": "2.0", "id": 0, "result": {"decision": "accept"}}


def test_no_socket_says_so_once_and_keeps_looking(tmp_path):
    async def go():
        statuses = []
        link = CodexLink(Sink(), lambda st, err: statuses.append((st, err)), path=tmp_path / "none.sock", retry_sec=0.01)
        task = asyncio.create_task(link.run())
        await asyncio.sleep(0.08)
        task.cancel()
        return statuses

    statuses = asyncio.run(go())
    assert statuses == [("stopped", None)]   # once, and no error: no banner on a machine that runs no Codex


def test_a_codex_robot_is_labelled_from_its_ids_random_tail():
    state = VizState()
    world = World(state)
    tr = Translator()
    world.apply_codex(tr.thread_seen(_thread()), {}, 1)
    world.apply_codex(tr.thread_seen(_thread("01a1750c-564e-7711-ac44-2de868970088")), {}, 2)
    world.publish()
    assert [s["label"] for s in state.slices["sessions"]] == ["88", "088"]


def test_the_codex_tab_makes_a_codex_line_and_its_prompt_names_the_thread():
    from jui_cli.viz import callcmd

    line = callcmd.codex_command("/work/app", "review", "PRs")
    assert line.startswith("cd /work/app && codex app-server daemon start >/dev/null && codex ")
    prompt = callcmd.prompt_of("review", "PRs")
    assert callcmd.name_in_prompt(prompt) == "review"
    assert callcmd.name_in_prompt("hello\\nセッション名: x") is None and callcmd.name_in_prompt(None) is None


def test_the_stop_button_interrupts_a_codex_turn_at_once():
    state = VizState()
    world = World(state)
    tr = Translator()
    world.apply_codex(tr.thread_seen(_thread()), {}, 1)
    assert tr.event("turn/started", {"threadId": ROOT, "turn": {"id": "t1"}}) == [] and tr.turns == {ROOT: "t1"}
    world.apply_codex(tr.event("item/started", {"threadId": ROOT, "item": _cmd_item()}), {}, 2)
    asked = []
    world.codex_stop = lambda sid: asked.append(sid) or True
    assert world.request_stop(ROOT, 3) is None and asked == [ROOT]
    assert world.request_stop(ROOT, 3, cancel=True)[0] == 409
    world.codex_stop = lambda sid: False   # no turn, or no daemon
    assert world.request_stop(ROOT, 4)[0] == 409
    tr.event("turn/completed", {"threadId": ROOT, "turn": {"id": "t1"}})
    assert tr.turns == {}
