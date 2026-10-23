"""Hook payloads, the agents list and session files → projects / sessions / agents / events.

Every entry point takes the time as an argument (``at``, epoch ms) instead of
reading a clock, so a recording replayed with its own timestamps rebuilds
the same state (the recorder's test depends on it).

Design: 03 (fields), 04 §1–§4 (slices, robot states, rooms).
"""
from __future__ import annotations

import re
import threading
import time
from typing import Any

from pathlib import Path

from . import clockout, data_docs, gitbox, i18n, infra_docs, prices, robots
from .rooms import Rooms, tilde
from .sources.jsonui_project import TEXTS_SUFFIX, JsonUIProject, test_dirs
from .attachments import Attachments
from .calls import CallBook, peer_name
from .denials import DenialBook
from .permissions import PROMPTS_QUEUED_MAX, PermissionBook
from .questions import QuestionBook
from .sources import devices as devices_mod
from .sources import launch, processes
from .sources.history import sent_files as history_sent_files
from .sources.tasks import TaskBook
from .sources.test_progress import ProgressBook
from .state import VizState
from . import quiet_fs

#: The 18 events the hooks are installed for; anything else is dropped.
KNOWN_EVENTS = frozenset({
    "SessionStart", "SessionEnd", "UserPromptSubmit", "PreToolUse", "PostToolUse",
    "PostToolUseFailure", "PermissionRequest", "PermissionDenied", "Notification",
    "SubagentStart", "SubagentStop", "TaskCreated", "TaskCompleted", "Stop",
    "StopFailure", "CwdChanged", "PreCompact", "PostCompact",
})
TOOL_EVENTS = frozenset({"PreToolUse", "PostToolUse", "PostToolUseFailure", "PermissionRequest", "PermissionDenied"})

PROMPT_MAX = 200
#: A test run's command as the card's テスト実行 row shows it: whole up to this (2.3.6 — the row is cut to one line by the
#: page and its floating tag shows the rest; until then the server cut it at 200 and the tail was nowhere).
TEST_COMMAND_MAX = 2000
#: How a robot's act says it waits for the person (a permission / a question); _settled_act takes it off when the wait ends.
def perm_wait() -> str:
    return i18n.tl("status.waiting") + " "


def question_wait() -> str:
    return i18n.tl("status.asking")
#: How much of a prompt sent from the page goes into the event log (the rest is never stored).
PROMPT_HEAD = 40
#: A session process whose argv could not be read is tried again after 1 s, then 2, 4 … up to 30 s apart.
ARGV_RETRY_FIRST = 1.0
ARGV_RETRY_MAX = 30.0
MESSAGE_MAX = 300
SUBAGENT_LINGER_MS = 5_000
DONE_TO_IDLE_MS = 3_000
CARRY_MS = 3_000
DELETING_KEPT = 64   # Bash deletions waiting for their PostToolUse (the shredder, 10-19)
THINKING_AFTER_MS = 30_000
# "Heavy" work (requester, 10-18): any one of these, while the session works.
HEAVY_TOKENS_PER_MIN = 2_000          # output tokens a minute over the last HEAVY_WINDOW_MS (the transcript)
HEAVY_WINDOW_MS = 120_000
HEAVY_TOOL_MS = 60_000                # one tool call running this long (hooks)
HEAVY_SUBAGENTS = 3                   # subagents at work at once (hooks)
# The bill over a robot (2.3.6, ticket 2026-10-19-jui-viz-cost-bill-over-robot): each response's estimated cost, kept
# this long in the "bills" slice (the page shows each one once, by its message id), at most BILLS_MAX of them.
BILL_KEEP_MS = 30_000
BILLS_MAX = 60
UNPRICED_MAX = 20
ENDED_LINGER_MS = 60_000
#: the hooks after which a session no longer waits for input (Notification idle_prompt set it): a prompt, a tool, its end
INPUT_WAIT_ENDS = frozenset({"UserPromptSubmit", "PreToolUse", "SessionEnd", "SessionStart"})
#: The events the --stop hook runs on (hooks_installer.STOP_EVENTS, the plugin's hooks.json): a tool boundary is answered,
#: a new prompt only takes the last turn's stop away (synchronously, before that turn's first tool asks)
STOP_EVENTS = frozenset({"UserPromptSubmit", "PreToolUse", "PostToolUse"})
STOP_ANSWERED = frozenset({"PreToolUse", "PostToolUse"})
# Waiting on background work (requester, 10-18): a session whose Stop listed background_tasks keeps its light on
# until the work ends — the next Stop without any, SessionEnd, or no background shell left under its process
# (check_background). Only when its process cannot be watched (no pid, or ps has not answered for
# BACKGROUND_UNWATCHED_MS) does it go dark after BACKGROUND_CAP_MS.
BACKGROUND_CAP_MS = 30 * 60_000
BACKGROUND_UNWATCHED_MS = 60_000
TEST_RUNS_KEPT = 50
DEVICE_CMDS_KEPT = 200   # device ids named by Bash commands, newest kept (the デバイス pane's estimate)
EDIT_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}


def clip_strings(value: Any, limit: int) -> Any:
    """Every string inside ``value`` cut to ``limit`` characters (the 2,000-char rule)."""
    if isinstance(value, str):
        return value if len(value) <= limit else value[:limit] + "…"
    if isinstance(value, dict):
        return {k: clip_strings(v, limit) for k, v in value.items()}
    if isinstance(value, list):
        return [clip_strings(v, limit) for v in value]
    return value


def _s(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


QUESTION_TOOL = "AskUserQuestion"
#: A skill in use (ticket 2026-10-21-jui-viz-skill-spirit): Claude calling the Skill tool. Its robot carries ``skill`` until
#: the turn ends (inline) or the skill's own subagent finishes (forked); never longer than SKILL_MAX_MS (the end is
#: guessed: no hook says it). A forked skill runs in a subagent that starts within SKILL_FORK_MS of the call: the skill
#: moves to it (the call names no agent; its agentId comes only with the result).
SKILL_TOOL = "Skill"
#: A file sent to the person (ticket 2026-10-23-viz-sent-pictures-gone-when-the-file-moves): its pictures are copied when
#: the call is made (viz/sent_copies.py), so the history still shows them after the file moves.
SENT_TOOL = "SendUserFile"
SKILL_MAX_MS = 30 * 60_000
SKILL_FORK_MS = 5_000
SKILL_NAME = re.compile(r"[A-Za-z0-9_.:-]{1,128}")


def _question_summary(card: dict) -> str:
    """The log line of an answered question: each question's header (or text) and the answer it got."""
    got = card.get("sentAnswers") or card.get("gotAnswers") or {}
    parts = [f"{q.get('header') or q['question']}: {got.get(q['question'], '?')}" for q in card["questions"]]
    return _head(" / ".join(parts), 300) or ""


def _head(text: Any, n: int) -> str | None:
    if not isinstance(text, str) or not text:
        return None
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1] + "…"



def _runs_of(test: dict) -> list[str]:
    """Every progress run tied to a test command (a command runs one per test file)."""
    runs = test.get("progressRuns")
    if runs:
        return runs
    return [test["progressRun"]] if test.get("progressRun") else []


def _file_key(project: JsonUIProject, file: str | None) -> str:
    """A driver's `file` as the test file it names in *project* (any platform's spelling), else as written:
    the case key is (file, test, case), so two test files with the same test / case names stay two. The room's own
    apps first: a worktree's app@branch holds the same files, and two owners would name none (each spelling its own
    key, one case counted twice)."""
    matched = (project.test_file_matches(file, only=[s for s in project.sources if not s.linked])
               or project.test_file_matches(file)) if file else []
    return matched[0][1] if matched else (file or "")


def _settled_act(act: str, failed: bool) -> str:
    """The act once the wait it names is over: a permission's act loses its 許可待ち (the call itself is what it did),
    a question's says it got its answer — or none, when the call failed (declined, interrupted). Any other act stays."""
    if act.startswith(perm_wait()):
        return act[len(perm_wait()):]
    if act.startswith(question_wait()):
        return i18n.tl("act.question.none") if failed else i18n.tl("act.question.answered")
    return act

#: The data server's counts (2.3.5) are never taken on the event loop (the independent review, 10-19: counted for each watcher
#: event, 200 files rewritten held /health for 8.8 s): a change marks the room, tick hands the marked rooms to one
#: worker thread once DATA_DOCS_QUIET_MS have passed without a new change, and applies what it found on a later tick.
#: Every DATA_DOCS_EVERY_MS every room is marked (the watcher misses a docs/api or docs/db moved whole).
DATA_DOCS_EVERY_MS = 5_000
DATA_DOCS_QUIET_MS = 500
#: The server room's door (2.3.9+, infra_docs.py): every room's model files are counted (a listing, nothing opened)
#: this often, in a worker thread of their own; the model itself is read only when the door is pressed.
INFRA_EVERY_MS = 5_000
#: how often each room looks again at the worktrees its sessions work in (and at once when their cwds change):
#: a worktree made, removed or switched to another branch while a session works in it
WORKTREES_EVERY_MS = 5_000


def attachment_line(record: dict) -> str:
    """The prompt's line for one attached file: its absolute path, then the shown name, media type and size. In English
    (the receiving session reads it; 55-history.js reads this form and the Japanese one written before 2.3.13)."""
    size = record["size"]
    shown = f"{size} B" if size < 1024 else f"{size / 1024:.0f} KB" if size < 1024 * 1024 else f"{size / 1048576:.1f} MB"
    return f"attached: {record['path']} ({record['name']}, {record['media']}, {shown})"


def _skill_forked(response) -> bool:
    """A Skill call's result says it ran in a subagent: {"status": "forked", …} (measured in the transcripts of 10-21),
    or the result's words 'completed (forked execution)'."""
    if isinstance(response, dict):
        return response.get("status") == "forked"
    return isinstance(response, str) and "(forked execution)" in response


class World:
    def __init__(self, state: VizState, tool_input_max: int = 2000, session_start=None) -> None:
        self.state = state
        self.tool_input_max = tool_input_max
        # session id, cwd, transcript path -> when the session really started (sources/transcripts.py), or None.
        # A session gets ``since`` only from it; never the time the server first saw the session.
        self.session_start = session_start
        self._since_tries: dict[str, int] = {}
        # files attached to prompts from the page (attachments.py); viz_cmd replaces it with the configured place
        self.attachments = Attachments()
        # session id -> (cwd, transcript path from a hook); the transcript's usage tail; tokens per message id
        self.transcript_path = None
        # session id, cwd, transcript path, agent id, agent transcript path -> the 応答の履歴 tab (sources/history.py)
        self.history_reader = None
        self.sent_copies = None   # viz/sent_copies.SentCopies, set by the server (a World made in a test copies nothing)
        self._agent_paths: dict[str, str] = {}   # subagent id -> the hook's agent_transcript_path
        self._paths: dict[str, tuple[str | None, str | None]] = {}
        self._tails: dict = {}
        self._usage_seen: dict[str, dict[str, int]] = {}
        # the bills: the price table (prices.PriceBook, read again off the loop when the user's file changes), the
        # bills of the last BILL_KEEP_MS, per transcript the usage last billed for each message id (a message is
        # written once per content block with the same usage: billed once), and the models with no price
        self.prices: prices.PriceBook | None = None
        self._prices_pool = None
        self._bills: list[dict] = []
        self._billed: dict[str, dict[str, tuple]] = {}
        self._unpriced: dict[str, int] = {}
        self._tokens: dict[str, list[tuple[int, int]]] = {}
        self._tool_started: dict[str, int] = {}
        self.rooms = Rooms()
        self.sessions: dict[str, dict] = {}
        self.agents: dict[str, dict] = {}
        # Robot bookkeeping the page does not need: open tool_use_ids, timers.
        self._open: dict[str, list[str]] = {}
        self._open_tool: dict[str, str] = {}  # tool_use_id -> tool_name
        self._deleting: dict[str, dict] = {}  # tool_use_id -> what its Bash command deletes (robots.deletions)
        # session id -> the Skill calls not yet given a subagent: (when, the calling agent, the skill), oldest first
        self._skill_called: dict[str, list[tuple[int, str, dict]]] = {}
        self._until: dict[str, tuple[int, str]] = {}  # agent id -> (time, state to go to)
        # The tool_use_id an agent was asking permission for. PermissionRequest
        # carries no tool_use_id and a refusal may send no PostToolUse (nor
        # PermissionDenied: measured in -p), so the next PreToolUse from that
        # agent settles it — otherwise the id stays open and the robot never idles.
        self._asking: dict[str, str] = {}
        self._new_files: set[str] = set()  # tool_use_ids writing a file that did not exist
        self.pid_to_session: dict[int, str] = {}
        # A session's process as its newest agents-list row / session file names it: (pid, procStart, entrypoint),
        # and that process's argv as read once (sources/launch.py) — only the classification is ever published.
        self.session_proc: dict[str, tuple] = {}
        self._argv: dict[tuple, list] = {}            # argv read, per process: only successful reads are kept
        self._argv_retry: dict[tuple, tuple] = {}     # a failed read: (when to try again, the wait after that), monotonic s
        self.read_argv = launch.read_argv   # a test puts its own reader here
        self.clock = time.monotonic         # and its own clock here
        self.tasks = TaskBook()
        self.perms = PermissionBook()
        self.questions = QuestionBook()
        # tool calls stopped by auto mode (denials.py): the hook and the transcript, one card per call
        self.denials = DenialBook()
        self.git_jobs: list = []                 # (agent id, trip id, what to count) for the box (2.3.4)
        # SendMessage between two sessions here (calls.py): a session's messaging name and socket -> its id
        self.calls = CallBook()
        self._peer_names: dict[str, str] = {}
        self._peer_socks: dict[str, str] = {}
        self._session_names: dict[str, str] = {}
        self.devices: list[dict] = []
        # who uses a device (sources/devices.py, the デバイス pane): device id -> sessions with a process naming it
        # (ps, only while a device is up), and device id -> (agent id, at) of the last Bash command naming it
        self.device_procs: dict[str, list[str]] = {}
        self.device_cmds: dict[str, tuple[str, int]] = {}
        self.machine: dict = {}                  # this machine's load (sources/machine.py), every 5 s
        self.wall_ms = lambda: int(time.time() * 1000)   # the clock a command's estimate ages by (tests set their own)
        self.progress = ProgressBook()
        self.tests: dict[str, dict] = {}
        # a finished test command's head from its output (robots.test_verdict without the runner's records): kept so a
        # run_end that comes after the command ended decides it again, the runner's records first (2.3.10)
        self._test_from_output: dict[str, dict] = {}
        # Per case, the newest outcome a source reported, merged into each project's test_results:
        # live progress (project id -> spec id -> (test, case) -> (t, status)) and the saved
        # result files' rows (sources/test_results.py). Newest wins, so a case that ran live
        # and was then written to a file is counted once.
        self.live_cases: dict[str, dict[str, dict[tuple[str, str, str], tuple[int, str]]]] = {}
        self.saved_rows: list[dict] = []
        self._saved_by_run: dict[str, list[dict]] = {}
        # Merging is not per record (ticket 2026-10-19-jui-viz-merge-results-per-progress-record-freezes-the-server):
        # a record marks its project, tick merges each marked project once. Where a saved row's file goes
        # (_saved_specs) is remembered per (project, file, platform, app) until a project loads or a spec / test
        # file changes; which runs are tied to a command is compared at each merge (_run_rooms).
        self._merge_due: set[str] = set()
        self._ties: dict[tuple, list[str]] = {}
        self._file_keys: dict[tuple[str, str], str] = {}
        self._all_test_keys: dict[str, list[str]] | None = None   # test file name -> every room's keys of it
        self._cases_due: set[str] = set()                         # test commands whose cases tick rebuilds
        self._run_rooms_seen: dict[str, frozenset[str]] = {}
        self.jsonui: dict[str, JsonUIProject] = {}
        self.jsonui_errors: dict[str, str] = {}
        self._data_docs_cache: dict[str, dict] = {}   # project id -> data_docs.counts' cache (the worker's only)
        self._data_docs_at = 0
        self._data_docs_due: dict[str, int] = {}     # project id -> its last change (ms)
        self._data_docs_dirs: dict[str, tuple] = {}  # project id -> its docs/api and docs/db (for file_changed)
        self._data_docs_job = None                   # the worker's future: {project id: (counts, dirs)}
        self._data_docs_pool = None
        self._infra_cache: dict[str, dict] = {}   # project id -> infra_docs.counts' cache (the worker's only)
        self._infra_at = -INFRA_EVERY_MS
        self._infra_job = None
        self._infra_pool = None
        self._dirty: set[str] = set()
        self._now = 0
        # Called with each JsonUIProject once it is loaded (serve starts its file watcher).
        self.on_project_loaded = None
        # Called with a JsonUIProject whose apps changed (a worktree shown or gone: serve watches its folders again).
        self.on_sources_changed = None
        self._worktree_cwds: frozenset = frozenset()
        self._test_cwds: dict[str, str] = {}   # test command id -> the cwd of its session (never sent to the page)
        self._worktrees_at = -WORKTREES_EVERY_MS

    # ---------------------------------------------------------------- labels

    def _label(self, ident: str) -> str:
        taken = {a["label"] for a in self.agents.values() if a["id"] != ident}
        taken |= {s["label"] for s in self.sessions.values() if s["id"] != ident}
        for n in range(2, len(ident) + 1):
            label = ident[:n]
            if label not in taken:
                return label
        return ident

    # ---------------------------------------------------------------- sessions / agents

    def _session(self, sid: str, cwd: str | None, at: int) -> dict:
        session = self.sessions.get(sid)
        if session is None:
            project = self.rooms.project_for(cwd or "?")
            session = {
                "id": sid, "label": self._label(sid), "projectId": project["id"],
                "cwd": tilde(cwd) if cwd else "?", "status": "idle", "relay": False, "prompt": False,
                "startedAt": at, "updatedAt": at, "roomSince": at,
            }
            self.sessions[sid] = session
            self._dirty |= {"sessions", "projects"}
            self._main(sid, at)
            if project["jsonui"]:
                self.jsonui_project(project["id"], at)
        elif cwd and session["cwd"] == "?":
            self._move(session, cwd, at)
        return session

    SINCE_TRIES = 20

    def _find_since(self, session: dict, cwd: str | None, transcript: str | None) -> None:
        """The session's real start, once (a new session's transcript appears with its first prompt: retried)."""
        sid = session["id"]
        if cwd or transcript:
            old = self._paths.get(sid, (None, None))
            self._paths[sid] = (cwd or old[0], transcript or old[1])
        if self.session_start is None or session.get("sinceFrom") == "transcript" or self._since_tries.get(sid, 0) >= self.SINCE_TRIES:
            return
        self._since_tries[sid] = self._since_tries.get(sid, 0) + 1
        since = self.session_start(sid, cwd, transcript)
        if isinstance(since, int) and since > 0:
            session["since"], session["sinceFrom"] = since, "transcript"   # the session's own start wins
            self._dirty.add("sessions")

    def _agents_since(self, session: dict, row: dict, at: int) -> None:
        """Without a readable transcript, the process start `claude agents --json` reports (a real time, not
        when the server saw the session). A transcript found later replaces it."""
        started = row.get("startedAt")
        if "since" in session or not isinstance(started, int) or isinstance(started, bool) or not 0 < started <= at:
            return
        session["since"], session["sinceFrom"] = started, "agents"
        self._dirty.add("sessions")

    def _move(self, session: dict, cwd: str, at: int) -> None:
        project = self.rooms.project_for(cwd)
        if session["projectId"] != project["id"] or session["cwd"] != tilde(cwd):
            if session["projectId"] != project["id"]:
                session["roomSince"] = at   # the view seats robots in the order they came into a room
            session["projectId"] = project["id"]
            session["cwd"] = tilde(cwd)
            self._dirty |= {"sessions", "projects"}

    def _main(self, sid: str, at: int) -> dict:
        agent = self.agents.get(sid)
        if agent is None:
            agent = {
                "id": sid, "label": self.sessions[sid]["label"], "sessionId": sid, "kind": "main",
                "role": "main", "state": "idle", "act": i18n.tl("status.idle"), "startedAt": at, "updatedAt": at,
            }
            self.agents[sid] = agent
            self._dirty.add("agents")
        return agent

    def _sub(self, sid: str, aid: str, agent_type: str | None, at: int) -> dict:
        agent = self.agents.get(aid)
        if agent is None:
            agent = {
                "id": aid, "label": self._label(aid), "sessionId": sid, "kind": "sub",
                "agentType": agent_type, "role": robots.role_for(agent_type, False),
                "state": "idle", "act": i18n.tl("act.start"), "startedAt": at, "updatedAt": at,
            }
            self.agents[aid] = agent
            self._dirty.add("agents")
        elif agent_type and not agent.get("agentType"):
            agent["agentType"] = agent_type
            agent["role"] = robots.role_for(agent_type, False)
        return agent

    def _set(self, agent: dict, at: int, state: str | None = None, act: str | None = None, **extra) -> None:
        if state is not None:
            agent["state"] = state
            self._until.pop(agent["id"], None)
            if "waitingOn" not in extra:
                agent.pop("waitingOn", None)   # what it waits on belongs to the state it was set with
            if "readKind" not in extra:
                agent.pop("readKind", None)    # so does the kind of reading (the dictionary, robots.read_kind)
        if act is not None:
            agent["act"] = act
        for k, v in extra.items():
            if v is None:
                agent.pop(k, None)
            else:
                agent[k] = v
        agent["updatedAt"] = at
        self._dirty.add("agents")

    def _end(self, session: dict, agent: dict, at: int) -> None:
        """The session has ended (SessionEnd, or 退勤 from the page): ended, and its robot walks out of the door."""
        sid = session["id"]
        self._background_off(session, at)
        self.perms.session_stopped(sid, at)
        self._dirty.add("perms")
        self.attachments.session_ended(sid, at)
        if self.questions.session_stopped(sid, at):
            self._dirty.add("questions")
        if self.calls.session_ended(sid, at):
            self._dirty.add("calls")
        if self.denials.session_ended(sid, at):
            self._dirty.add("denials")
        session.pop("stopAt", None)
        session.pop("stopTurn", None)
        session.pop("haltOn", None)
        self._status(session, "ended", at)
        self._set(agent, at, "idle", i18n.tl("act.clock_out"), leftAt=at)

    def clock_out(self, sid: str, at: int) -> None:
        """退勤 from the page ended this session's process (clockout.end_session saw it go): the same as its SessionEnd,
        which the session sends too — whichever comes first ends it."""
        session = self.sessions.get(sid)
        if session is None:
            return
        session["clockedOut"] = at   # also when its own SessionEnd came first
        self._dirty.add("sessions")
        if session["status"] != "ended":
            self._end(session, self._main(sid, at), at)

    def clock_out_event(self, sid: str, at: int, record: dict) -> None:
        """The event log's line for one 退勤 attempt: when (the event's time), to whom, and the outcome."""
        session = self.sessions.get(sid)
        label = session["label"] if session else sid[:8]
        how = {"ended": i18n.tl("ev.clockout.ended"), "not-ended": i18n.tl("ev.clockout.not_ended"),
               "refused": i18n.tl("ev.clockout.refused")}.get(record.get("result"), "?")
        pid = i18n.tl("ev.clockout.pid", pid=record["pid"]) if record.get("pid") else ""
        why = "" if record.get("result") == "ended" else f": {record.get('reason', '')}"
        self.state.add_event({"at": at, "sessionId": sid, "agentId": sid, "kind": "ClockOut", "cat": "session",
                              "text": i18n.tl("ev.clockout", label=label, pid=pid, how=how, why=why)})

    def _status(self, session: dict, status: str, at: int, waiting_for: str | None = None) -> None:
        if session["status"] != status or session.get("waitingFor") != waiting_for:
            session["status"] = status
            if waiting_for:
                session["waitingFor"] = waiting_for
            else:
                session.pop("waitingFor", None)
            self._dirty.add("sessions")
        if self.tasks.turn_waiting(session["id"], status == "waiting", waiting_for):
            self._dirty.add("tasks")
        session["updatedAt"] = at

    # ---------------------------------------------------------------- JsonUI projects

    def jsonui_project(self, project_id: str, at: int) -> JsonUIProject | None:
        """The loaded JsonUI project of a room, loading it on first sight."""
        if project_id in self.jsonui:
            return self.jsonui[project_id]
        project = self.rooms.projects.get(project_id)
        if not project or not project["jsonui"] or project_id in self.jsonui_errors:
            return None
        root = self.rooms.root_of(project_id)
        try:
            loaded = JsonUIProject(Path(root), project_id)
            loaded.load_all(at)
        except (OSError, ValueError) as exc:
            self.jsonui_errors[project_id] = f"{type(exc).__name__}: {exc}"[:200]
            return None
        self.jsonui[project_id] = loaded
        self._forget_ties()
        for other in self.jsonui.values():  # a new room's test files can make another room's row ambiguous
            self._merge_results(other)
        self._dirty |= {"specs", "tasks"}
        self._data_docs_dirs[project_id] = tuple(d for _k, d, _r in data_docs.doc_dirs(loaded))
        self._data_docs_due[project_id] = 0   # counted by the worker on the next tick
        if self.on_project_loaded is not None:
            self.on_project_loaded(loaded)
        return loaded

    def _data_docs_tick(self, at: int) -> None:
        """The data server's counts (2.3.5), off the event loop: apply a finished count, then hand the rooms marked and
        quiet for DATA_DOCS_QUIET_MS to the worker (data_docs.counts and doc_dirs read the files there). A room's row
        gets ``dataDocs``: the page puts the rack there when either count is above 0."""
        if at - self._data_docs_at >= DATA_DOCS_EVERY_MS:
            self._data_docs_at = at
            for pid in self.jsonui:
                self._data_docs_due.setdefault(pid, 0)
        job = self._data_docs_job
        if job is not None:
            if not job.done():
                return
            self._data_docs_job = None
            try:
                found = job.result()
            except Exception:  # noqa: BLE001 — a count that failed is taken again on the next round
                found = {}
            for pid, (n, dirs) in found.items():
                self._data_docs_dirs[pid] = dirs
                room = self.rooms.projects.get(pid)
                if room is not None and room.get("dataDocs") != n:
                    room["dataDocs"] = n
                    self._dirty.add("projects")
        quiet = {pid: self.jsonui[pid] for pid, t in self._data_docs_due.items() if pid in self.jsonui and at - t >= DATA_DOCS_QUIET_MS}
        if not quiet:
            return
        for pid in quiet:
            del self._data_docs_due[pid]
        if self._data_docs_pool is None:
            from concurrent.futures import ThreadPoolExecutor
            self._data_docs_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="jui-viz-data-docs")
        caches = {pid: self._data_docs_cache.setdefault(pid, {}) for pid in quiet}

        def count() -> dict:
            return {pid: (data_docs.counts(p, caches[pid]), tuple(d for _k, d, _r in data_docs.doc_dirs(p))) for pid, p in quiet.items()}
        self._data_docs_job = self._data_docs_pool.submit(count)

    def _infra_tick(self, at: int) -> None:
        """The server room's door: every INFRA_EVERY_MS, each room's model files counted in a worker thread (a listing of
        its infra folder, infra_docs.counts); a room's row gets ``infraDocs`` {files, dir} and the page puts the door
        where files > 0. Any room, JsonUI or not: the folder is found from the room's own root."""
        job = self._infra_job
        if job is not None:
            if not job.done():
                return
            self._infra_job = None
            try:
                found = job.result()
            except Exception:  # noqa: BLE001 — taken again on the next round
                found = {}
            for pid, n in found.items():
                room = self.rooms.projects.get(pid)
                if room is not None and room.get("infraDocs") != n:
                    room["infraDocs"] = n
                    self._dirty.add("projects")
        if at - self._infra_at < INFRA_EVERY_MS:
            return
        self._infra_at = at
        roots = {pid: self.rooms.root_of(pid) for pid in self.rooms.projects}
        roots = {pid: r for pid, r in roots.items() if r}
        if not roots:
            return
        if self._infra_pool is None:
            from concurrent.futures import ThreadPoolExecutor
            self._infra_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="jui-viz-infra")
        caches = {pid: self._infra_cache.setdefault(pid, {}) for pid in roots}

        def count() -> dict:
            return {pid: infra_docs.counts(root, caches[pid]) for pid, root in roots.items()}
        self._infra_job = self._infra_pool.submit(count)

    def _worktrees_tick(self, at: int) -> None:
        """Each loaded room shows the worktrees of its apps that a session not ended works in (JsonUIProject.
        set_worktrees): when the sessions' cwds change, and every WORKTREES_EVERY_MS (a worktree made, removed or on
        another branch)."""
        cwds = frozenset(str(Path(s["cwd"]).expanduser()) for s in self.sessions.values()
                         if s.get("status") != "ended" and s.get("cwd") not in (None, "?"))
        if cwds == self._worktree_cwds and at - self._worktrees_at < WORKTREES_EVERY_MS:
            return
        self._worktree_cwds, self._worktrees_at = cwds, at
        for project in self.jsonui.values():
            if project.set_worktrees(cwds, at):
                self._forget_ties()
                self._merge_due.add(project.project_id)
                self._dirty.add("specs")
                if self.on_sources_changed is not None:
                    self.on_sources_changed(project)

    def _worktree_twins(self, project, path: str) -> list:
        """The other loaded rooms that show the file through a worktree of theirs (the session's room is its own)."""
        target = Path(path)
        return [p for p in self.jsonui.values() if p is not project
                and any(s.base is not None and target.is_relative_to(d) for s in p.sources
                        for d in (s.spec_dir, s.layouts_dir, s.tests_dir) if d is not None)]

    def infra_root(self, project_id) -> str | None:
        """The room's root the server room reads (POST /api/infra-docs, /api/infra-icon): a room this server knows, by
        its id only; None otherwise."""
        if not isinstance(project_id, str) or project_id not in self.rooms.projects:
            return None
        return self.rooms.root_of(project_id)

    def data_docs_room(self, project_id):
        """The loaded JsonUI room the rack's sheet reads (POST /api/data-docs), its count marked to be taken again;
        None for a room that is not one. The reading itself (data_docs.payload) is the caller's, off the event loop."""
        loaded = self.jsonui.get(project_id) if isinstance(project_id, str) else None
        if loaded is not None:
            self._data_docs_due[project_id] = 0
        return loaded

    def data_docs(self, project_id) -> tuple[int, object]:
        """The rack's documents of one JsonUI room (data_docs.read), read now: (200, JSON bytes) or (404, reason). The
        room is named by its id only; which files are read is the server's (data_docs.doc_dirs). Blocking: the server
        calls it in an executor."""
        loaded = self.jsonui.get(project_id) if isinstance(project_id, str) else None
        if loaded is None:
            return 404, "no such JsonUI room"
        return 200, data_docs.payload(loaded)

    def file_changed(self, project_id: str, path: str, at: int, by: str | None = None) -> None:
        """A spec, layout or test file changed (an edit by a robot, or the watcher)."""
        project = self.jsonui.get(project_id)
        if project is None:
            return
        target = Path(path)
        if target.suffix == ".json" and any(target.is_relative_to(d) for d in self._data_docs_dirs.get(project_id, ())):
            self._data_docs_due[project_id] = at   # counted off the loop once quiet (_data_docs_tick); read when pressed
            return
        if target.name.endswith(TEXTS_SUFFIX):
            project.reload_texts(target, at)
        elif target.name.endswith(".spec.json"):
            project.reload_spec(target, at, by)
            self._forget_ties()  # a spec's name and layoutFile decide which spec a test file reaches
            self._merge_due.add(project.project_id)
        elif target.name.endswith(".test.json"):
            project.load_tests()
            self._forget_ties()  # which app has a test file decides where a saved row goes
            self._merge_due.update(self.jsonui)
        for sid in project.specs_touching(path):
            if by:
                entry = project.specs[sid]
                entry.by, entry.by_until = by, at + 10_000
        self._dirty.add("specs")

    def _touch_files(self, session: dict, agent: dict, tool_input: dict, at: int, after: bool,
                     use_id: str | None = None) -> None:
        path = tool_input.get("file_path") or tool_input.get("notebook_path")
        if not isinstance(path, str):
            return
        project = self.jsonui_project(session["projectId"], at)
        if project is None:
            return
        target = Path(path)
        in_artifacts = any(target.is_relative_to(d) for d in project.artifact_dirs())
        if not after and in_artifacts and use_id and not quiet_fs.exists(target):
            self._new_files.add(use_id)  # a new spec / layout / test is being written
        twins = self._worktree_twins(project, path)   # a room showing this worktree hears the robot write too
        if after:
            self.file_changed(session["projectId"], path, at, by=agent["id"])
            for twin in twins:
                self.file_changed(twin.project_id, path, at, by=agent["id"])
            if use_id in self._new_files and quiet_fs.exists(target):
                # A new artifact: the robot carries the paper to the shelf (P7 §A4).
                self._set(agent, at, "carry", robots._clip(i18n.tl("act.carry", path=robots._rel(path, str(project.root)))))
                self._until[agent["id"]] = (at + CARRY_MS, "idle")
            self._new_files.discard(use_id or "")
        else:
            for room in (project, *twins):
                hits = room.specs_touching(path)
                for sid in hits:
                    entry = room.specs[sid]
                    entry.by, entry.by_until = agent["id"], at + 10_000
                if hits:
                    self._dirty.add("specs")

    # ---------------------------------------------------------------- hooks

    def apply_hook(self, payload: dict, at: int) -> dict | None:
        """Apply one hook payload. Returns the event added to the log, or None if dropped."""
        self._now = max(self._now, at)
        kind = payload.get("hook_event_name")
        sid = _s(payload.get("session_id"))
        if kind not in KNOWN_EVENTS or sid is None:
            return None
        cwd = _s(payload.get("cwd"))
        session = self._session(sid, cwd, at)
        if kind in INPUT_WAIT_ENDS and session.pop("inputWaitAt", None) is not None:   # it moves again: no longer waits for input
            self._dirty.add("sessions")
        self._find_since(session, cwd, _s(payload.get("transcript_path")))
        if kind != "SessionEnd":
            self.attachments.ended.pop(sid, None)   # resumed within the hour: its attachments stay
        root = self.rooms.root_of(session["projectId"])
        aid = _s(payload.get("agent_id"))
        agent_type = _s(payload.get("agent_type"))
        agent = self._sub(sid, aid, agent_type, at) if aid else self._main(sid, at)
        if aid and _s(payload.get("agent_transcript_path")):
            self._agent_paths[aid] = payload["agent_transcript_path"]
        tool = _s(payload.get("tool_name"))
        tool_input = payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {}
        use_id = _s(payload.get("tool_use_id"))
        cat = "tool" if kind in TOOL_EVENTS else "session"
        text = kind
        if tool == SENT_TOOL and use_id and kind in ("PreToolUse", "PostToolUse") and self.sent_copies is not None:
            # the files are read off this thread (up to 20 of 15 MB); a copy already taken is not taken again
            threading.Thread(target=self.sent_copies.take, args=(use_id, history_sent_files(tool_input), payload.get("cwd")),
                             name="viz-sent-copy", daemon=True).start()

        if kind == "SessionStart":
            if _s(payload.get("model")):
                session["model"] = payload["model"]
            if _s(payload.get("session_title")):
                session["title"] = _head(payload["session_title"], 120)
            self._status(session, "idle", at)
            self._clear_open(agent["id"])
            self._set(agent, at, "idle", i18n.tl("status.idle"))
            text = i18n.tl("ev.clock_in", source=payload.get('source') or '').strip()
        elif kind == "SessionEnd":
            self._end(session, agent, at)
            text = i18n.tl("ev.clock_out", reason=payload.get('reason') or '').strip()
        elif kind == "UserPromptSubmit":
            session["lastPrompt"] = _head(payload.get("prompt"), PROMPT_MAX)
            if self.questions.session_stopped(sid, at):   # a question left open: the person moved on
                self._dirty.add("questions")
            if agent["kind"] == "main":
                self.tasks.turn_started(sid, agent["id"], payload.get("prompt"), at)
                self._dirty.add("tasks")
                if self._new_prompt_unstops(session):
                    self._dirty.add("sessions")   # a stop asked for the last turn never stops this one
            self._status(session, "busy", at)
            # A new prompt: whatever the last turn left open was interrupted (Esc).
            self._clear_open(agent["id"])
            agent["promptAt"] = at   # the page ends an errand (the shredder, 10-19) that a new instruction overtakes
            # an instruction: no trip to the box any more — the trip stays, marked stopped, for the card's 最近の git
            self._set(agent, at, "idle", i18n.tl("act.prompted"), git={**agent["git"], "stopped": True} if agent.get("git") else None)
            self._skill_ended(sid, at)   # a new instruction: the skill the last turn used is over
            text = i18n.tl("ev.prompt", prompt=session['lastPrompt'] or '').strip()
        elif kind == "PreToolUse" and tool:
            if tool == QUESTION_TOOL:   # a question for the person (both the async forward and --ask bring it)
                self.questions.from_hook(sid, agent["id"], tool_input, use_id, at)
                self._dirty.add("questions")
            self._status(session, "busy", at)
            self._settle_asking(agent["id"])
            state = robots.state_for_tool(tool, tool_input)
            act = robots.act_for_tool(tool, tool_input, root)
            if tool == QUESTION_TOOL:   # it waits for the person: a raised hand, the room lit as waiting
                card = self.questions.cards.get(self.questions._by_use.get(use_id or "", ""))
                heads = [q.get("header") or q["question"] for q in (card or {}).get("questions", [])]
                state, act = "waiting", _head(f"{question_wait()} {' / '.join(heads)}", 120) or question_wait()
            if use_id:
                self._open.setdefault(agent["id"], []).append(use_id)
                self._open_tool[use_id] = tool
                self._tool_started[use_id] = at
            target = {"file": robots._rel(str(tool_input["file_path"]), root)} if _s(tool_input.get("file_path")) else None
            # A question waits for the person as a permission does, but it is not one: the page says 質問に回答待ち,
            # not 許可待ち, and does not count it with the permissions (requester, 10-18).
            asking = tool == QUESTION_TOOL
            if asking:
                self._status(session, "waiting", at, "question")
            self._set(agent, at, state, act, target=target, waitingOn="question" if asking else None,
                      readKind=robots.read_kind(tool) if state == "reading" else None)
            if state == "carry":
                self._until[agent["id"]] = (at + CARRY_MS, "idle")
            if tool == SKILL_TOOL:
                self._skill_started(session, agent, tool_input, use_id, at)
            if tool in robots.LAUNCH_TOOLS:   # the whistle: from now for its fixed length, whatever the call's length
                self._set(agent, at, whistle={"at": at, "until": at + robots.LAUNCH_WHISTLE_MS})
            if tool in EDIT_TOOLS:
                self._touch_files(session, agent, tool_input, at, after=False, use_id=use_id)
            if tool == "TodoWrite":
                self.tasks.from_todowrite(sid, agent["id"], tool_input.get("todos"), at)
                self._dirty.add("tasks")
            if tool == "SendMessage" and _s(tool_input.get("to")):
                self._dial(session, agent, tool_input["to"], use_id, at)
            if tool == "Bash" and _s(tool_input.get("command")):
                self._device_named(str(tool_input["command"]), agent, at)
            if tool in ("Bash",) and use_id:   # a deletion (10-19): what it deletes, kept until it has run
                gone = robots.deletions(str(tool_input.get("command", "")))
                if gone is not None:
                    self._deleting[use_id] = gone
                    for old in list(self._deleting)[:-DELETING_KEPT]:   # a PostToolUse that never came
                        del self._deleting[old]
            platform = robots.test_platform(str(tool_input.get("command", ""))) if state == "phone" else None
            if platform is not None and use_id:  # a test run only when it runs tests, not when it holds a device
                command = str(tool_input.get("command", ""))
                self._test_cwds[use_id] = str(Path(session["cwd"]).expanduser())   # the checkout it runs in (_saved_specs)
                self.tests[use_id] = {
                    "id": use_id, "projectId": session["projectId"], "agentId": agent["id"],
                    "platform": platform, "command": robots._clip(command, TEST_COMMAND_MAX),
                    "status": "running", "startedAt": at,
                }
                device_id = devices_mod.device_for_command(command, self.devices)
                if device_id:
                    self.tests[use_id]["deviceId"] = device_id
                    name = next((d["name"] for d in self.devices if d["id"] == device_id), device_id)
                    self._set(agent, at, act=robots._clip(i18n.tl("act.on_device", act=act, name=name)))
                    self._dirty.add("devices")
                for old in sorted(self.tests, key=lambda k: self.tests[k]["startedAt"])[:-TEST_RUNS_KEPT]:
                    del self.tests[old]
                self._dirty.add("tests")
            text = act
        elif kind in ("PostToolUse", "PostToolUseFailure") and tool:
            if tool == "Bash":
                self._git_trip(agent, sid, cwd, tool_input, payload.get("tool_response"), use_id, at)   # the box (2.3.4)
            if tool == QUESTION_TOOL:
                card = self.questions.tool_finished(sid, use_id, tool_input, at)
                if card is not None:
                    self._dirty.add("questions")
                    if card["status"] == "answered_in_terminal":
                        self.state.add_event({"at": at, "sessionId": sid, "agentId": agent["id"], "kind": "QuestionAnswered",
                                              "cat": "perm", "text": i18n.tl("ev.answered_in_terminal", summary=_question_summary(card))})
            opened = self._open.get(agent["id"], [])
            if use_id in opened:
                opened.remove(use_id)
            self._open_tool.pop(use_id or "", None)
            if self.perms.tool_finished(sid, use_id, True, at):
                self._dirty.add("perms")
            if session["status"] == "waiting":
                self._status(session, "busy", at)  # the tool it asked for has run
            # The call the robot waited on (its permission, or its question) has finished: the wait is over, even with
            # another of its calls still open (ticket 2026-10-19-jui-viz-act-stays-question-waiting-after-answer).
            waited_on = self._asking.get(agent["id"]) == use_id or (tool == QUESTION_TOOL and agent.get("waitingOn") == "question")
            if self._asking.get(agent["id"]) == use_id:
                self._asking.pop(agent["id"], None)
            failed = kind == "PostToolUseFailure"
            if not opened and agent["state"] not in ("carry",):
                self._set(agent, at, "idle", _settled_act(agent["act"], failed))
            elif opened and agent["state"] == "waiting" and waited_on:
                still = self._open_tool.get(opened[-1]) or ""   # the newest call still open: what the robot does now
                back = robots.state_for_tool(still, {}) if still else "idle"
                self._set(agent, at, back, _settled_act(agent["act"], failed), readKind=robots.read_kind(still) if back == "reading" else None)
            if tool == SKILL_TOOL and _skill_forked(payload.get("tool_response")):
                self._skill_ended(sid, at, use_id=use_id)   # a forked skill: its subagent's work is done
            if tool == "SendMessage":
                self.calls.sent(use_id, failed, at)
                self._dirty.add("calls")
            if tool in EDIT_TOOLS and not failed:
                self._touch_files(session, agent, tool_input, at, after=True, use_id=use_id)
            run = self.tests.get(use_id) if use_id else None
            if run is not None and run["status"] == "running":
                response = payload.get("tool_response")
                output = ""
                if isinstance(response, dict):
                    output = f"{response.get('stdout') or ''}\n{response.get('stderr') or ''}"
                elif isinstance(response, str):
                    output = response
                self._test_from_output[use_id] = robots.test_verdict(output[-200_000:], bool(failed))
                for old in list(self._test_from_output)[:-TEST_RUNS_KEPT]:
                    del self._test_from_output[old]
                run["endedAt"] = at
                self._test_decide(run)
                self._dirty |= {"tests", "devices", "specs"}
            text = f"{i18n.tl('ev.failed') if failed else i18n.tl('status.done')} {robots.act_for_tool(tool, tool_input, root)}"
            gone = self._deleting.pop(use_id, None) if use_id else None
            if gone is not None:
                text = self._shred(agent, gone, failed, payload.get("tool_response"), at)
            if agent["kind"] == "main" and use_id and session.get("haltOn") == use_id:
                self._halt(session, agent, at)   # the call the stop was handed out at has run: the turn ended there
        elif kind == "PermissionRequest" and tool == QUESTION_TOOL:
            # A question, not a permission (permissions.NOT_PERMISSIONS): the robot stays "質問に回答待ち" from its
            # PreToolUse, and nothing goes on the permission board.
            cat = "perm"
            text = i18n.tl("ev.question_permission")
        elif kind == "PermissionRequest":
            # No tool_use_id here: take the newest open call of the same tool
            # (parallel calls are real: Bash and ToolSearch overlapped in P0).
            opened = self._open.get(agent["id"]) or []
            same = [u for u in opened if self._open_tool.get(u) == tool]
            if same:
                self._asking[agent["id"]] = same[-1]
            self.perms.from_hook(sid, agent["id"], tool or "?", tool_input, self._asking.get(agent["id"]),
                                 payload.get("permission_suggestions"), at)
            self._dirty.add("perms")
            self._status(session, "waiting", at, "permission prompt")
            self._set(agent, at, "waiting", f"{perm_wait()}{robots.act_for_tool(tool or '?', tool_input, root)}")
            cat = "perm"
            text = agent["act"]
        elif kind == "PermissionDenied":
            denied_id = use_id or self._asking.get(agent["id"])
            # fired only by auto mode (hooks reference): a card that offers to tell the session to go on
            if self.denials.add(sid, agent["id"], use_id, tool or "?", tool_input, _s(payload.get("reason")) or "", at, "hook"):
                self._dirty.add("denials")
            if self.perms.tool_finished(sid, denied_id, False, at):
                self._dirty.add("perms")
            self._settle_asking(agent["id"])
            self._status(session, "busy", at)
            self._set(agent, at, "idle", i18n.tl("act.denied", tool=tool or '').strip())
            cat = "perm"
            text = agent["act"]
        elif kind == "Notification":
            ntype = _s(payload.get("notification_type")) or ""
            if ntype == "permission_prompt":
                self._status(session, "waiting", at, "permission prompt")
                self._set(agent, at, "waiting")
            elif ntype == "idle_prompt":
                self._status(session, "idle", at)
                if agent["state"] == "waiting":
                    self._set(agent, at, "idle", i18n.tl("status.idle"))
                # 入力待ち (ticket 2026-10-20-jui-viz-3d-waiting-kinds-question-permission-input): a mark over the main
                # robot, not a state; from this until the session moves again (INPUT_WAIT_ENDS). A subagent's does not
                # (the page does not ring it either, notifyIdle)
                if not aid:
                    session["inputWaitAt"] = at
                    self._dirty.add("sessions")
            text = i18n.tl("ev.notification", kind=ntype, message=_head(payload.get('message'), 120) or '').strip()
        elif kind == "SubagentStart":
            self._set(agent, at, "idle", i18n.tl("act.start_as", agent=agent_type or '').strip())
            self._skill_forked_to(sid, agent, at)
            text = i18n.tl("ev.subagent.in", agent=agent_type or aid)
        elif kind == "SubagentStop":
            message = _head(payload.get("last_assistant_message"), MESSAGE_MAX)
            self._set(agent, at, "done", i18n.tl("status.done"), lastMessage=message, leftAt=at, skill=None)
            self._until[agent["id"]] = (at + SUBAGENT_LINGER_MS, "gone")
            text = i18n.tl("ev.subagent.out", agent=agent_type or aid)
        elif kind in ("TaskCreated", "TaskCompleted"):
            if kind == "TaskCreated":
                self.tasks.created(sid, payload, agent["id"], at)
            else:
                self.tasks.completed(sid, payload, at)
            self._dirty.add("tasks")
            subject = _head(payload.get("task_subject"), 120) or ""
            if kind == "TaskCreated":
                self._set(agent, at, "carry", i18n.tl("act.task", subject=subject))
                self._until[agent["id"]] = (at + CARRY_MS, "idle")
            else:
                self._set(agent, at, "done", i18n.tl("act.task.done", subject=subject))
                self._until[agent["id"]] = (at + DONE_TO_IDLE_MS, "idle")
            cat = "task"
            text = f"{i18n.tl('ev.task.created') if kind == 'TaskCreated' else i18n.tl('ev.task.done')} {subject}"
        elif kind in ("Stop", "StopFailure"):
            background = payload.get("background_tasks")
            busy = isinstance(background, list) and len(background) > 0
            if agent["kind"] == "main" and session.pop("stopAt", None) is not None:   # the turn ended before any boundary
                self._dirty.add("sessions")
                self.state.add_event({"at": at, "sessionId": sid, "agentId": agent["id"], "kind": "StopMissed", "cat": "perm",
                                      "text": i18n.tl("ev.stop.missed", label=session["label"])})
            self._turn_over(session, agent, at, busy, _head(payload.get("last_assistant_message"), MESSAGE_MAX),
                            kind == "StopFailure")
            text = i18n.tl("ev.stop.failed") if kind == "StopFailure" else i18n.tl("ev.stop")
        elif kind == "CwdChanged" and cwd:
            self._move(session, cwd, at)
            self._set(agent, at, "carry", i18n.tl("act.move", path=tilde(cwd)))
            self._until[agent["id"]] = (at + CARRY_MS, "idle")
            text = i18n.tl("act.move", path=tilde(cwd))
        elif kind in ("PreCompact", "PostCompact"):
            self._set(agent, at, act=i18n.tl("act.compacting") if kind == "PreCompact" else agent["act"])
            text = i18n.tl("act.compacting") if kind == "PreCompact" else i18n.tl("ev.compacted")

        event = {
            "at": at, "sessionId": sid, "agentId": agent["id"], "kind": kind, "cat": cat,
            "text": robots._clip(text, 200),
        }
        if tool:
            event["tool"] = tool
        if kind == "Notification" and _s(payload.get("notification_type")):   # the page rings idle_prompt (2.3.7)
            event["ntype"] = _head(payload.get("notification_type"), 40)
        if tool_input:
            event["detail"] = clip_strings(tool_input, self.tool_input_max)
        return self.state.add_event(event)

    def _turn_over(self, session: dict, agent: dict, at: int, busy: bool, message: str | None, failed: bool) -> None:
        """The robot's turn has ended: by its Stop / StopFailure hook, or by the page's 停止 (no Stop hook comes then)."""
        sid = session["id"]
        if agent["kind"] == "main":
            self.perms.session_stopped(sid, at)
            self._dirty.add("perms")
            if self.questions.session_stopped(sid, at):
                self._dirty.add("questions")
            self.tasks.turn_ended(sid, at, background=busy, failed=failed)
            self._dirty.add("tasks")
        self._status(session, "busy" if busy else "idle", at)
        self._clear_open(agent["id"])
        if not busy and agent["kind"] == "main":
            # An interrupted subagent sends no SubagentStop; with nothing in
            # the background, none of this session's subagents is still working.
            for sub in [a for a in self.agents.values() if a["sessionId"] == sid and a["kind"] == "sub" and "leftAt" not in a]:
                self._clear_open(sub["id"])
                self._set(sub, at, "done", i18n.tl("status.done"), leftAt=at)
                self._until[sub["id"]] = (at + SUBAGENT_LINGER_MS, "gone")
        if busy and agent["kind"] == "main":
            # waiting on background work: lit, at its desk watching the screen, until the work ends
            session["background"] = {"since": at}
            self._dirty.add("sessions")
            self._set(agent, at, "background", i18n.tl("act.background"), lastMessage=message)
        else:
            if agent["kind"] == "main":
                self._background_off(session, at, touch_agent=False)
            self._set(agent, at, "done", i18n.tl("act.background") if busy else i18n.tl("status.done"), lastMessage=message)
            self._until[agent["id"]] = (at + DONE_TO_IDLE_MS, "idle")
        if agent["kind"] == "main":
            self._skill_ended(sid, at)   # the turn is over: an inline skill with it

    # ---------------------------------------------------------------- calls (SendMessage, 10-18)

    def _resolve_peer(self, to: str) -> str | None:
        """A SendMessage's `to` -> a session id here: a name (`name [ref]`) or a `uds:` socket address. A socket
        no list row named (an old row, a list not read yet) is tried by the pid in its file name
        (``/tmp/cc-socks/<pid>.sock``) against the pids the agents list and the session files gave."""
        if to.startswith("uds:"):
            path = to[len("uds:"):]
            sid = self._peer_socks.get(path)
            m = None if sid else re.search(r"/([0-9]{1,9})\.sock$", path)
            return sid or (self.pid_to_session.get(int(m.group(1))) if m else None)
        return self._peer_names.get(peer_name(to))

    def _dial(self, session: dict, agent: dict, to: str, use_id: str | None, at: int) -> None:
        to_sid = self._resolve_peer(to)
        if to_sid == session["id"] or (to_sid and to_sid not in self.sessions):
            to_sid = None
        self.calls.dial(use_id, agent["id"], session["id"], self._session_names.get(session["id"]),
                        peer_name(to)[:120], to_sid, at)
        self._dirty.add("calls")

    def _call_records(self, sid: str, records: list, at: int) -> None:
        """What the receiver's transcript said about cross-session messages (calls.record_event). The call moves
        when the server reads it (``at``): a record's own time can be behind this clock, and the ring limit and how
        long a picked-up call shows must not start in the past. The record's time is kept as information."""
        for kind, name, when in records:
            if kind == "ring":
                from_sid = self._peer_names.get(name)
                changed = self.calls.ring(sid, name, from_sid, from_sid, at, when)
            elif kind == "answer":
                changed = self.calls.pick_up(sid, name, at, when)
            else:
                changed = self.calls.hang_up(sid, name, at)
            if changed:
                self._dirty.add("calls")

    def _clear_open(self, aid: str) -> None:
        for use_id in self._open.pop(aid, []):
            self._open_tool.pop(use_id, None)
        self._asking.pop(aid, None)

    # ---------------------------------------------------------------- a skill in use (the spirit, 2.3.16)

    def _skill_started(self, session: dict, agent: dict, tool_input: dict, use_id: str | None, at: int) -> None:
        """The session called the Skill tool: its robot carries the skill (a skill named otherwise than SKILL_NAME is
        none). It replaces the skill that robot held; a forked skill already in a subagent goes on until its own
        result. The call waits SKILL_FORK_MS for a subagent (two calls at once: two subagents, oldest first)."""
        name = tool_input.get("skill")
        if not isinstance(name, str) or not SKILL_NAME.fullmatch(name):
            return
        skill = {"name": name, "since": at, **({"useId": use_id} if use_id else {})}
        self._set(agent, at, skill=skill)
        waiting = [c for c in self._skill_called.get(session["id"], []) if at - c[0] <= SKILL_FORK_MS]
        self._skill_called[session["id"]] = waiting + [(at, agent["id"], skill)]

    def _skill_forked_to(self, sid: str, sub: dict, at: int) -> None:
        """A subagent started within SKILL_FORK_MS of the session's Skill call: the skill runs there (forked), so the
        skill moves from the calling robot to it."""
        waiting = [c for c in self._skill_called.get(sid, []) if at - c[0] <= SKILL_FORK_MS]
        if not waiting:
            self._skill_called.pop(sid, None)
            return
        _when, caller_id, skill = waiting.pop(0)
        self._skill_called[sid] = waiting
        caller = self.agents.get(caller_id)
        if caller is None or caller["id"] == sub["id"]:
            return
        if caller.get("skill") is skill:   # the caller still holds it (not replaced by a later call)
            self._set(caller, at, skill=None)
        self._set(sub, at, skill={**skill, "forked": True})

    def _skill_ended(self, sid: str, at: int, use_id: str | None = None) -> None:
        """The skills held by the session's robots end (only the one its call started, given ``use_id``)."""
        for agent in [a for a in self.agents.values() if a["sessionId"] == sid and a.get("skill")]:
            if use_id is None or agent["skill"].get("useId") == use_id:
                self._set(agent, at, skill=None)
        if use_id is None:
            self._skill_called.pop(sid, None)

    def _settle_asking(self, aid: str) -> None:
        use_id = self._asking.pop(aid, None)
        opened = self._open.get(aid)
        if use_id and opened and use_id in opened:
            opened.remove(use_id)

    # ---------------------------------------------------------------- other sources

    def apply_agents_list(self, items: list, at: int) -> None:
        """Rows of ``claude agents --json``: creates sessions no hook has named yet."""
        for row in items:
            if not isinstance(row, dict):
                continue
            sid = _s(row.get("sessionId"))
            if sid is None:
                continue
            session = self._session(sid, _s(row.get("cwd")), at)
            self._find_since(session, _s(row.get("cwd")), None)
            self._agents_since(session, row, at)
            status = row.get("status")
            if status in ("busy", "idle", "waiting"):
                waiting_for = _s(row.get("waitingFor")) if status == "waiting" else None
                self._status(session, status, at, waiting_for)
            if isinstance(row.get("pid"), int):
                self.pid_to_session[row["pid"]] = sid
                proc = (row["pid"], row.get("procStart"), _s(row.get("entrypoint")))
                if self.session_proc.get(sid) != proc:
                    self.session_proc[sid] = proc
                    self._dirty.add("sessions")
            entry = _s(row.get("entrypoint"))
            if entry and session.get("client") != clockout.client_of(entry):
                session["client"] = clockout.client_of(entry)   # terminal / vscode / desktop / other: 退勤 is terminal only
                self._dirty.add("sessions")
            name = _s(row.get("name"))
            if name:   # the name a SendMessage's `to` uses (changes on a restart: the newest row wins)
                old = self._session_names.get(sid)
                if old and old != name and self._peer_names.get(old) == sid:
                    del self._peer_names[old]
                self._peer_names[name], self._session_names[sid] = sid, name
            sock = _s(row.get("messagingSocketPath"))
            if sock:
                self._peer_socks[sock] = sid
            if name and session.get("title") != _head(name, 120):   # a /rename shows: the newest row's name wins
                session["title"] = _head(name, 120)
                self._dirty.add("sessions")

    # ---------------------------------------------------------------- waiting on background work (10-18)

    def _background_off(self, session: dict, at: int, touch_agent: bool = True) -> None:
        if session.pop("background", None) is None:
            return
        self._dirty.add("sessions")
        # the turn that was waiting on the work is done with it (the card and the lamp agree; the independent review, 10-18)
        self.tasks.turn_ended(session["id"], at, background=False, failed=False)
        self._dirty.add("tasks")
        agent = self.agents.get(session["id"])
        if touch_agent and agent and agent["state"] == "background":
            self._set(agent, at, "idle", i18n.tl("status.idle"))

    def background_pids(self) -> dict[str, int]:
        """Sessions waiting on background work whose process is known: session id -> pid (the newest)."""
        want = {sid for sid, s in self.sessions.items() if s.get("background")}
        return {sid: pid for pid, sid in self.pid_to_session.items() if sid in want}

    def check_background(self, rows: list | None, at: int) -> None:
        """A ps snapshot (sources/processes.py): a session with no background shell left under its process, and no
        subagent still at work, is done waiting."""
        if rows is None:
            return
        for sid, pid in self.background_pids().items():
            session = self.sessions[sid]
            session["background"]["checkedAt"] = at
            shells = processes.background_shells(rows, pid)
            subs = any(a["sessionId"] == sid and a["kind"] == "sub" and "leftAt" not in a for a in self.agents.values())
            if not shells and not subs:
                self._background_off(session, at)

    def _background_cap(self, at: int) -> None:
        watched = self.background_pids()
        for sid, session in self.sessions.items():
            bg = session.get("background")
            if not bg:
                continue
            seen = bg.get("checkedAt")
            unwatched = sid not in watched or seen is None or at - seen > BACKGROUND_UNWATCHED_MS
            if unwatched and at - bg["since"] >= BACKGROUND_CAP_MS:
                self._background_off(session, at)

    def apply_session_file(self, data: dict, at: int) -> None:
        """~/.claude/sessions/<pid>.json (never a .key file)."""
        self.apply_agents_list([data], at)

    # ---------------------------------------------------------------- relay channel (08 §2)

    def channel_hello(self, ppid, cwd, session_id, at: int, accepts=None, via=None) -> str:
        """Register a channel; find its session by id, by the parent pid, or by a unique cwd."""
        sid = session_id if isinstance(session_id, str) and session_id in self.sessions else None
        if sid is None and isinstance(ppid, int):
            sid = self.pid_to_session.get(ppid)
        if sid is None and isinstance(cwd, str):
            relay = self.perms.relay_sessions()
            same = [s for s, v in self.sessions.items() if v["cwd"] == tilde(cwd) and v["status"] != "ended" and s not in relay]
            sid = same[0] if len(same) == 1 else None
        prompts = isinstance(accepts, list) and "prompt" in accepts   # jui-viz 1.2.0+ (channel.py VERSION 2)
        channel = self.perms.hello(sid, at, prompts, via if via in ("plugin", "mcp") else None)
        self._dirty.add("sessions")
        return channel.id

    def launch_of(self, sid: str) -> str:
        """Why this session can or cannot take a prompt from the page (a key of launch.REASONS): its process's argv,
        its entrypoint, and how its jui-viz channel is connected."""
        proc = self.session_proc.get(sid)
        if proc is None:
            return "unreadable"
        channel = self.perms.prompt_channel(sid)
        return launch.classify(self._argv_of(proc), proc[2], channel.via if channel else None)

    def _argv_of(self, proc: tuple) -> list | None:
        """The argv of a session's process, read once and kept while (pid, procStart) is the same. A read that failed is
        not kept: it is tried again at a later publish or send, ARGV_RETRY_FIRST s after, the wait doubling up to
        ARGV_RETRY_MAX s (never every frame). Once a failure was kept, and the session stayed "unreadable" — prompts
        refused — until viz restarted (the independent review, 10-19)."""
        if proc[2] in launch.IDE_ENTRYPOINTS:
            return None                      # told by its entrypoint; nothing to read
        if proc in self._argv:
            return self._argv[proc]
        now = self.clock()
        due, wait = self._argv_retry.get(proc, (now, ARGV_RETRY_FIRST))
        if now < due:
            return None
        argv = self.read_argv(proc[0])
        if argv is None:
            self._argv_retry[proc] = (now + wait, min(wait * 2, ARGV_RETRY_MAX))
            return None
        self._argv_retry.pop(proc, None)
        self._argv[proc] = argv
        return argv

    def send_prompt(self, sid: str, text: str, at: int, attached: list[dict] | None = None) -> tuple[int, str] | None:
        """A prompt typed in the page for this session (POST /api/prompt, after its checks): queued for that session's
        channel only, and the event log gets when, to whom and the first PROMPT_HEAD characters — never the whole
        text, which lives only in the channel's queue until its next poll. ``attached`` (attachments.Attachments.take)
        adds one line per file with its absolute path, which the session opens with Read. Returns None, or
        (HTTP status, why)."""
        refused = self.prompt_refusal(sid)
        if refused is not None:
            return refused
        session = self.sessions[sid]
        channel = self.perms.prompt_channel(sid)
        if len(channel.inbox) >= PROMPTS_QUEUED_MAX:
            return 429, "earlier prompts have not been taken yet"
        lines = [attachment_line(a) for a in attached or []]
        full = "\n".join([text.rstrip(), *lines]).strip() if lines else text
        channel.inbox.append({"text": full, "at": at})
        head = " ".join(text.split()) or i18n.tl("ev.attachments", n=len(lines))
        head = head if len(head) <= PROMPT_HEAD else head[: PROMPT_HEAD - 1] + "…"
        extra = i18n.tl("ev.attachments.paren", n=len(lines)) if lines and text.strip() else ""
        self.state.add_event({"at": at, "sessionId": sid, "agentId": sid, "kind": "PromptSent", "cat": "perm",
                              "text": i18n.tl("ev.prompt.sent", label=session['label'], head=head, extra=extra)})
        return None

    def prompt_refusal(self, sid: str) -> tuple[int, str] | None:
        """Why a prompt (or an attachment for one) cannot go to this session now, or None."""
        session = self.sessions.get(sid)
        if session is None or session["status"] == "ended":
            return 404, "no such session"
        if sid not in self.perms.relay_sessions():
            return 409, "this session has no relay (relay: false)"
        channel = self.perms.prompt_channel(sid)
        if channel is None:
            return 409, "this session's jui-viz plugin is older than 1.2.0 and cannot receive prompts"
        why = self.launch_of(sid)
        if not launch.REASONS[why][0]:
            # The CLI drops a channel's text unless the channel was named at launch (2.3.4): refuse here, so the
            # page never says "sent" for a prompt that cannot arrive.
            return 409, f"this session was not started with the channel named ({why}): {launch.START_DEV}"
        return None

    # ---------------------------------------------------------------- 停止 (the page's stop button, jui-viz 1.3.0)

    def request_stop(self, sid: str, at: int, cancel: bool = False) -> tuple[int, str] | None:
        """The page's 停止 for this session (POST /api/stop, after prompt_checks), or its 取り消し (``cancel``). The
        request waits in session["stopAt"] for the session's next --stop hook (hook_stop). A Stop, a new prompt or the
        session's end takes it away. A turn being stopped already (stopTurn) is not asked again. Returns None, or (HTTP
        status, why)."""
        session = self.sessions.get(sid)
        if session is None or session["status"] == "ended":
            return 404, "no such session"
        if cancel:
            if session.pop("stopAt", None) is None:
                return 409, "no stop is waiting for this session"
            self._dirty.add("sessions")
            self.state.add_event({"at": at, "sessionId": sid, "agentId": sid, "kind": "StopCancelled", "cat": "perm",
                                  "text": i18n.tl("ev.stop.cancelled", label=session["label"])})
            return None
        if session["status"] not in ("busy", "waiting"):
            return 409, "this session is not working"
        if "stopAt" in session or session.get("stopTurn"):
            return None   # asked already (or handed out, this turn): the first press stands
        session["stopAt"] = at
        self._dirty.add("sessions")
        self.state.add_event({"at": at, "sessionId": sid, "agentId": sid, "kind": "StopAsked", "cat": "perm",
                              "text": i18n.tl("ev.stop.asked", label=session["label"])})
        return None

    def hook_stop(self, payload: dict, at: int) -> dict:
        """The synchronous --stop hook: {"continue": false, ...} at a tool boundary (PreToolUse / PostToolUse) of a
        turn the page asked to stop, else {}. The main robot's first boundary hands the request out (stopAt becomes
        stopTurn, one Stopped event); every later boundary of that turn is answered the same, since the calls of the
        response already made still run (measured 10-22: from PreToolUse the call still runs; from PostToolUse no
        further model call is made but the response's next call ran, and no Stop hook comes either way). So the server
        ends the turn at each such call's PostToolUse (haltOn), or here at a PostToolUse. A subagent's call is answered
        the same and leaves the request (unmeasured: what a subagent does with it). The turn's stop goes with the next
        prompt, here at its UserPromptSubmit: synchronous, so it comes before the new turn's first tool asks, which the
        async forward of that prompt may not."""
        kind, sid = payload.get("hook_event_name"), _s(payload.get("session_id"))
        session = self.sessions.get(sid) if sid else None
        if kind not in STOP_EVENTS or session is None or session["status"] == "ended":
            return {}
        if not session.get("stopHook"):
            session["stopHook"] = True   # this session's plugin has the hook (1.3.0): the page can say it will stop
            self._dirty.add("sessions")
        if kind not in STOP_ANSWERED:
            if self._new_prompt_unstops(session):
                self._dirty.add("sessions")
            return {}
        if "stopAt" not in session and not session.get("stopTurn"):
            return {}
        answer = {"continue": False, "stopReason": i18n.tl("stop.reason")}
        if _s(payload.get("agent_id")):
            return answer
        agent = self._main(sid, at)
        if "stopAt" in session:
            del session["stopAt"]
            session["stopTurn"] = True
            session["stoppedAt"] = at
            self._dirty.add("sessions")
            self.state.add_event({"at": at, "sessionId": sid, "agentId": agent["id"], "kind": "Stopped", "cat": "perm",
                                  "text": i18n.tl("ev.stop.done", label=session["label"])})
        use_id = _s(payload.get("tool_use_id"))
        if use_id and (kind == "PreToolUse" or use_id in self._open_tool):
            session["haltOn"] = use_id   # the call runs (or its PostToolUse is still on the way): the turn ends after it
        else:
            self._halt(session, agent, at)
        return answer

    @staticmethod
    def _new_prompt_unstops(session: dict) -> bool:
        """A new prompt: a stop asked for, or handed out in, the last turn never stops this one. Whether any was there."""
        found = [session.pop(k, None) is not None for k in ("stopAt", "stopTurn", "haltOn")]
        return any(found)

    def _halt(self, session: dict, agent: dict, at: int) -> None:
        session.pop("haltOn", None)
        self._turn_over(session, agent, at, False, None, False)
        self._set(agent, at, act=i18n.tl("act.stopped"))   # done, back to idle as after a Stop; it says why

    def channel_request(self, channel_id: str, request: dict, at: int) -> bool:
        ok = self.perms.channel_request(channel_id, request, at)
        if ok:
            self._dirty.add("perms")
        return ok

    def hook_decide(self, payload: dict, at: int) -> dict | None:
        """The synchronous PermissionRequest hook: the card it waits on (same card
        as the async forward's), or None if the payload is not a permission request."""
        if payload.get("hook_event_name") != "PermissionRequest" or not _s(payload.get("session_id")):
            return None
        sid = payload["session_id"]
        self._session(sid, _s(payload.get("cwd")), at)
        aid = _s(payload.get("agent_id"))
        agent = self._sub(sid, aid, _s(payload.get("agent_type")), at) if aid else self._main(sid, at)
        tool = _s(payload.get("tool_name")) or "?"
        tool_input = payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {}
        opened = self._open.get(agent["id"]) or []
        same = [u for u in opened if self._open_tool.get(u) == tool]
        card = self.perms.from_hook(sid, agent["id"], tool, tool_input, same[-1] if same else None,
                                    payload.get("permission_suggestions"), at, source="decide")
        self._dirty.add("perms")
        return card

    def hook_waiting(self, card: dict, future) -> None:
        """A --decide hook now waits on this card: the page must learn that it can answer."""
        self.perms.hook_waiting(card, future)
        self._dirty.add("perms")

    def hook_gave_up(self, card: dict) -> None:
        self.perms.hook_gave_up(card)
        self._dirty.add("perms")

    # ---------------------------------------------------------------- questions (AskUserQuestion, 10-18)

    def hook_ask(self, payload: dict, at: int) -> dict | None:
        """The synchronous PreToolUse hook of AskUserQuestion (forward.py --ask): the card it waits on."""
        if (payload.get("hook_event_name") != "PreToolUse" or payload.get("tool_name") != QUESTION_TOOL
                or not _s(payload.get("session_id"))):
            return None
        sid = payload["session_id"]
        self._session(sid, _s(payload.get("cwd")), at)
        aid = _s(payload.get("agent_id"))
        agent = self._sub(sid, aid, _s(payload.get("agent_type")), at) if aid else self._main(sid, at)
        tool_input = payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {}
        card = self.questions.from_hook(sid, agent["id"], tool_input, _s(payload.get("tool_use_id")), at)
        self._dirty.add("questions")
        return card

    def question_waiting(self, card: dict, future, until: int, latest: int) -> None:
        self.questions.hook_waiting(card, future, until, latest)
        self._dirty.add("questions")

    def hold_question(self, card_id: str, at: int, wait_ms: int) -> str | None:
        error = self.questions.hold(card_id, at, wait_ms)
        self._dirty.add("questions")
        return error

    def release_question(self, card_id: str, at: int) -> str | None:
        error = self.questions.release(card_id, at)
        if error is None:
            card = self.questions.cards[card_id]
            self.state.add_event({"at": at, "sessionId": card["sessionId"], "agentId": card["agentId"], "kind": "QuestionReleased",
                                  "cat": "perm", "text": i18n.tl("ev.question.released")})
            self._dirty.add("questions")
        return error

    def question_gave_up(self, card: dict, reason: str | None = None, at: int | None = None) -> None:
        self.questions.hook_gave_up(card, reason, at)
        self._dirty.add("questions")

    def answer_question(self, card_id: str, picks, at: int) -> str | None:
        error = self.questions.answer(card_id, picks, at)
        if error is None:
            card = self.questions.cards[card_id]
            self.state.add_event({"at": at, "sessionId": card["sessionId"], "agentId": card["agentId"], "kind": "QuestionAnswered",
                                  "cat": "perm", "text": i18n.tl("ev.question.answered", summary=_question_summary(card))})
            self._dirty.add("questions")
        return error

    def decide(self, perm_id: str, behavior: str, at: int, always=None, reason=None) -> str | None:
        error = self.perms.decide(perm_id, behavior, at, always, reason)
        if error is None:
            card = self.perms.perms[perm_id]
            extra = i18n.tl("ev.sent.always") if card.get("sentRules") else i18n.tl("ev.sent.reason") if card.get("sentReason") else ""
            self.state.add_event({
                "at": at, "sessionId": card["sessionId"], "agentId": card["agentId"], "kind": "PermissionAnswered",
                "cat": "perm", "text": i18n.tl("ev.sent.allow" if behavior == "allow" else "ev.sent.deny", extra=extra, summary=card['summary']),
            })
            self._dirty.add("perms")
        return error

    # ---------------------------------------------------------------- devices and test progress (P7)

    def apply_devices(self, devices: list[dict]) -> None:
        if devices != self.devices:
            self.devices = devices
            self._dirty.add("devices")
            # a test that started before its device was seen (the command booted it, or the first scan had not run)
            for test in self.running_tests():
                if not test.get("deviceId"):
                    found = devices_mod.device_for_command(test.get("command", ""), devices)
                    if found:
                        test["deviceId"] = found
                        self._dirty.add("tests")
        elif self.devices_slice(self.wall_ms()) != self.state.slices.get("devices"):
            self._dirty.add("devices")   # a command's estimate went out of date (COMMAND_KEPT_MS), a robot left

    def apply_mock(self, project_id: str, info: dict) -> None:
        project = self.rooms.projects.get(project_id)
        if project is not None and project.get("mock") != info:
            project["mock"] = info
            self._dirty.add("projects")

    def _device_named(self, command: str, agent: dict, at: int) -> None:
        for dev_id in devices_mod.ids_in_command(command, self.devices):
            self.device_cmds.pop(dev_id, None)
            self.device_cmds[dev_id] = (agent["id"], at)
            if any(d["id"] == dev_id for d in self.devices):
                self._dirty.add("devices")
        for old in list(self.device_cmds)[:-DEVICE_CMDS_KEPT]:
            del self.device_cmds[old]

    def apply_device_procs(self, rows: list | None) -> None:
        """A ps snapshot taken with the device scan while a device is up: which sessions have a process naming it."""
        if rows is None:
            return
        found = devices_mod.sessions_using(rows, self.devices, self.pid_to_session) if self.devices else {}
        if found != self.device_procs:
            self.device_procs = found
            self._dirty.add("devices")

    def apply_machine(self, reading: dict) -> None:
        if reading != self.machine:
            self.machine = reading
            self._dirty.add("machine")

    def devices_slice(self, at: int) -> list[dict]:
        """The devices, each with who uses it when that can be told, and how it was told (strongest first)."""
        busy = {t["deviceId"]: t["agentId"] for t in self.running_tests() if t.get("deviceId")}
        here = lambda aid: aid in self.agents and "leftAt" not in self.agents[aid]   # a robot gone or walking out: nobody
        out = []
        for dev in self.devices:
            row = dict(dev)
            used = None
            if dev["id"] in busy:
                row["busyBy"] = busy[dev["id"]]   # the test pane's field, as before
            if dev["id"] in busy and here(busy[dev["id"]]):
                used = {"agentId": busy[dev["id"]], "how": "test"}
            elif any(here(sid) for sid in self.device_procs.get(dev["id"], [])):
                sids = [sid for sid in self.device_procs[dev["id"]] if here(sid)]
                used = {"agentId": sids[0], "how": "process", "others": sids[1:]}
            elif dev["id"] in self.device_cmds:
                agent_id, when = self.device_cmds[dev["id"]]
                if here(agent_id) and at - when <= devices_mod.COMMAND_KEPT_MS:
                    used = {"agentId": agent_id, "how": "command", "at": when}
            if used:
                row["usedBy"] = used
            out.append(row)
        return out

    def running_tests(self, platform: str | None = None) -> list[dict]:
        return [r for r in self.tests.values() if r["status"] == "running" and (platform is None or r["platform"] == platform)]

    def _runner_counts(self, test: dict) -> tuple[int, int] | None:
        """jsonui-test-runner's own run_end counts over a command's runs, summed; None before any run_end."""
        ended = [self.progress.runs[r] for r in _runs_of(test) if r in self.progress.runs and "failed" in self.progress.runs[r]]
        if not ended:
            return None
        return sum(int(r.get("passed") or 0) for r in ended), sum(int(r.get("failed") or 0) for r in ended)

    def _test_decide(self, test: dict) -> None:
        """A finished command's head: the runner's records, else what its output said (robots.test_verdict's order)."""
        got = self._test_from_output.get(test["id"])
        if got is None:
            return
        runner = self._runner_counts(test)
        if runner is not None:
            got = robots.test_verdict("", False, runner)
        test["status"], test["verdictFrom"] = got["status"], got["from"]
        if got["summary"]:
            test["summary"] = got["summary"]   # a command with runner records: the tick puts its cases' counts over it (_run_cases)
        self._dirty |= {"tests", "devices", "specs"}

    def apply_progress(self, rec, source: str, device_id: str | None, at: int) -> bool:
        run = self.progress.add(rec, source, device_id)
        if run is None:
            return False
        # Tie the runner's run to the test command that started it: same
        # platform, running, started before the record (and on that device when known).
        # One command runs many: each driver starts a run per test file (xcodebuild, gradle and playwright
        # alike), so a command keeps every run tied to it (progressRuns); progressRun stays its first.
        target = next((t for t in self.tests.values() if run["run"] in _runs_of(t)), None)
        if target is None:
            candidates = [t for t in self.running_tests(run["platform"]) if t["startedAt"] <= run["startedAt"] + 5_000
                          and (not run.get("deviceId") or t.get("deviceId") in (None, run.get("deviceId")))]
            if len(candidates) == 1:
                target = candidates[0]
                target.setdefault("progressRun", run["run"])
                target.setdefault("progressRuns", []).append(run["run"])
        if target is not None:
            if target["status"] != "running" and rec.get("event") == "run_end":
                self._test_decide(target)   # the runner's own word came after the command ended
            self._cases_due.add(target["id"])  # tick rebuilds its cases once: each record would go over every run again
            project = self.jsonui.get(target["projectId"])
            if project is not None:
                live = self.live_cases.setdefault(project.project_id, {})
                for case in run["cases"].values():
                    key = (self._file_key(project, case["file"]), case["test"], case["name"])
                    for spec_id in self._specs_of_file(project, case["file"]):
                        live.setdefault(spec_id, {})[key] = (run["updatedAt"], case["status"])
                self._merge_due.add(project.project_id)
        self._dirty.add("tests")
        return True

    def _run_cases(self, target: dict) -> None:
        """A test command's cases (a robot's card and the test pane): the live progress of every run it started
        (one per test file), and the saved result files of the same runs (B's rows, sources/test_results.py) —
        tied by run id only, so only runs this server saw start. Per (file, test, case) the newer outcome wins,
        so a case seen live and then saved counts once."""
        rids = _runs_of(target)
        runs = [self.progress.runs[r] for r in rids if r in self.progress.runs]
        saved = [r for rid in rids for r in self._saved_by_run.get(rid, ())]
        merged: dict[tuple, tuple[int, str, str]] = {}
        for run in runs:
            for c in run["cases"].values():
                merged[(c["file"], c["test"], c["name"], len(merged))] = (run["updatedAt"], c["status"], c["name"])
        if saved:
            merged = {k[:3]: v for k, v in merged.items()}  # one row per (file, test, case) once files are merged in
            for r in saved:
                key = (r["file"], r["test"], r["case"])
                if key not in merged or merged[key][0] <= r["t"]:
                    merged[key] = (r["t"], r["status"], r["case"])
            target["savedAt"] = max(r["t"] for r in saved)
        else:
            target.pop("savedAt", None)
        target["cases"] = [{"name": name, "status": status} for _, status, name in merged.values()]
        done = [c for c in target["cases"] if c["status"] in ("passed", "failed")]
        if runs or saved:
            target["summary"] = f"{sum(c['status'] == 'passed' for c in done)} passed, {sum(c['status'] == 'failed' for c in done)} failed"

    def _shred(self, agent: dict, gone: dict, failed: bool, response, at: int) -> str:
        """A deletion has run (10-19): the robot's shred (the page walks it to the shredder), its act and the log line.
        ok is False when the hook says it failed or rm / git say there was nothing there: no paper, a puzzled robot."""
        output = f"{response.get('stdout') or ''}\n{response.get('stderr') or ''}" if isinstance(response, dict) else str(response or "")
        ok = not failed and not robots.deletion_failed(output[-20_000:])
        label = robots.deletion_label(gone)
        agent["shred"] = {"at": at, "ok": ok, "label": label, "count": len(gone["targets"]), "folder": gone["folder"], "how": gone["how"]}
        self._set(agent, at, act=robots._clip(i18n.tl("act.shred", label=label) if ok else i18n.tl("act.shred.failed", label=label)))
        self._dirty.add("agents")
        return f"{i18n.tl('ev.deleted') if ok else i18n.tl('ev.not_deleted')} {i18n.tl('ev.deleted.how', label=label, how=gone['how'])}"

    def apply_saved_results(self, rows: list[dict]) -> None:
        """The rows of every saved result file (sources/test_results.py), replacing the previous scan.
        The same scan again (every 5 s while nothing was written) changes nothing and costs nothing."""
        if rows == self.saved_rows:
            return
        self.saved_rows = rows
        self._saved_by_run = {}
        for row in rows:
            if row.get("run"):
                self._saved_by_run.setdefault(row["run"], []).append(row)
        for target in self.tests.values():
            if _runs_of(target):
                self._run_cases(target)
                self._dirty.add("tests")
        for project in self.jsonui.values():
            self._merge_results(project)

    def _forget_ties(self) -> None:
        self._ties, self._file_keys, self._all_test_keys = {}, {}, None

    def _file_key(self, project: JsonUIProject, file: str | None) -> str:
        key = (project.project_id, file or "")
        if key not in self._file_keys:
            self._file_keys[key] = _file_key(project, file)
        return self._file_keys[key]

    def _specs_of_file(self, project: JsonUIProject, file: str) -> list[str]:
        key = (project.project_id, "file", file)
        if key not in self._ties:
            self._ties[key] = project.specs_for_test_file(file)
        return self._ties[key]

    def _run_rooms(self) -> dict[str, frozenset[str]]:
        """Run id -> the rooms of the test commands it is tied to, and the cwds they ran in (hand 1 of _saved_specs)."""
        rooms: dict[str, set[str]] = {}
        for t in self.tests.values():
            for rid in _runs_of(t):
                rooms.setdefault(rid, set()).add(t["projectId"])
                if t["id"] in self._test_cwds:
                    rooms[rid].add("cwd:" + self._test_cwds[t["id"]])
        return {rid: frozenset(r) for rid, r in rooms.items()}

    def flush_results(self) -> None:
        """Merge each project a record or a file change marked, once (tick). A run newly tied to a command
        moves its saved rows (hand 1 of _saved_specs), so every room merges again when the ties changed."""
        for tid in sorted(self._cases_due):
            if tid in self.tests:
                self._run_cases(self.tests[tid])
        self._cases_due.clear()
        ties = self._run_rooms()
        if ties != self._run_rooms_seen:
            self._run_rooms_seen = ties
            self._merge_due.update(self.jsonui)
        for pid in sorted(self._merge_due):
            if pid in self.jsonui:
                self._merge_results(self.jsonui[pid])
        self._merge_due.clear()

    def _saved_specs(self, project: JsonUIProject, row: dict, run_rooms: dict | None = None) -> list[str]:
        """The specs of *project* a saved row belongs to, tied without guessing (design memo ②, 10-18):
        1. its run is one this server saw start from a test command: that command's room;
        2. Android: the app whose config names the row's package as test.artifacts.android.appId;
        3. the one app, among every loaded room, that has the row's test file.
        Anything else is left unattached. iOS has no counterpart of 2 (its app is the runner's id)."""
        file = row.get("file")
        if not file:
            return []
        run_rooms = self._run_rooms() if run_rooms is None else run_rooms
        if row.get("run") and row["run"] in run_rooms:
            # the checkout the command ran in (ticket 2026-10-23-viz-test-tally-and-worktrees): in this room, its own
            # apps; in a worktree this room shows, that worktree's app@branch only
            seen = run_rooms[row["run"]]
            cwds = [Path(c[4:]) for c in seen if c.startswith("cwd:")]
            here = [sid for sid in self._specs_of_file(project, file) if project.project_id in seen
                    and (project.specs[sid].source is None or project.specs[sid].source.base is None)]
            there = [s for s in project.sources if s.base is not None
                     and any(c.is_relative_to(Path(s.checkout["worktree"])) for c in cwds)]
            return here + (project.specs_for_test_file(file, only=there) if there else [])
        key = (project.project_id, file, row["platform"], row.get("app"))
        if key not in self._ties:
            self._ties[key] = self._untied_specs(project, row)
        return self._ties[key]

    def _untied_specs(self, project: JsonUIProject, row: dict) -> list[str]:
        """Hands 2 and 3 of _saved_specs: they read only the loaded rooms' apps and test files."""
        file = row["file"]
        if row["platform"] == "android" and row.get("app"):
            # a result no command of this server ran is the main checkout's: never a linked worktree's
            by_app = [(p, s) for p in self.jsonui.values() for s in p.sources if s.android_app_id == row["app"] and not s.linked]
            if by_app:
                return project.specs_for_test_file(file, only=[s for p, s in by_app if p is project]) \
                    if any(p is project for p, _ in by_app) else []
        owners = [(p, s) for p in self.jsonui.values()
                  for s, _ in p.test_file_matches(file, only=[x for x in p.sources if not x.linked])]
        if len(owners) == 1 and owners[0][0] is project and not self._file_elsewhere(project, file):
            return project.specs_for_test_file(file, only=[owners[0][1]])
        return []

    def _file_elsewhere(self, project: JsonUIProject, file: str) -> bool:
        """Another room has a test file whose path agrees with *file* at least as far as *project*'s does:
        the best match is not unique across rooms, so the row is not tied (hand 3 never guesses)."""
        rules = test_dirs()
        if rules is None:
            return True
        if self._all_test_keys is None:
            self._all_test_keys = {}
            for k in (k for p in self.jsonui.values() for s in p.sources if not s.linked for k in s.test_file_paths.values()):
                self._all_test_keys.setdefault(rules.segments(k)[-1], []).append(k)
        wanted = rules.segments(file)
        return rules.match_test_file(file, self._all_test_keys.get(wanted[-1] if wanted else "", [])) is None

    def _merge_results(self, project: JsonUIProject) -> None:
        merged: dict[str, dict[tuple[str, str, str], tuple[int, str, bool]]] = {}

        def put(spec_id: str, key: tuple[str, str, str], t: int, status: str, saved: bool) -> None:
            cases = merged.setdefault(spec_id, {})
            if key not in cases or cases[key][0] <= t:
                cases[key] = (t, status, saved)

        run_rooms = self._run_rooms()
        for row in self.saved_rows:
            for spec_id in self._saved_specs(project, row, run_rooms):
                put(spec_id, (self._file_key(project, row["file"]), row["test"], row["case"]), row["t"], row["status"], True)
        for spec_id, cases in self.live_cases.get(project.project_id, {}).items():
            for key, (t, status) in cases.items():
                put(spec_id, key, t, status, False)
        results = {}
        for spec_id, cases in merged.items():
            statuses = [status for _, status, _ in cases.values()]
            results[spec_id] = {"passed": statuses.count("passed"), "failed": statuses.count("failed"),
                                "running": "running" in statuses}
            results[spec_id]["lastAt"] = max(t for t, _, _ in cases.values())   # the spec's newest result: it moved on
            saved_at = [t for t, _, saved in cases.values() if saved]
            if saved_at:  # a case shown from a file, not from this server's own run: how old it may be
                results[spec_id]["latest"] = max(saved_at)
        if results != project.test_results:
            project.test_results = results
            self._dirty.add("specs")

    # ---------------------------------------------------------------- time

    def tick(self, at: int) -> None:
        self._now = max(self._now, at)
        self.flush_results()
        if self.perms.tick(at):
            self._dirty |= {"perms", "sessions"}
        if self.questions.tick(at):
            self._dirty.add("questions")
        if self.calls.tick(at):
            self._dirty.add("calls")
        if self.denials.tick(at):
            self._dirty.add("denials")
        self._data_docs_tick(at)
        for sid in self.attachments.due(at):   # an hour after the session ended (a few files: done here)
            try:
                self.attachments.drop(sid)
            except OSError:
                pass
        self._infra_tick(at)
        self._worktrees_tick(at)
        for project in self.jsonui.values():
            for entry in project.specs.values():
                due = [t for t in (entry.by_until, *entry.writing_until.values()) if t and t <= at]
                if due:
                    if entry.by_until and entry.by_until <= at:
                        entry.by, entry.by_until = None, 0
                    entry.writing_until = {k: t for k, t in entry.writing_until.items() if t > at}
                    self._dirty.add("specs")
        for agent in self.agents.values():   # the whistle of a subagent call, over at its fixed length
            if agent.get("whistle") and at >= agent["whistle"]["until"]:
                agent.pop("whistle")
                self._dirty.add("agents")
            if agent.get("skill") and at - agent["skill"]["since"] >= SKILL_MAX_MS:   # an end that never came
                agent.pop("skill")
                self._dirty.add("agents")
        for aid, (due, to) in list(self._until.items()):
            if at < due:
                continue
            self._until.pop(aid, None)
            agent = self.agents.get(aid)
            if agent is None:
                continue
            if to == "gone":
                del self.agents[aid]
                self._open.pop(aid, None)
                self._dirty.add("agents")
            else:
                self._set(agent, at, to)
        for sid, session in list(self.sessions.items()):
            if session["status"] == "ended" and at - session["updatedAt"] >= ENDED_LINGER_MS:
                del self.sessions[sid]
                for aid in [a for a, ag in self.agents.items() if ag["sessionId"] == sid]:
                    del self.agents[aid]
                self.tasks.drop_session(sid)
                self._dirty |= {"sessions", "agents", "tasks"}
            elif session["status"] == "busy":
                # Busy and quiet for a while: the model is thinking. Its own state, not idle with another act — the
                # page drew it as idle (10-18 live check: every hookless session that worked looked asleep).
                agent = self.agents.get(sid)
                if agent and agent["state"] == "idle" and at - agent["updatedAt"] >= THINKING_AFTER_MS:
                    agent["state"], agent["act"] = "thinking", i18n.tl("status.thinking")
                    self._dirty.add("agents")
            else:
                # No longer busy (a hookless session's status comes from `claude agents --json` only): stop thinking.
                agent = self.agents.get(sid)
                if agent and agent["state"] == "thinking":
                    self._set(agent, at, "idle", i18n.tl("status.idle"))
        self._background_cap(at)
        self._heavy(at)

    # ---------------------------------------------------------------- the cardboard box: git push / pull (2.3.4)

    def _git_trip(self, agent: dict, sid: str, cwd: str | None, tool_input: dict, response, use_id: str | None, at: int) -> None:
        """A finished Bash call that pushed or pulled: the robot's trip to the box (agent["git"]), and the amount to
        count afterwards, off the event loop (take_git_jobs / git_counted; gitbox.count_range reads only)."""
        command = tool_input.get("command") if isinstance(tool_input.get("command"), str) else ""
        trip = gitbox.trip_of(command, cwd, response) if command else None
        if trip is None:
            return
        job = trip.pop("_count", None)
        trip.update(id=str(use_id or at), at=at, pending=job is not None)
        trip["label"] = gitbox.label(trip)
        agent["git"] = trip
        self._dirty.add("agents")
        if job is not None:
            self.git_jobs.append((agent["id"], trip["id"], job))
        else:
            self._git_event(agent, sid, trip, at)

    def _git_event(self, agent: dict, sid: str, trip: dict, at: int) -> None:
        self.state.add_event({"at": at, "sessionId": sid, "agentId": agent["id"],
                              "kind": "GitPush" if trip["kind"] == "push" else "GitPull", "cat": "tool", "text": gitbox.label(trip)})

    def take_git_jobs(self) -> list:
        jobs, self.git_jobs = self.git_jobs, []
        return jobs

    def git_counted(self, agent_id: str, trip_id: str, counted: dict | None, at: int) -> None:
        """The amount of a trip, counted in an executor; dropped when the trip was replaced or cleared meanwhile."""
        agent = self.agents.get(agent_id)
        trip = agent.get("git") if agent else None
        if not trip or trip.get("id") != trip_id:
            return
        # a new dict, never the old one changed: the published agents slice copies each agent shallowly, so a trip
        # changed in place was the same object in the slice already sent, compared equal, and was never sent again
        trip = {**trip, "pending": False, **({"counted": counted} if counted else {})}
        trip["label"] = gitbox.label(trip)
        agent["git"] = trip
        self._dirty.add("agents")
        self._git_event(agent, agent["sessionId"], trip, at)

    # ---------------------------------------------------------------- the 応答の履歴 tab (10-18)

    def history(self, agent_id: str, end: int | None = None, stop: int | None = None) -> dict | None:
        """The last turns of one robot's transcript, read now (never kept in a slice), or None. end / stop: further back
        (sources/history.read_tail)."""
        agent = self.agents.get(agent_id)
        if agent is None or self.history_reader is None:
            return None
        sid = agent["sessionId"]
        cwd, given = self._paths.get(sid, (None, None))
        if agent["kind"] == "sub":
            got = self.history_reader(sid, cwd, given, agent_id, self._agent_paths.get(agent_id), end=end, stop=stop)
        else:
            got = self.history_reader(sid, cwd, given, end=end, stop=stop)
        return self._history_peers(got, sid)

    def _history_peers(self, got: dict | None, own: str) -> dict | None:
        """The session on the other end of a SendMessage (its `to`) and of a received message (its sender), when it
        is a session here: the page links the name to that robot (2.3.6). Another machine, the cloud, a session
        that ended, ``main`` and this session itself stay unlinked."""
        if not isinstance(got, dict):
            return got
        for item in got.get("items") or []:
            if item.get("kind") == "tool" and isinstance(item.get("to"), str):
                key, names = "toSession", [item["to"]]
            elif item.get("kind") == "peer":
                key, names = "fromSession", [x for x in (item.get("from"), item.get("fromAddr")) if isinstance(x, str)]
            else:
                continue
            for name in names:
                peer = self._resolve_peer(name)
                if peer and peer != own and peer in self.sessions and self.sessions[peer].get("status") != "ended":
                    item[key] = peer
                    break
        return got

    def history_image(self, agent_id, off, n) -> tuple[int, object]:
        """One picture of the transcript history() reads for this robot (sources/history.image_at): (200, (media,
        bytes)) or (status, reason). The robot names the transcript; off and n name the picture in it."""
        agent = self.agents.get(agent_id) if isinstance(agent_id, str) else None
        image = getattr(self.history_reader, "image", None)
        if agent is None or image is None:
            return 404, "no such image"
        sid = agent["sessionId"]
        cwd, given = self._paths.get(sid, (None, None))
        if agent["kind"] == "sub":
            return image(sid, cwd, given, agent_id, self._agent_paths.get(agent_id), off, n)
        return image(sid, cwd, given, None, None, off, n)

    def history_file(self, agent_id, off, n) -> tuple[int, object]:
        """One picture a SendUserFile call of this robot's transcript sent: its copy taken when the call was made
        (viz/sent_copies.py), else read from its path (sources/history.sent_file_at) and copied then. (200, (media,
        bytes)), (404, "gone") or (404, "gone:<why>") when neither is there and the copy could not be taken, or (status,
        reason)."""
        agent = self.agents.get(agent_id) if isinstance(agent_id, str) else None
        sent_file = getattr(self.history_reader, "sent_file", None)
        sent_ref = getattr(self.history_reader, "sent_ref", None)
        if agent is None or sent_file is None:
            return 404, "no such file"
        sid = agent["sessionId"]
        cwd, given = self._paths.get(sid, (None, None))
        where = (sid, cwd, given, agent_id, self._agent_paths.get(agent_id)) if agent["kind"] == "sub" else (sid, cwd, given, None, None)
        ref = sent_ref(*where, off, n) if sent_ref is not None and self.sent_copies is not None else (404, "")
        if ref[0] == 200:
            status, got = self.sent_copies.read(*ref[1])
            if status == 200:
                return status, got
        status, got = sent_file(*where, off, n)
        if ref[0] == 200 and status == 200:
            self.sent_copies.keep(*ref[1], *got)
        elif ref[0] == 200 and status == 404 and got == "gone":
            why = self.sent_copies.read(*ref[1])[1]
            if why:
                return 404, f"gone:{why}"
        return status, got

    def history_reveal(self, agent_id, off, n) -> tuple[int, str]:
        """The path of one file a SendUserFile call of this robot's transcript sent, to show in Finder
        (sources/history.sent_reveal_at): (200, path), (404, "gone"), or (status, reason)."""
        agent = self.agents.get(agent_id) if isinstance(agent_id, str) else None
        sent_reveal = getattr(self.history_reader, "sent_reveal", None)
        if agent is None or sent_reveal is None:
            return 404, "no such file"
        sid = agent["sessionId"]
        cwd, given = self._paths.get(sid, (None, None))
        if agent["kind"] == "sub":
            return sent_reveal(sid, cwd, given, agent_id, self._agent_paths.get(agent_id), off, n)
        return sent_reveal(sid, cwd, given, None, None, off, n)

    def history_tool_reveal(self, agent_id, off, use_id) -> tuple[int, str]:
        """The file a Read / Edit / Write / NotebookEdit call of this robot's transcript names, to show in Finder
        (sources/history.tool_file_reveal_at): (200, path), (404, "gone"), or (status, reason)."""
        agent = self.agents.get(agent_id) if isinstance(agent_id, str) else None
        tool_reveal = getattr(self.history_reader, "tool_reveal", None)
        if agent is None or tool_reveal is None:
            return 404, "no such file"
        sid = agent["sessionId"]
        cwd, given = self._paths.get(sid, (None, None))
        if agent["kind"] == "sub":
            return tool_reveal(sid, cwd, given, agent_id, self._agent_paths.get(agent_id), off, use_id)
        return tool_reveal(sid, cwd, given, None, None, off, use_id)

    # ---------------------------------------------------------------- heavy work (10-18)

    def poll_usage(self, at: int) -> dict:
        """Read what each live session's transcript added (the usage of its assistant records).
        Returns {'bytes', 'assistant', 'usage', 'bad'} over all of them, for the source's status."""
        total = {"bytes": 0, "assistant": 0, "usage": 0, "bad": 0}
        if self.transcript_path is None:
            return total
        from .sources.transcripts import UsageTail
        for sid, session in self.sessions.items():
            if session["status"] == "ended":
                self._tails.pop(sid, None)
                continue
            tail = self._tails.get(sid)
            if tail is None:
                cwd, given = self._paths.get(sid, (None, None))
                path = self.transcript_path(sid, cwd, given)
                if path is None:
                    continue
                tail = self._tails[sid] = UsageTail(path)
            got = tail.read()
            for k in ("bytes", "assistant", "bad"):
                total[k] += got[k]
            total["usage"] += len(got["usage"])
            if got.get("calls"):
                self._call_records(sid, got["calls"], at)
            self._denied_records(sid, sid, got.get("denials"), at)
            if self.denials.reply(sid, got.get("replies"), at):   # the receiver's next response under a sent card
                self._dirty.add("denials")
            self._bill(sid, sid, got.get("bills"), at)
            seen = self._usage_seen.setdefault(sid, {})
            for mid, tokens, when in got["usage"]:
                delta = tokens - seen.get(mid, 0)
                if delta > 0:
                    seen[mid] = tokens
                    self._tokens.setdefault(sid, []).append((when or at, delta))
            if len(seen) > 2_000:                                     # old ids: keep the newest
                for mid in list(seen)[:-1_000]:
                    del seen[mid]
        self._poll_sub_usage(at)
        self._prune_bills(at)
        return total

    def _poll_sub_usage(self, at: int) -> None:
        """Each subagent at work: its own transcript's new responses, billed over its own robot (the main session's
        transcript holds none of them: measured 10-19, no isSidechain record in it)."""
        for aid, agent in self.agents.items():
            key = f"sub:{aid}"
            if agent["kind"] != "sub" or agent.get("leftAt") or self.sessions.get(agent["sessionId"], {}).get("status") == "ended":
                if key in self._tails:
                    self._tails.pop(key, None)
                    self._billed.pop(aid, None)
                continue
            tail = self._tails.get(key)
            if tail is None:
                cwd, given = self._paths.get(agent["sessionId"], (None, None))
                try:
                    path = self.transcript_path(agent["sessionId"], cwd, given, aid, self._agent_paths.get(aid))
                except TypeError:          # a finder that knows no subagents (a test's)
                    path = None
                if path is None:
                    continue
                from .sources.transcripts import UsageTail
                tail = self._tails[key] = UsageTail(path)
            got = tail.read()
            self._bill(aid, agent["sessionId"], got.get("bills"), at)
            self._denied_records(agent["sessionId"], aid, got.get("denials"), at)
        for key in [k for k in self._tails if isinstance(k, str) and k.startswith("sub:") and k[4:] not in self.agents]:
            self._tails.pop(key, None)
            self._billed.pop(key[4:], None)

    def _denied_records(self, sid: str, agent_id: str, got, at: int) -> None:
        """Auto mode denials read from a transcript (sources/transcripts.denial_of): the same cards as the hook's."""
        from .denials import reason_of
        for use_id, tool, tool_input, text, when in got or []:
            if self.denials.add(sid, agent_id, use_id, tool, tool_input, reason_of(text), when or at, "transcript"):
                self._dirty.add("denials")

    def approve_denial(self, card_id: str, at: int) -> tuple[int, str] | None:
        """「実行してよいと伝える」, confirmed on the page: denials.prompt_text(card) goes to that session as a prompt from the
        page (send_prompt, the path of POST /api/prompt). Nothing else: no rule, no setting, no answer to a hook."""
        from .denials import prompt_text
        card = self.denials.find(card_id)
        if card is None:
            return 404, "no such card"
        if card["status"] != "pending":
            return 409, f"this card is {card['status']}"
        refused = self.send_prompt(card["sessionId"], prompt_text(card), at)
        if refused is not None:
            return refused
        self.denials.settle(card_id, "sent", at)
        self._dirty.add("denials")
        return None

    def dismiss_denial(self, card_id: str, at: int) -> tuple[int, str] | None:
        """「そのまま」: the card closes; nothing is sent."""
        if self.denials.settle(card_id, "dismissed", at) is None:
            return (404, "no such card") if self.denials.find(card_id) is None else (409, "already answered")
        self._dirty.add("denials")
        return None

    def _bill(self, agent_id: str, sid: str, got, at: int) -> None:
        """The new responses of one transcript as bills over agent_id's robot: one per message id (the same usage
        written again is not billed again; a usage that grew replaces the bill), priced by the table in use."""
        if not got or self.prices is None:
            return
        seen = self._billed.setdefault(agent_id, {})
        for mid, model, usage, when in got:
            sig = (model, tuple(sorted((k, v) for k, v in usage.items() if isinstance(v, (int, float, str)))))
            if seen.get(mid) == sig:
                continue
            seen[mid] = sig
            tokens = prices.total_tokens(usage)
            if tokens <= 0:
                continue
            usd, why = prices.cost(self.prices.table, model, usage)
            bill = {"id": mid, "agentId": agent_id, "sessionId": sid, "at": at, "model": model, "tokens": tokens,
                    "usd": None if usd is None else round(usd, 6),
                    "priceFrom": "user" if self.prices.user_rows.get(model) else "default"}   # the card says whose
            if why:
                bill["why"] = why
                if why == "model not in the table" and model not in self._unpriced:
                    self._unpriced[model] = at
                    while len(self._unpriced) > UNPRICED_MAX:
                        self._unpriced.pop(next(iter(self._unpriced)))
                    self._dirty.add("prices")
            self._bills = [b for b in self._bills if not (b["id"] == mid and b["agentId"] == agent_id)] + [bill]
            self._dirty.add("bills")
        if len(seen) > 2_000:
            for mid in list(seen)[:-1_000]:
                del seen[mid]

    def _prune_bills(self, at: int) -> None:
        kept = [b for b in self._bills if at - b["at"] < BILL_KEEP_MS][-BILLS_MAX:]
        if len(kept) != len(self._bills):
            self._bills = kept
            self._dirty.add("bills")

    def close_pools(self) -> None:
        """The server stopping: each pool's idle thread goes now, a job still running is not waited for (the server
        does not wait for it either; ticket 2026-10-21-jui-viz-serve-does-not-exit-on-term)."""
        for pool in (self._prices_pool, self._data_docs_pool, self._infra_pool):
            if pool is not None:
                pool.shutdown(wait=False, cancel_futures=True)

    def poll_prices(self) -> bool:
        """The user's price table read again when it changed (in a worker thread of its own: never on the loop), and
        a model that is priced now no longer listed as unpriced. True when the table changed (serve logs the rows
        left out)."""
        if self.prices is None:
            return False
        if self._prices_pool is None:
            from concurrent.futures import ThreadPoolExecutor
            self._prices_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="jui-viz-prices")
        if not self.prices.poll(self._prices_pool):
            return False
        for model in [m for m in self._unpriced if m in self.prices.table]:
            del self._unpriced[model]
        self._dirty.add("prices")
        return True

    def prices_slice(self) -> dict:
        book = self.prices
        if book is None:
            return {}
        return {"rows": book.rows(), "errors": list(book.errors), "unpriced": sorted(self._unpriced),
                "source": book.default.get("source"), "checked": book.default.get("checked"),
                "userPath": tilde(str(book.path())), "rev": book.rev}

    def _heavy(self, at: int) -> None:
        for sid, session in self.sessions.items():
            window = [x for x in self._tokens.get(sid, []) if x[0] > at - HEAVY_WINDOW_MS]
            self._tokens[sid] = window
            reasons = []
            if sum(t for _, t in window) >= HEAVY_TOKENS_PER_MIN * HEAVY_WINDOW_MS / 60_000:
                reasons.append("tokens")
            mine = [aid for aid, ag in self.agents.items() if ag["sessionId"] == sid]
            if any(at - self._tool_started.get(u, at) >= HEAVY_TOOL_MS for aid in mine for u in self._open.get(aid, [])):
                reasons.append("tool")
            subs = sum(1 for aid in mine if self.agents[aid]["kind"] == "sub" and not self.agents[aid].get("leftAt"))
            if subs >= HEAVY_SUBAGENTS:
                reasons.append("subagents")
            if session["status"] == "ended":
                reasons = []
            open_ms = [at - self._tool_started.get(u, at) for aid in mine for u in self._open.get(aid, [])]
            info = {"tokensPerMin": round(sum(t for _, t in window) * 60_000 / HEAVY_WINDOW_MS), "toolSec": max(open_ms, default=0) // 1000,
                    "subagents": subs} if reasons else None
            if reasons != session.get("heavy", []) or info != session.get("heavyInfo"):
                if reasons:
                    session["heavy"], session["heavyInfo"] = reasons, info   # the card says what made it heavy
                else:
                    session.pop("heavy", None)
                    session.pop("heavyInfo", None)
                self._dirty.add("sessions")

    # ---------------------------------------------------------------- publish

    def publish(self) -> None:
        """Write the changed slices into the state store (sorted for stable output)."""
        if "projects" in self._dirty:
            used = {s["projectId"] for s in self.sessions.values()}
            # copies: a row changed in place (apply_mock) must compare unequal to the one published before, or
            # set_slice sees no change and the page never hears of it
            projects = [dict(p) for p in self.rooms.projects.values() if p["id"] in used]
            self.state.set_slice("projects", sorted(projects, key=lambda p: p["order"]))
        relay, prompt = self.perms.relay_sessions(), self.perms.prompt_sessions()
        for sid, session in self.sessions.items():
            how = self.launch_of(sid) if sid in prompt else None
            if session["relay"] != (sid in relay) or session.get("prompt") != (sid in prompt) or session.get("launch") != how:
                session["relay"] = sid in relay
                session["prompt"] = sid in prompt   # relay true and prompt false: a jui-viz plugin older than 1.2.0
                session["launch"] = how             # launch.REASONS: whether the CLI hands the channel's text over
                self._dirty.add("sessions")
        if "perms" in self._dirty:
            self.state.set_slice("perms", self.perms.items())
        if "questions" in self._dirty:
            self.state.set_slice("questions", self.questions.items())
        if "denials" in self._dirty:
            self.state.set_slice("denials", self.denials.items())
        if "calls" in self._dirty:
            self.state.set_slice("calls", self.calls.items())
        if "sessions" in self._dirty:
            self.state.set_slice("sessions", sorted((dict(s) for s in self.sessions.values()), key=lambda s: s["startedAt"]))
        if "agents" in self._dirty:
            self.state.set_slice("agents", sorted((dict(a) for a in self.agents.values()), key=lambda a: (a["startedAt"], a["id"])))
        if "specs" in self._dirty or "tasks" in self._dirty:
            names: dict[str, str] = {}
            for project in self.jsonui.values():
                for sid, entry in project.specs.items():
                    meta = (entry.data or {}).get("metadata") or {}
                    for name in (meta.get("name"), meta.get("displayName"), entry.path.name.replace(".spec.json", "")):
                        if isinstance(name, str) and name:
                            names[name.lower()] = sid
            self.tasks.link_specs(names)
        if "specs" in self._dirty:
            specs = []
            for project in self.jsonui.values():
                specs.extend(project.summaries(self._now))
            self.state.set_slice("specs", specs)
        if "tasks" in self._dirty:
            self.state.set_slice("tasks", self.tasks.items())
        if "tests" in self._dirty:
            self.state.set_slice("tests", sorted(({k: v for k, v in t.items() if k not in ("progressRun", "progressRuns")} for t in self.tests.values()),
                                                 key=lambda t: t["startedAt"]))
        if "bills" in self._dirty:
            self.state.set_slice("bills", [dict(b) for b in self._bills])
        if "prices" in self._dirty:
            self.state.set_slice("prices", self.prices_slice())
        if "devices" in self._dirty:
            self.state.set_slice("devices", self.devices_slice(self.wall_ms()))
        if "machine" in self._dirty:
            self.state.set_slice("machine", dict(self.machine))
        self._dirty.clear()
