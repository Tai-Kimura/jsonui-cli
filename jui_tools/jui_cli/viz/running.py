"""What runs in the background of each session on this Mac (ticket 2026-11-25-viz-show-running-tasks-of-local-sessions).

Requester 11-25: the running tasks the phone app shows, on the viz page. Only the sessions of this Mac (the
sessions folder); a session on another Mac or in the cloud is out (no public API). Read only — nothing is written to
any session.

What is read (measured 11-25 on 28 live sessions, every open task matched a live process or a live subagent):

* the session's transcript ``~/.claude/projects/<cwd>/<session id>.jsonl``:
  - a start is the tool's result record: Bash's ``backgroundTaskId``, Agent's (or Task's) and Workflow's
    ``status: async_launched`` (``agentId`` / ``taskId``), Monitor's ``taskId`` (with ``timeoutMs`` and ``persistent``);
    what it is about is the call's ``description`` (Bash's command line is never shown: it may hold a secret);
  - an end is a ``<task-notification>`` with that ``<task-id>`` and a ``<status>`` (completed / failed / killed …),
    written as a ``queue-operation`` record the moment it is queued (while the session is busy too), and again as
    the user record it becomes; a Monitor's ends with "stream ended" or "expired"; TaskStop's result names the
    ``task_id`` it stopped.
  - not an end: a Monitor's ``<event>`` (the same task id, every line it prints), and an Agent's "is waiting on its
    own background work" (status completed, but the agent goes on when that work reports).
* a subagent's own transcript (``<session>/subagents/agent-<id>.jsonl``): what that agent started in the background.
  Such a task's end is often not written there (40+ old subagents left open ones), so it is shown only while the
  agent that started it runs, and goes with it.
* ``agent-<id>.meta.json`` beside it: ``finished: true`` once the agent is done (702 of 727 had it; the 2 running
  ones did not).
* the hooks the server already gets: SubagentStop ends that agent; SessionEnd ends all of its session's; Stop's ``background_tasks`` closes what it does not list — only when the key is there, and only for
  the kinds it was seen to list (STOP_LISTED). Raw payload: not yet captured (claude 2.1.332's hook schema lists
  shell, monitor, subagent and workflow; a live viz's snapshot showed a session with only a background Bash waiting
  on its Stop's list, so shell is in it). A monitor is never closed by Stop (not yet seen in the list).
* ps (the server's background loop): a Bash or Monitor still open when no shell-snapshot shell has been under the
  session's process for SHELL_GONE_MS is closed.

Limits so nothing shows as running for ever: a Monitor not persistent closes at its timeout plus MONITOR_GRACE_MS;
an agent whose transcript has not grown for AGENT_QUIET_MS closes; anything open OPEN_CAP_MS closes; a session that
ended closes all of its own. Ended ones stay DONE_KEEP_MS, marked done, then go.

No file is read for this but once: the server already reads what every live session's transcript (and every
subagent's the hooks named) adds, every 2 s (sources/transcripts.UsageTail); each record it parses is handed over here
too. That tail starts at the file's end, so at the first sight of a session its transcript's past is read once, in a
worker (``backscan``: only whole lines holding one of MARKERS are parsed), to find what is still open. No file watcher
is added (the talk.db lesson: nothing here makes FSEvents traffic).

Known limits (what we know of):

* a task a subagent started is shown only while that subagent runs (its end is often not in its transcript);
* at the server's start every session's transcript is read once from the top (242 MB over 28 sessions took 0.4 s
  with the byte filter) to find what is still open.
"""
from __future__ import annotations

import json
import os
import re
import stat
from datetime import datetime
from pathlib import Path

KINDS = ("bash", "agent", "monitor", "workflow")
#: Stop's background_tasks ``type`` → our kind, for the kinds it was seen to list (see the module's note). Monitor is
#: not here: if the list did not carry it, every running Monitor would be closed at each Stop.
STOP_LISTED = {"shell": "bash", "bash": "bash", "subagent": "agent", "agent": "agent", "workflow": "workflow"}
END_STATUSES = frozenset({"completed", "failed", "killed", "stopped", "error", "cancelled", "canceled", "timeout"})
DONE_KEEP_MS = 60_000
SHELL_GONE_MS = 120_000
MONITOR_GRACE_MS = 5 * 60_000
AGENT_QUIET_MS = 60 * 60_000
OPEN_CAP_MS = 24 * 60 * 60_000
DESC_MAX = 120
ENDED_KEPT = 2000
LINE_MAX = 8_000_000          # a longer line is skipped, not parsed
META_MAX = 64_000
#: A line is parsed only when it holds one of these (a start, an end, or the call a start's description comes from).
MARKERS = (b'"run_in_background"', b'"name":"Agent"', b'"name":"Task"', b'"name":"Monitor"', b'"name":"Workflow"',
           b'"name":"TaskStop"', b"backgroundTaskId", b"async_launched", b"task-notification", b'"task_id"',
           b'"timeoutMs"')
START_TOOLS = ("Bash", "Agent", "Task", "Monitor", "Workflow", "TaskStop")
NOTICE = re.compile(r"<task-notification>(.*?)</task-notification>", re.S)
TAG = {k: re.compile(rf"<{k}>(.*?)</{k}>", re.S) for k in ("task-id", "status", "summary", "event")}
TASK_ID = re.compile(r"^[A-Za-z0-9_-]{1,80}$")


def _one_line(value, n: int = DESC_MAX) -> str:
    if not isinstance(value, str):
        return ""
    value = " ".join(value.split())
    return value if len(value) <= n else value[: n - 1] + "…"


def _ms(ts) -> int | None:
    if not isinstance(ts, str) or not ts:
        return None
    try:
        return int(datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp() * 1000)
    except ValueError:
        return None


class Parser:
    """Turns transcript lines into ("start", id, fields) and ("end", id, status, at) — one per file, as it keeps the
    calls it saw (a start's description is on the call, a line before its result)."""

    USES_KEPT = 400

    def __init__(self) -> None:
        self.uses: dict[str, tuple[str, dict]] = {}

    def feed(self, raw: bytes) -> list[tuple]:
        if len(raw) > LINE_MAX or not any(m in raw for m in MARKERS):
            return []
        try:
            rec = json.loads(raw)
        except ValueError:
            return []
        return self.feed_rec(rec)

    def feed_rec(self, rec) -> list[tuple]:
        """One record already parsed (the transcript tail the server reads anyway hands each one over)."""
        if not isinstance(rec, dict):
            return []
        at = _ms(rec.get("timestamp"))
        out: list[tuple] = []
        kind = rec.get("type")
        msg = rec.get("message") if isinstance(rec.get("message"), dict) else {}
        content = msg.get("content")
        if kind == "assistant" and isinstance(content, list):
            for b in content:
                if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") in START_TOOLS and isinstance(b.get("id"), str):
                    self.uses[b["id"]] = (b["name"], b.get("input") if isinstance(b.get("input"), dict) else {})
                    if len(self.uses) > self.USES_KEPT:
                        self.uses.pop(next(iter(self.uses)))
        if kind == "user" and isinstance(content, list):
            result = rec.get("toolUseResult")
            for b in content:
                if isinstance(b, dict) and b.get("type") == "tool_result" and isinstance(result, dict):
                    name, inp = self.uses.get(b.get("tool_use_id") or "", ("", {}))
                    out.extend(self._result(name, inp, result, at))
        texts = []
        if kind == "queue-operation" and isinstance(rec.get("content"), str):
            texts.append(rec["content"])
        if kind == "user":
            if isinstance(content, str):
                texts.append(content)
            elif isinstance(content, list):
                texts.extend(b.get("text") for b in content if isinstance(b, dict) and b.get("type") == "text" and isinstance(b.get("text"), str))
        for text in texts:
            if "<task-notification>" in text:
                out.extend(self._notices(text, at))
        return out

    @staticmethod
    def _result(name: str, inp: dict, r: dict, at) -> list[tuple]:
        if isinstance(r.get("backgroundTaskId"), str):   # Bash (run_in_background, or sent there while it ran)
            return [("start", r["backgroundTaskId"], {"kind": "bash", "desc": _one_line(inp.get("description")), "at": at})]
        if r.get("status") == "async_launched" and isinstance(r.get("agentId"), str):
            return [("start", r["agentId"], {"kind": "agent", "desc": _one_line(r.get("description") or inp.get("description")), "at": at})]
        if r.get("status") == "async_launched" and isinstance(r.get("taskId"), str):   # a workflow
            desc = r.get("workflowName") or r.get("summary") or inp.get("description")
            return [("start", r["taskId"], {"kind": "workflow", "desc": _one_line(desc), "at": at, "runId": r.get("runId")})]
        if (name == "Monitor" or "timeoutMs" in r and "persistent" in r) and isinstance(r.get("taskId"), str):
            timeout = r.get("timeoutMs")
            return [("start", r["taskId"], {"kind": "monitor", "desc": _one_line(inp.get("description")), "at": at,
                                            "timeoutMs": timeout if isinstance(timeout, int) and not isinstance(timeout, bool) else None,
                                            "persistent": r.get("persistent") is True})]
        if name == "TaskStop" and isinstance(r.get("task_id"), str):
            return [("end", r["task_id"], "stopped", at)]
        return []

    @staticmethod
    def _notices(text: str, at) -> list[tuple]:
        out = []
        for m in NOTICE.finditer(text):
            body = m.group(1)
            tags = {k: (rx.search(body).group(1).strip() if rx.search(body) else "") for k, rx in TAG.items()}
            tid, status, summary = tags["task-id"], tags["status"], tags["summary"]
            if not tid:
                continue
            if "waiting on its own background work" in summary:
                out.append(("waiting", tid, at))   # an agent stopped with its own work still running: not over
                continue
            if status in END_STATUSES or "stream ended" in summary or tags["event"].startswith("[Monitor expired"):
                out.append(("end", tid, status or "ended", at))
        return out


def mtime_ms(path: Path) -> int | None:
    try:
        st = os.stat(path, follow_symlinks=False)
    except OSError:
        return None
    return int(st.st_mtime * 1000) if stat.S_ISREG(st.st_mode) else None


def agent_finished(meta: Path) -> bool:
    """``agent-<id>.meta.json`` says ``finished: true`` (read only when small and regular)."""
    try:
        fd = os.open(meta, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        return False
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_size > META_MAX:
            return False
        raw = os.read(fd, META_MAX)
    except OSError:
        return False
    finally:
        os.close(fd)
    try:
        data = json.loads(raw)
    except ValueError:
        return False
    return isinstance(data, dict) and data.get("finished") is True


class Running:
    """The book: per session, the tasks it runs in the background. Keys are (session id, task id)."""

    def __init__(self) -> None:
        self.tasks: dict[tuple[str, str], dict] = {}
        self.ended_ids: dict[str, set[str]] = {}   # session -> task ids whose end the tail saw (for the backscan)
        self.shell_seen: dict[str, int] = {}   # session -> when a shell was last seen under it (or first checked)

    # ------------------------------------------------------------------ what is open

    def open_of(self, sid: str) -> list[dict]:
        return [t for (s, _), t in self.tasks.items() if s == sid and t["state"] == "running"]

    def has_open_shell(self, sid: str) -> bool:
        return any(t["kind"] in ("bash", "monitor") for t in self.open_of(sid))

    def shell_sessions(self) -> set[str]:
        return {s for (s, _), t in self.tasks.items() if t["state"] == "running" and t["kind"] in ("bash", "monitor")}

    def slice_of(self, sid: str) -> list[dict]:
        """What the session's row shows: running first (oldest first), then the ones that just ended."""
        rows = [dict(t) for (s, _), t in self.tasks.items() if s == sid and (t["state"] == "running" or t.get("parent") is None)]
        rows = [{k: v for k, v in r.items() if k in ("id", "kind", "desc", "startedAt", "state", "endedAt", "status", "parent", "waiting")} for r in rows]
        return sorted(rows, key=lambda r: (r["state"] != "running", r.get("startedAt") or 0, r["id"]))

    # ------------------------------------------------------------------ changes (each returns the sessions changed)

    def _start(self, sid: str, tid: str, f: dict, parent: str | None, at: int) -> bool:
        if not TASK_ID.match(tid):
            return False
        key = (sid, tid)
        old = self.tasks.get(key)
        if old is not None:
            return False   # read twice (a back-scan and a tail): the first stays
        self.tasks[key] = {"id": tid, "kind": f["kind"], "desc": f.get("desc") or "", "startedAt": f.get("at") or at,
                           "state": "running", "parent": parent, "timeoutMs": f.get("timeoutMs"),
                           "persistent": f.get("persistent", False), "runId": f.get("runId")}
        return True

    def _end(self, sid: str, tid: str, status: str, at: int) -> bool:
        t = self.tasks.get((sid, tid))
        if t is None or t["state"] != "running":
            return False
        t.update(state="done", status=status, endedAt=at)
        t.pop("waiting", None)
        for (s, cid), c in list(self.tasks.items()):   # what this agent started goes with it
            if s == sid and c.get("parent") == tid:
                del self.tasks[(s, cid)]
        return True

    def apply_records(self, sid: str, records: list[tuple], at: int, parent: str | None = None) -> bool:
        changed = False
        for rec in records:
            if rec[0] == "start":
                changed |= self._start(sid, rec[1], rec[2], parent, at)
            elif rec[0] == "end":
                changed |= self._end(sid, rec[1], rec[2], rec[3] or at)
            elif rec[0] == "waiting":
                t = self.tasks.get((sid, rec[1]))
                if t is not None and t["state"] == "running" and not t.get("waiting"):
                    t["waiting"] = True
                    changed = True
        return changed

    def stop_listed(self, sid: str, listed, at: int) -> bool:
        """Stop's ``background_tasks``: None (no key) closes nothing. A list closes the open tasks of the kinds it was
        seen to carry (STOP_LISTED) that it does not name. A list naming ids of which none is open here says the ids
        are not ours: nothing is closed then either."""
        if not isinstance(listed, list):
            return False
        ids = {str(b.get("id")) for b in listed if isinstance(b, dict) and b.get("id") is not None}
        mine = [t for t in self.open_of(sid) if t.get("parent") is None]
        if ids and not any(t["id"] in ids for t in mine):
            return False
        kinds = set(STOP_LISTED.values())
        changed = False
        for t in mine:
            if t["kind"] in kinds and t["id"] not in ids:
                changed |= self._end(sid, t["id"], "ended", at)
        return changed

    def agent_stopped(self, sid: str, aid: str, at: int) -> bool:
        return self._end(sid, aid, "completed", at)

    def session_ended(self, sid: str, at: int) -> bool:
        changed = False
        for t in self.open_of(sid):
            changed |= self._end(sid, t["id"], "ended", at)
        return changed

    def shells(self, sid: str, count: int | None, at: int) -> bool:
        """ps: ``count`` shell-snapshot shells under the session's process (None: the process is gone)."""
        if count:
            self.shell_seen[sid] = at
            return False
        since = self.shell_seen.setdefault(sid, at)
        if count is None or at - since >= SHELL_GONE_MS:
            changed = False
            for t in self.open_of(sid):
                if t["kind"] in ("bash", "monitor") and (count is None or at - t["startedAt"] >= SHELL_GONE_MS):
                    changed |= self._end(sid, t["id"], "gone", at)
            return changed
        return False

    def caps(self, at: int, agent_moved=None) -> set[str]:
        """The limits (module note); ``agent_moved(sid, aid)`` -> the agent transcript's mtime or None. Also drops
        the ended ones past DONE_KEEP_MS. Returns the sessions changed."""
        changed: set[str] = set()
        for (sid, tid), t in list(self.tasks.items()):
            if t["state"] != "running":
                if at - (t.get("endedAt") or at) >= DONE_KEEP_MS:
                    del self.tasks[(sid, tid)]
                    changed.add(sid)
                continue
            age = at - (t["startedAt"] or at)
            end = None
            if age >= OPEN_CAP_MS:
                end = "cap"
            elif t["kind"] == "monitor" and not t.get("persistent") and t.get("timeoutMs") and age >= t["timeoutMs"] + MONITOR_GRACE_MS:
                end = "timeout"
            elif t["kind"] == "agent" and agent_moved is not None and age >= AGENT_QUIET_MS:
                moved = agent_moved(sid, tid)
                if moved is None or at - moved >= AGENT_QUIET_MS:
                    end = "quiet"
            if end and self._end(sid, tid, end, at):
                changed.add(sid)
        return changed

    # ------------------------------------------------------------------ the transcripts

    def tail(self, sid: str, records: list[tuple], at: int, parent: str | None = None) -> bool:
        """What the server's transcript tail (sources/transcripts.UsageTail) found in what a file added."""
        ended = self.ended_ids.setdefault(sid, set())
        for rec in records:
            if rec[0] == "end":
                ended.add(rec[1])
        if len(ended) > ENDED_KEPT:
            self.ended_ids[sid] = set(list(ended)[-ENDED_KEPT // 2:])
        return self.apply_records(sid, records, at, parent)

    def backscan_done(self, sid: str, records: list[tuple], at: int, parent: str | None = None) -> bool:
        """What was in the file before the tail's first read (backscan, in a worker): a start whose end the tail has
        seen since is not opened."""
        ended = self.ended_ids.get(sid, set()) | {r[1] for r in records if r[0] == "end"}   # over before: not shown
        return self.apply_records(sid, [r for r in records if r[0] != "end" and not (r[0] == "start" and r[1] in ended)], at, parent)

    def forget(self, sid: str) -> None:
        for key in [k for k in self.tasks if k[0] == sid]:
            del self.tasks[key]
        self.ended_ids.pop(sid, None)
        self.shell_seen.pop(sid, None)


def backscan(path: Path, end: int) -> list[tuple]:
    """In a worker: the records of ``path``'s first ``end`` bytes (where the tail started), only the lines holding one
    of MARKERS parsed. Nothing is read through a symlink or from what is not a regular file."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        return []
    out: list[tuple] = []
    parser = Parser()
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            return []
        with os.fdopen(fd, "rb", closefd=True) as fh:
            fd = -1
            done = 0
            for raw in fh:
                done += len(raw)
                if done > end:
                    break
                out.extend(parser.feed(raw))
    except OSError:
        return out
    finally:
        if fd >= 0:
            os.close(fd)
    return out
