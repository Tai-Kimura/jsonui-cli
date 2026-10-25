"""The Codex sessions on this machine, from the Codex app-server daemon (``codex app-server daemon start``).

A terminal ``codex`` attaches itself to the daemon when one runs (measured 2026-10-25/26 on Linux and macOS, Codex
0.164.0): its threads are listed by ``thread/loaded/list``, and a client that subscribes to a thread (``thread/resume``
with ``excludeTurns``) is sent every event of it, and every approval request the terminal is sent — both show it, the
first answer wins, and the other is told ``serverRequest/resolved``. A session started without the daemon, and the VS
Code extension's (its own stdio server), are not seen: the requester left those out (10-26, as the Claude side's VS Code).

The socket: ``$CODEX_HOME/app-server-control/app-server-control.sock`` (default ``~/.codex``), a WebSocket over a Unix
socket carrying JSON-RPC 2.0 (``initialize`` then ``initialized``). Read only, with two exceptions the page asks for: an
answer to an approval request this client was sent, and a name for a thread started from the call dialog (callcmd.
name_in_prompt, once, only a thread with no name). Nothing else is written. viz never starts the daemon.

Two halves:
  * ``Translator`` (pure, tested on its own): app-server notifications -> the Claude Code hook payloads ``World.apply_hook``
    already reads (SessionStart, UserPromptSubmit, PreToolUse / PostToolUse with Bash / Edit / Write / mcp__…, Stop,
    SubagentStart / SubagentStop, SessionEnd). A child thread (``parentThreadId``) is a subagent of its root thread.
    An approval request -> what a permission card needs; the card's answer -> the response's ``decision``.
  * ``CodexLink`` (asyncio, aiohttp): finds the socket, connects, lists the loaded threads every POLL_SEC, subscribes to
    each once, feeds the translator's output to a sink, and sends an answer back when the sink resolves one. No socket:
    the source is "stopped" with no error (no banner on the page; ``jui viz doctor`` says how to start the daemon), and
    it looks again every RETRY_SEC.
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any, Callable

from .. import callcmd, i18n, quiet_fs

POLL_SEC = 3.0
RETRY_SEC = 5.0
CALL_TIMEOUT_SEC = 10.0
TEXT_MAX = 4_000
#: The approval requests a card is made for. Others (item/permissions/requestApproval, MCP elicitations) are left to
#: the terminal: this client never answers them.
APPROVALS = ("item/commandExecution/requestApproval", "item/fileChange/requestApproval")


def codex_home() -> Path:
    home = os.environ.get("CODEX_HOME", "")
    return Path(home) if os.path.isabs(home) else Path.home() / ".codex"


def socket_path() -> Path:
    return codex_home() / "app-server-control" / "app-server-control.sock"


def _s(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _text_of(content) -> str:
    if not isinstance(content, list):
        return ""
    return "\n".join(p.get("text", "") for p in content if isinstance(p, dict) and isinstance(p.get("text"), str))


class Translator:
    """app-server notifications -> hook payloads. Keeps what it must remember: each thread's root, cwd and role, and the
    items in flight (an approval names its item; a file change's paths are on the item, not on the request)."""

    def __init__(self) -> None:
        self.threads: dict[str, dict] = {}     # thread id -> {"root", "cwd", "role", "name"}
        self.items: dict[str, dict] = {}       # item id -> {"thread", "tool", "inputs": [(use id, tool, input)]}
        self.last_message: dict[str, str] = {}  # thread id -> its turn's latest agent message
        self.turns: dict[str, str] = {}         # thread id -> the turn running now (the page's 停止 interrupts it)

    # ------------------------------------------------------------ threads

    def thread_seen(self, thread: dict) -> list[dict]:
        """A loaded thread first seen (a list row or a resume response): its SessionStart, or a subagent's start."""
        tid = _s(thread.get("id"))
        if tid is None or tid in self.threads:
            if tid is not None:
                self._remember(tid, thread)
            return []
        parent = _s(thread.get("parentThreadId"))
        root = self.threads[parent]["root"] if parent in self.threads else (parent or tid)
        self.threads[tid] = {"root": root, "cwd": None, "role": None, "name": None}
        self._remember(tid, thread)
        if root == tid:
            out = {**self._base(tid), "hook_event_name": "SessionStart", "source": "codex"}
            if _s(thread.get("model")):
                out["model"] = thread["model"]
            return [out]
        return [{**self._base(tid), "hook_event_name": "SubagentStart"}]

    def _remember(self, tid: str, thread: dict) -> None:
        t = self.threads[tid]
        cwd = _s(thread.get("cwd"))
        if cwd:
            t["cwd"] = cwd
        role = _s(thread.get("agentRole")) or _s(thread.get("agentNickname"))
        if role:
            t["role"] = role
        if "name" in thread:
            t["name"] = _s(thread.get("name"))

    def title_of(self, thread: dict) -> str | None:
        """The session's name for the page: the thread's own name (/rename), else nothing (the page shows its id)."""
        return _s(thread.get("name"))

    def thread_gone(self, tid: str) -> list[dict]:
        t = self.threads.pop(tid, None)
        if t is None:
            return []
        self.last_message.pop(tid, None)
        self.turns.pop(tid, None)
        for item_id in [k for k, v in self.items.items() if v["thread"] == tid]:
            self.items.pop(item_id, None)
        if t["root"] == tid:
            base = {"session_id": tid, "cwd": t["cwd"], "cli": "codex"}
            return [{**base, "hook_event_name": "SessionEnd", "reason": "codex thread closed"}]
        base = {"session_id": t["root"], "cwd": t["cwd"], "cli": "codex", "agent_id": tid, "agent_type": t["role"]}
        return [{**base, "hook_event_name": "SubagentStop"}]

    def known(self) -> set[str]:
        return set(self.threads)

    def root_of(self, tid: str) -> str | None:
        t = self.threads.get(tid)
        return t["root"] if t else None

    def _base(self, tid: str) -> dict:
        t = self.threads[tid]
        base = {"session_id": t["root"], "cwd": t["cwd"] or self.threads.get(t["root"], {}).get("cwd"), "cli": "codex"}
        if t["root"] != tid:
            base["agent_id"] = tid
            base["agent_type"] = t["role"] or "codex-agent"
        return base

    # ------------------------------------------------------------ events

    def event(self, method: str, params: dict) -> list[dict]:
        tid = _s(params.get("threadId"))
        # thread/started is not taken here: a thread is taken when the poll subscribes to it (its events come only then)
        if method == "thread/closed" and tid:
            return self.thread_gone(tid)
        if tid is None or tid not in self.threads:
            return []
        if method == "thread/name/updated":
            self.threads[tid]["name"] = _s(params.get("threadName") or params.get("name"))
            return []
        if method == "item/started" and isinstance(params.get("item"), dict):
            return self._item_started(tid, params["item"])
        if method == "item/completed" and isinstance(params.get("item"), dict):
            return self._item_completed(tid, params["item"])
        if method == "turn/started" and isinstance(params.get("turn"), dict) and _s(params["turn"].get("id")):
            self.turns[tid] = params["turn"]["id"]
            return []
        if method == "turn/completed":
            self.turns.pop(tid, None)
            message = self.last_message.pop(tid, None)
            kind = "Stop" if self.threads[tid]["root"] == tid else "SubagentStop"
            out = {**self._base(tid), "hook_event_name": kind}
            if message:
                out["last_assistant_message"] = message[:TEXT_MAX]
            return [out]
        return []

    def _item_started(self, tid: str, item: dict) -> list[dict]:
        kind, iid = item.get("type"), _s(item.get("id"))
        if iid is None:
            return []
        if kind == "userMessage":
            text = _text_of(item.get("content"))
            if self.threads[tid]["root"] != tid or not text:
                return []
            return [{**self._base(tid), "hook_event_name": "UserPromptSubmit", "prompt": text[:TEXT_MAX]}]
        inputs = self._tool_inputs(iid, item)
        if not inputs:
            return []
        self.items[iid] = {"thread": tid, "inputs": inputs}
        return [{**self._base(tid), "hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": tin, "tool_use_id": use}
                for use, tool, tin in inputs]

    def _item_completed(self, tid: str, item: dict) -> list[dict]:
        kind, iid = item.get("type"), _s(item.get("id"))
        if kind == "agentMessage" and isinstance(item.get("text"), str) and item["text"].strip():
            self.last_message[tid] = item["text"]
            return []
        if iid is None:
            return []
        known = self.items.pop(iid, None)
        inputs = known["inputs"] if known else self._tool_inputs(iid, item)
        if not inputs:
            return []
        status = item.get("status")
        failed = status in ("failed", "declined") or (kind == "mcpToolCall" and item.get("error"))
        out = []
        for use, tool, tin in inputs:
            payload = {**self._base(tid), "hook_event_name": "PostToolUseFailure" if failed else "PostToolUse",
                       "tool_name": tool, "tool_input": tin, "tool_use_id": use}
            if kind == "commandExecution":
                payload["tool_response"] = {"stdout": (item.get("aggregatedOutput") or "")[-20_000:], "stderr": "",
                                            "interrupted": False, "exitCode": item.get("exitCode")}
            if failed:
                payload["error"] = str(status or "failed")
            out.append(payload)
        return out

    @staticmethod
    def _tool_inputs(iid: str, item: dict) -> list[tuple[str, str, dict]]:
        """One item -> the (tool_use_id, Claude tool name, tool_input) it reads as. A patch of several files is one
        Write / Edit per file (the page's file marks are per file)."""
        kind = item.get("type")
        if kind == "commandExecution" and _s(item.get("command")):
            return [(iid, "Bash", {"command": item["command"], "description": ""})]
        if kind == "fileChange" and isinstance(item.get("changes"), list):
            out = []
            for n, change in enumerate(item["changes"]):
                if not isinstance(change, dict) or not _s(change.get("path")):
                    continue
                ckind = (change.get("kind") or {}).get("type") if isinstance(change.get("kind"), dict) else change.get("kind")
                tool = "Write" if ckind == "add" else "Edit"
                out.append((iid if n == 0 else f"{iid}#{n}", tool, {"file_path": change["path"]}))
            return out
        if kind == "mcpToolCall" and _s(item.get("server")) and _s(item.get("tool")):
            args = item.get("arguments") if isinstance(item.get("arguments"), dict) else {}
            return [(iid, f"mcp__{item['server']}__{item['tool']}", args)]
        if kind == "webSearch":
            return [(iid, "WebSearch", {"query": item.get("query") or ""})]
        if kind == "collabAgentToolCall" and item.get("tool") == "spawn_agent":
            return [(iid, "Task", {"description": _s(item.get("prompt")) or "spawn_agent"})]
        return []

    # ------------------------------------------------------------ approvals

    def approval(self, method: str, params: dict) -> dict | None:
        """An approval request -> {session_id, agent_id, tool, tool_input, suggestions} for a permission card, or None
        (not one this client answers, or a thread it does not know)."""
        if method not in APPROVALS:
            return None
        tid = _s(params.get("threadId"))
        if tid is None or tid not in self.threads:
            return None
        base = self._base(tid)
        reason = _s(params.get("reason")) or ""
        if method == "item/commandExecution/requestApproval":
            command = _s(params.get("command")) or ""
            known = self.items.get(_s(params.get("itemId")) or "")
            if not command and known:
                command = known["inputs"][0][2].get("command", "")
            if not command:
                return None
            amendment = params.get("proposedExecpolicyAmendment")
            suggestions = None
            if isinstance(amendment, list) and amendment and all(isinstance(w, str) for w in amendment):
                suggestions = [{"type": "addRules", "rules": [{"toolName": "Bash", "ruleContent": " ".join(amendment)}],
                                "behavior": "allow", "destination": "codexExecPolicy", "execpolicyAmendment": amendment}]
            return {**base, "kind": "command", "tool": "Bash", "tool_input": {"command": command, "description": reason},
                    "suggestions": suggestions}
        known = self.items.get(_s(params.get("itemId")) or "")
        paths = [tin["file_path"] for _, _, tin in known["inputs"]] if known else []
        tool_input = {"file_path": paths[0]} if len(paths) == 1 else {"file_path": ", ".join(paths)} if paths else {}
        if reason:
            tool_input["description"] = reason
        if not paths:
            return None   # what would be written is not known: the terminal answers it
        return {**base, "kind": "fileChange", "tool": "Edit", "tool_input": tool_input,
                "suggestions": [{"type": "addRules", "rules": [{"toolName": "Edit"}], "behavior": "allow", "destination": "session"}]}

    @staticmethod
    def decision(kind: str, answer: dict) -> Any | None:
        """A card's answer (permissions.PermissionBook.hook_output's shape, or {} when it was settled elsewhere) -> the
        response's decision, or None to send nothing."""
        decision = (answer.get("hookSpecificOutput") or {}).get("decision") if isinstance(answer, dict) else None
        if not isinstance(decision, dict):
            return None
        if decision.get("behavior") == "deny":
            return "decline"
        if decision.get("behavior") != "allow":
            return None
        rules = decision.get("updatedPermissions")
        if rules and kind == "command":
            amendment = next((r.get("execpolicyAmendment") for r in rules if isinstance(r, dict) and r.get("execpolicyAmendment")), None)
            if amendment:
                return {"acceptWithExecpolicyAmendment": {"execpolicy_amendment": amendment}}
        if rules and kind == "fileChange":
            return "acceptForSession"
        return "accept"


class CodexLink:
    """One connection to the daemon. ``sink`` is the World's side: an object with
      apply(payloads: list[dict], titles: dict[str, str | None]) — hook payloads to apply, names of the root threads;
      approval(info: dict, rid, reply: Callable[[Any], None]) — a card to make; reply(decision) answers it;
      resolved(rid) — the request was answered elsewhere (the terminal), or withdrawn.
    on_status(status, error) — the server slice's source row ("codex")."""

    def __init__(self, sink, on_status: Callable[[str, str | None], None], path: Path | None = None,
                 poll_sec: float = POLL_SEC, retry_sec: float = RETRY_SEC) -> None:
        self.sink = sink
        self.on_status = on_status
        self.path = path
        self.poll_sec = poll_sec
        self.retry_sec = retry_sec
        self.tr = Translator()
        self._ws = None
        self._n = 0
        self._calls: dict[int, asyncio.Future] = {}
        self._said: str | None = None
        # threads being subscribed: what comes for them before the resume's answer waits here (the daemon sends a
        # thread's events from the moment it is subscribed, the answer can come after them)
        self._held: dict[str, list[tuple]] = {}
        self._named: set[str] = set()   # threads this link named from their call prompt (once each)

    def _status(self, status: str, error: str | None) -> None:
        if (status, error) != self._said:
            self._said = (status, error)
            self.on_status(status, error)

    async def run(self) -> None:
        import aiohttp

        while True:
            path = self.path or socket_path()
            if not quiet_fs.exists(path):
                # not a fault (a machine may run no Codex): the server slice says stopped, with no error banner;
                # jui viz doctor says how to start the daemon
                self._status("stopped", None)
                await asyncio.sleep(self.retry_sec)
                continue
            try:
                async with aiohttp.ClientSession(connector=aiohttp.UnixConnector(path=str(path))) as http:
                    async with http.ws_connect("http://localhost/", max_msg_size=0, autoping=True) as ws:
                        self._ws = ws
                        await self._session(ws)
            except (aiohttp.ClientError, OSError, asyncio.TimeoutError, ValueError) as err:
                self._status("degraded", i18n.tl("srv.codex.lost", error=type(err).__name__))
            finally:
                self._ws = None
                for fut in self._calls.values():
                    if not fut.done():
                        fut.cancel()
                self._calls.clear()
                self._drop_all()
            await asyncio.sleep(self.retry_sec)

    def _drop_all(self) -> None:
        """The connection is gone: what it showed ends (the threads come back on the next connection)."""
        out: list[dict] = []
        for tid in sorted(self.tr.known(), key=lambda t: self.tr.root_of(t) == t):   # subagents first
            out += self.tr.thread_gone(tid)
        if out:
            self.sink.apply(out, {})

    async def _session(self, ws) -> None:
        reader = asyncio.create_task(self._read(ws))
        try:
            await self._call("initialize", {"clientInfo": {"name": "jui_viz", "title": "jui viz", "version": "1"},
                                            "capabilities": {"experimentalApi": True}})
            await ws.send_str(json.dumps({"jsonrpc": "2.0", "method": "initialized", "params": {}}))
            self._status("running", None)
            while not reader.done():
                await self._poll()
                done, _ = await asyncio.wait({reader}, timeout=self.poll_sec)
                if done:
                    break
        finally:
            reader.cancel()

    async def _poll(self) -> None:
        got = await self._call("thread/loaded/list", {})
        ids = [t for t in (got.get("data") or []) if isinstance(t, str)] if isinstance(got, dict) else []
        out: list[dict] = []
        titles: dict[str, str | None] = {}
        for tid in ids:
            if tid in self.tr.threads:
                continue
            self._held[tid] = []
            try:
                res = await self._call("thread/resume", {"threadId": tid, "excludeTurns": True})
            finally:
                held = self._held.pop(tid, [])
            thread = res.get("thread") if isinstance(res, dict) else None
            if isinstance(thread, dict):
                out += self.tr.thread_seen(thread)
                if self.tr.root_of(tid) == tid:
                    titles[tid] = self.tr.title_of(thread)
                    self._maybe_name(tid, thread.get("preview"))
                if out or titles:
                    self.sink.apply(out, titles)
                    out, titles = [], {}
                for message in held:
                    self._dispatch(message)
        for tid in sorted(self.tr.known() - set(ids), key=lambda t: self.tr.root_of(t) == t):
            out += self.tr.thread_gone(tid)
        if out or titles:
            self.sink.apply(out, titles)

    async def _call(self, method: str, params: dict) -> Any:
        self._n += 1
        rid = self._n
        fut = asyncio.get_running_loop().create_future()
        self._calls[rid] = fut
        await self._ws.send_str(json.dumps({"jsonrpc": "2.0", "id": rid, "method": method, "params": params}))
        try:
            msg = await asyncio.wait_for(fut, CALL_TIMEOUT_SEC)
        finally:
            self._calls.pop(rid, None)
        if "error" in msg:
            return None
        return msg.get("result")

    async def _read(self, ws) -> None:
        import aiohttp

        async for frame in ws:
            if frame.type != aiohttp.WSMsgType.TEXT:
                if frame.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.ERROR):
                    break
                continue
            try:
                msg = json.loads(frame.data)
            except ValueError:
                continue
            if not isinstance(msg, dict):
                continue
            method = msg.get("method")
            if method is None and "id" in msg:   # an answer to one of our calls
                fut = self._calls.get(msg["id"])
                if fut is not None and not fut.done():
                    fut.set_result(msg)
                continue
            if not isinstance(method, str):
                continue
            params = msg.get("params") if isinstance(msg.get("params"), dict) else {}
            held = self._held.get(params.get("threadId") or "")
            if held is not None:
                held.append(msg)
                continue
            self._dispatch(msg)

    def _dispatch(self, msg: dict) -> None:
        method = msg["method"]
        params = msg.get("params") if isinstance(msg.get("params"), dict) else {}
        if "id" in msg:   # a request to this client
            self._request(msg["id"], method, params)
            return
        if method == "serverRequest/resolved":
            self.sink.resolved(params.get("requestId"))
            return
        tid = params.get("threadId") if isinstance(params.get("threadId"), str) else ""
        name_changed = method == "thread/name/updated" and self.tr.root_of(tid) == tid
        out = self.tr.event(method, params)
        titles = {tid: self.tr.threads[tid]["name"]} if name_changed and tid in self.tr.threads else {}
        for p in out:
            if p["hook_event_name"] == "UserPromptSubmit" and "agent_id" not in p:
                self._maybe_name(p["session_id"], p.get("prompt"))
        if out or titles:
            self.sink.apply(out, titles)

    def interrupt(self, tid: str) -> bool:
        """The page's 停止 for a Codex session: turn/interrupt for the turn running now (Esc in the terminal does the same;
        measured on macOS 10-26). False: not connected, or no turn runs."""
        turn = self.tr.turns.get(tid)
        if self._ws is None or self._ws.closed or turn is None:
            return False

        async def go() -> None:
            try:
                await self._call("turn/interrupt", {"threadId": tid, "turnId": turn})
            except (asyncio.TimeoutError, asyncio.CancelledError, ConnectionError, RuntimeError):
                pass

        asyncio.get_running_loop().create_task(go())
        return True

    def _maybe_name(self, tid: str, text) -> None:
        """A session started from the dialog's Codex tab names itself in its first prompt (callcmd.prompt_of): the
        thread is given that name once, when it has none (/rename in the terminal renames it as usual)."""
        t = self.tr.threads.get(tid)
        name = callcmd.name_in_prompt(text) if t is not None and not t["name"] else None
        if name is None or tid in self._named:
            return
        self._named.add(tid)
        asyncio.get_running_loop().create_task(self._set_name(tid, name))

    async def _set_name(self, tid: str, name: str) -> None:
        try:
            await self._call("thread/name/set", {"threadId": tid, "name": name})
        except (asyncio.TimeoutError, asyncio.CancelledError, ConnectionError, RuntimeError):
            return
        if tid in self.tr.threads and not self.tr.threads[tid]["name"]:
            self.tr.threads[tid]["name"] = name
            self.sink.apply([], {tid: name})

    def _request(self, rid, method: str, params: dict) -> None:
        info = self.tr.approval(method, params)
        if info is None:
            return   # not ours to answer: the terminal does

        def reply(decision) -> None:
            ws = self._ws
            if ws is None or ws.closed or decision is None:
                return
            body = json.dumps({"jsonrpc": "2.0", "id": rid, "result": {"decision": decision}})
            asyncio.get_running_loop().create_task(ws.send_str(body))

        self.sink.approval(info, rid, reply)
