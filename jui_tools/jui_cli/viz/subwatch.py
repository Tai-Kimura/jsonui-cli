"""A subagent that stopped moving (ticket 2026-11-18-viz-notify-main-when-a-subagent-quiets).

Requester 11-18: 「サブエージェントに作業依頼した後サブエージェントが止まってるのにメインエージェントが気づかないことがよくある。
これ自動で検知してメインに通知するような仕組み viz に入れれないかな？ ストレージやメモリや CPU 食いすぎない設計で」.

Watched: a subagent the hooks named (agent_id) and that has not stopped. Dropped when it stops (SubagentStop), when its
session's main turn ends with nothing in the background, when the session ends. One entry per watched subagent, a few
hundred bytes; nothing is written anywhere.

When it last moved: its last hook, or its transcript's mtime (agent_transcript_path), whichever is later. The file is
only stat'ed — never read — at most once every CHECK_EVERY_MS (a fifth of the limit when that is shorter), and only
while something is watched.

Two kinds of stall, each told once per stretch of quiet (a hook or a grown transcript ends the stretch), at most
NOTICES_MAX times per subagent:
  * quiet — it has not moved for ``quiet_min`` minutes (default 20: measured over 14 days of this machine's transcripts,
    2294 subagents, a model call took up to 17 min 13 s and still answered, a tool call at most 10 min; 20 min had no
    false notice, 15 min 7, 10 min 22). A call still open whose own timeout is longer than that is given its timeout
    plus TIMEOUT_GRACE_MS.
  * wait — a permission prompt or a question of the subagent has not been answered for ``perm_min`` minutes (default 5);
    only a person can answer it.
"""
from __future__ import annotations

import glob
import os

QUIET_MIN = 20.0
PERM_MIN = 5.0
CHECK_EVERY_MS = 60_000
TIMEOUT_GRACE_MS = 5 * 60_000
NOTICES_MAX = 3
HEAD_MAX = 80
#: tool_input keys whose value says what a call is about, in this order (the notice's "last tool")
HEAD_KEYS = ("command", "file_path", "path", "pattern", "url", "query", "description", "prompt")


def head_of(tool_input) -> str:
    if not isinstance(tool_input, dict):
        return ""
    for key in HEAD_KEYS:
        value = tool_input.get(key)
        if isinstance(value, str) and value.strip():
            one = " ".join(value.split())
            return one if len(one) <= HEAD_MAX else one[: HEAD_MAX - 1] + "…"
    return ""


def timeout_ms_of(tool_input) -> int:
    """A call's own timeout (Bash's ``timeout``, in ms), or 0."""
    value = tool_input.get("timeout") if isinstance(tool_input, dict) else None
    return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0 else 0


class SubagentWatch:
    def __init__(self, quiet_min: float = QUIET_MIN, perm_min: float = PERM_MIN, stat=os.stat) -> None:
        self.quiet_ms = int(quiet_min * 60_000)
        self.perm_ms = int(perm_min * 60_000)
        self.stat = stat
        self.watched: dict[str, dict] = {}
        self.next_check = 0

    def configure(self, quiet_min: float, perm_min: float) -> None:
        """0 (or less) turns that kind off."""
        self.quiet_ms = int(max(0.0, float(quiet_min)) * 60_000)
        self.perm_ms = int(max(0.0, float(perm_min)) * 60_000)

    # ------------------------------------------------------------ hooks

    def hook(self, aid: str, sid: str, at: int, kind: str, *, tool: str | None = None, tool_input=None,
             use_id: str | None = None, path: str | None = None, agent_type: str | None = None,
             question: bool = False, main_transcript: str | None = None, foreground: bool | None = None,
             description: str | None = None) -> bool:
        """One hook of a subagent that goes on. True when this ended a stretch that was told (the page's mark goes)."""
        w = self.watched.get(aid)
        if w is None:
            if self.quiet_ms <= 0 and self.perm_ms <= 0:
                return False
            w = self.watched[aid] = {"sid": sid, "lastAt": at, "size": None, "mtimeMs": 0, "path": None, "type": None, "base": None,
                                     "foreground": False, "description": "",
                                     "calls": {}, "waitSince": 0, "waitTool": "", "waitHead": "", "tool": "", "head": "",
                                     "told": None, "notices": 0}
        if path:
            w["path"] = path
        elif not w["base"] and main_transcript and main_transcript.endswith(".jsonl"):
            # A subagent's own hooks carry the main's transcript_path, never its own (only SubagentStop has
            # agent_transcript_path; claude 2.1.327, measured 11-18): it is <main>/subagents/agent-<id>.jsonl, a
            # Workflow's under <main>/subagents/workflows/<run>/ — looked for at the check until found.
            w["base"] = main_transcript[: -len(".jsonl")]
        if foreground is not None:
            w["foreground"] = foreground
        if description:
            w["description"] = description
        if agent_type:
            w["type"] = agent_type
        w["lastAt"] = max(w["lastAt"], at)
        if kind == "PreToolUse" and tool:
            w["tool"], w["head"] = tool, head_of(tool_input)
            if use_id:
                w["calls"][use_id] = timeout_ms_of(tool_input)
            if question:   # a question waits on a person from its PreToolUse (ingest: the robot is 質問に回答待ち)
                w["waitSince"], w["waitTool"], w["waitHead"] = at, tool, w["head"]
        elif kind in ("PostToolUse", "PostToolUseFailure", "PermissionDenied"):
            if use_id:
                w["calls"].pop(use_id, None)
            w["waitSince"] = 0
        elif kind == "PermissionRequest":
            w["waitSince"], w["waitTool"], w["waitHead"] = at, tool or "", head_of(tool_input)
        elif kind != "Notification":   # a permission's own Notification says it still waits
            w["waitSince"] = 0
        return self._moved(w)

    def drop(self, aid: str) -> bool:
        """It stopped, or its session's turn or the session ended: no longer watched. True when it was told."""
        w = self.watched.pop(aid, None)
        return bool(w and w["told"] is not None)

    def drop_session(self, sid: str) -> list[str]:
        gone = [aid for aid, w in self.watched.items() if w["sid"] == sid]
        for aid in gone:
            self.watched.pop(aid, None)
        return gone

    def _moved(self, w: dict) -> bool:
        if w["told"] is None:
            return False
        w["told"] = None
        return True

    @staticmethod
    def find(base: str, aid: str) -> str | None:
        """The subagent's transcript under its main's folder: subagents/agent-<id>.jsonl, or a Workflow's
        subagents/workflows/<run>/agent-<id>.jsonl (one glob of the runs, only while it is not found)."""
        name = f"agent-{aid}.jsonl"
        direct = os.path.join(base, "subagents", name)
        if os.path.exists(direct):
            return direct
        runs = glob.glob(os.path.join(glob.escape(base), "subagents", "workflows", "*", glob.escape(name)))
        return runs[0] if runs else None

    def background(self, tasks: list[dict]) -> None:
        """The main's Stop listed its background work ({id, type, status, description}; type subagent or workflow):
        none of those is a foreground call, and its description names it in the notice."""
        for task in tasks:
            w = self.watched.get(str(task.get("id")))
            if w is not None:
                w["foreground"] = False
                if isinstance(task.get("description"), str) and task["description"].strip():
                    w["description"] = " ".join(task["description"].split())[:HEAD_MAX]

    # ------------------------------------------------------------ the check

    def every_ms(self) -> int:
        """How often the files are stat'ed: CHECK_EVERY_MS, or a fifth of the shortest limit when that is shorter (a
        test's config of a few seconds), never under a second."""
        limits = [x for x in (self.quiet_ms, self.perm_ms) if x > 0]
        return max(1000, min([CHECK_EVERY_MS] + [x // 5 for x in limits]))

    def due(self, now: int) -> bool:
        return bool(self.watched) and now >= self.next_check

    def check(self, now: int) -> tuple[list[dict], list[str]]:
        """(notices to give, subagents that moved again since they were told). Call when due()."""
        self.next_check = now + self.every_ms()
        notices, moved = [], []
        for aid, w in list(self.watched.items()):
            if not w["path"] and w["base"]:
                w["path"] = self.find(w["base"], aid)
            if w["path"]:
                try:
                    st = self.stat(w["path"])
                except OSError:
                    st = None
                if st is not None:
                    size, mtime_ms = st.st_size, int(st.st_mtime * 1000)
                    grew = w["size"] is not None and (size != w["size"] or mtime_ms > w["mtimeMs"])
                    w["size"], w["mtimeMs"] = size, mtime_ms
                    if grew:
                        w["lastAt"] = max(w["lastAt"], mtime_ms)
                        if self._moved(w):
                            moved.append(aid)
                    elif mtime_ms > w["lastAt"]:
                        w["lastAt"] = mtime_ms
            if w["told"] is not None or w["notices"] >= NOTICES_MAX:
                continue
            notice = None
            if self.perm_ms > 0 and w["waitSince"] and now - w["waitSince"] >= self.perm_ms:
                notice = {"kind": "wait", "since": w["waitSince"], "tool": w["waitTool"], "head": w["waitHead"]}
            elif self.quiet_ms > 0:
                limit = max([self.quiet_ms] + [t + TIMEOUT_GRACE_MS for t in w["calls"].values() if t > self.quiet_ms])
                # a wait on a person is told first (it began with its hook, so its quiet is never longer)
                if now - w["lastAt"] >= limit:
                    notice = {"kind": "quiet", "since": w["lastAt"], "tool": w["tool"], "head": w["head"]}
            if notice:
                w["told"] = notice["since"]
                w["notices"] += 1
                notices.append({**notice, "agentId": aid, "sessionId": w["sid"], "agentType": w["type"] or "",
                                "foreground": w["foreground"], "description": w["description"],
                                "path": w["path"] or "", "minutes": max(1, (now - notice["since"]) // 60_000)})
        return notices, moved


def desktop_notifier(environ=None, run=None):
    """(title, text) -> shown, for a foreground subagent's stall (requester 11-18: 画面＋デスクトップの通知; no new
    dependency): macOS's own `osascript -e 'display notification …'`, the words passed as arguments (never put into
    the script), run off the loop with a 10 s limit. None where there is no osascript (the page alone shows it).
    Under JUI_VIZ_E2E=1 nothing is shown: each one is a line in <viz home>/desktop-notices.e2e.jsonl for the test."""
    import json
    import shutil
    import subprocess
    import sys
    import threading

    from . import paths
    env = os.environ if environ is None else environ
    if env.get("JUI_VIZ_E2E") == "1":
        log = paths.viz_home() / "desktop-notices.e2e.jsonl"

        def record(title: str, text: str) -> bool:
            with open(log, "a", encoding="utf-8") as f:
                f.write(json.dumps({"title": title, "text": text}, ensure_ascii=False) + "\n")
            return True
        return record
    if sys.platform != "darwin" or not shutil.which("osascript"):
        return None
    def osascript(title: str, text: str) -> None:
        subprocess.run(["osascript", "-e", "on run argv", "-e", "display notification (item 2 of argv) with title (item 1 of argv)",
                        "-e", "end run", title, text],
                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10, check=False)
    runner = run or osascript

    def show(title: str, text: str) -> bool:
        def go():
            try:
                runner(str(title)[:120], str(text)[:400])
            except (OSError, subprocess.SubprocessError):
                pass
        threading.Thread(target=go, name="viz-desktop-notify", daemon=True).start()
        return True
    return show
