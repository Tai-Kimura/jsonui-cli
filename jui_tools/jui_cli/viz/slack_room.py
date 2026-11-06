"""The sorting factory: the Slack intake's own room (stages 2 and 3 of docs/plans/2026-11-02-viz-slack-intake-design.md,
§5–§7). Requester 11-02: one robot in a room of its own, reached from the header's Slack button and not from a project;
on the page only what it sorts, a way to tell it something, and the task board (a whiteboard with one note per task).

What it reads, all under ``<orchestrationDir>`` (``slack.json``'s, default ~/slack-orchestration; stage 1 writes it):
  * ``projects/<projectId>/<ts>-<workspace>-<channel>.json`` — a message sorted to a project, already filtered;
  * ``_unsorted/`` — only counted;
  * ``tasks/<taskId>.json`` — the task-making robot writes them (the §7 shape), this module changes the status fields.
What it writes:
  * ``tasks/<taskId>.json`` — the note's edits from the board, and status / startedAt / endedAt / doneAt / target;
  * ``.state/board.json`` — what the robot was already told of, and which started tasks were seen at work;
  * ``slack.json`` — only ``router.prompt`` and ``taskPrompt`` (the two prompts edited in the room); every other key
    is read and written back as it was (stage 1 only reads the file: the orchestrator, 11-02).
Every write is a temporary file renamed over the old one; slack.json keeps 0600 (it holds keys).

The robot: the one session (not ended) whose cwd is in orchestrationDir. Its room is the factory, never a project's
(rooms.Rooms.factory_dir marks it; the page leaves it out of the floors). When a sorted message comes that the robot
was not told of and no task names, and the robot is idle and can take a prompt, it is sent the task prompt with the
new files and the sessions a task can go to; it writes tasks/<id>.json.

A task's states: talking → draft → ready → working → ended → done (talking: the robot judged the exchange not settled;
it or a person raises it to draft). The robot groups messages: a thread always in one task, related ones too; only a
talking, draft or ready task takes more (a later one gets a new task with relatedTaskId). A prompt a person saved on
the board is marked promptEditedByUser and the sources it had then kept (sourcesAtEdit): the robot leaves that prompt,
and the note shows what came after. 開始 sends the task's prompt to the chosen session through
World.submit_prompt (the jui-viz channel: only a session started with it takes it, sources/launch.py) and makes it
working; once that session was seen at work and is idle again (or gone) it is ended; 完了 on the board makes it done.

The scan reads files only (no network, nothing run) in a worker thread; the loop applies it.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path

from . import i18n
from .rooms import tilde
from . import paths
from .slack import config as slack_config
from .slack import filters as slack_filters
from .slack import intake as slack_intake
from .sources import launch

DEFAULT_DIR = slack_config.DEFAULT["orchestrationDir"]
RESERVED_IDS = ("chitchat", "_unsorted", "inbox", "tasks")   # stage 1's (slack/config.validate)
STATUSES = ("talking", "draft", "ready", "working", "ended", "done")
EDITABLE = ("talking", "draft", "ready")
OPEN_SHOWN = 60                # open tasks listed in a notice to the robot (it adds to one or makes a new one)
HEADS_MAX = 400                # source messages whose heads the page gets
TASK_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
SHORT_ID = re.compile(r"^T-(\d{1,9})$")   # the ids the robot gives (T-0042: a person copies it into a message to the robot)
FILE_MAX = 256 * 1024          # a message or task file bigger than this is counted, not read
TASKS_MAX = 300                # newest first
RECENT_MAX = 40                # the arrivals the room shows
HEAD = 160                     # characters of a message the room shows
DONE_RETENTION_MIN = 60        # a done task and its messages are removed this long after doneAt (slack.json doneRetentionMinutes)
MESSAGE_MAX = 20_000           # characters of one message the side panel gets
NOTIFY_FILES_MAX = 40          # files named in one prompt to the robot
NOTIFY_GAP_MS = 20_000         # the robot is told again no sooner than this after a prompt to it
PROMPT_MAX = 20_000            # characters of one prompt kept from the board
LAUNCH_COMMAND = launch.START_CHANNELS
# What the robot may read of the session a task went to (ticket 2026-11-06-viz-slack-robot-reads-the-assigned-sessions-talk).
CONTEXT_DIR = ".state/context"
CONTEXT_MAX = 16_000           # characters of one excerpt; the newest are kept
CONTEXT_ITEM_MAX = 2_000       # characters of one turn in it
# A reply in the thread of a task whose session is settled goes to that session (the same ticket, the requester's addition).
FORWARD_QUIET_MS = 5_000       # a run of replies goes as one prompt: nothing new in the thread for this long
FORWARD_QUIET_MAX_MS = 30_000  # ... but no reply waits longer than this for the thread to go quiet
FORWARD_FULL_WAIT_MS = 600_000 # the session's queue is full (429): tried again this long, then the robot gets it
FORWARD_TEXT_MAX = 4_000       # characters of one reply in the prompt
FORWARD_BATCH_CHARS = 12_000   # characters of replies in one prompt; the rest go in the next
#: A started task's session not known at all is taken as gone only this long after the room first looked (a server just
#: started has not heard from every session yet); one known to have ended ends its task at once.
GONE_GRACE_MS = 60_000


def home_prefix() -> str:
    """`JUI_VIZ_HOME=<folder> ` when this viz keeps its files somewhere other than the default (a test viz on another
    port, JUI_VIZ_HOME or XDG_STATE_HOME set): a session started without it would reach the default viz, not this one —
    its hooks and its channel find the server by that folder (paths.py), and it shows relay: false here (the trial,
    11-02). Empty for the default folder. A folder under the home is written from ~ (the shell expands it in an
    assignment), so the page's slices never carry the home's path."""
    here = paths.viz_home()
    default = Path.home() / ".local" / "state" / "jui-viz"
    return "" if here == default else f"JUI_VIZ_HOME={_sh(tilde(str(here)))} "


def with_home(command: str) -> str:
    """A start command with home_prefix() right before its claude word (after a `cd … &&`), once."""
    prefix = home_prefix()
    if not prefix or not isinstance(command, str) or "JUI_VIZ_HOME=" in command:
        return command
    m = re.search(r"(^|&&\s*|;\s*)claude\b", command)
    return command[:m.end(1)] + prefix + command[m.end(1):] if m else prefix + command


def home_to_tilde(text: str) -> str:
    """A line with the home's path written as ~ (the robot may write a start command from the full path): the page's
    slices never carry the home's path (the talk e2e's check)."""
    home = str(Path.home()).rstrip(os.sep)
    return re.sub(re.escape(home) + r"(?![\w.-])", "~", text) if home and isinstance(text, str) else text


NAME_MAX = 60   # characters of a session name the room puts in a start command (-n)
#: The channels flag takes any number of values, so -n goes right after its one value (session-recovery's term_cmd).
CHANNELS_VALUE = re.compile(r"(--channels|--dangerously-load-development-channels)\s+(\S+)")


def session_name(value) -> str:
    """A name for -n: one line, printable, at most NAME_MAX characters; '' when nothing usable is left."""
    if not isinstance(value, str):
        return ""
    one = " ".join("".join(c if c.isprintable() else " " for c in value).split()).lstrip("-").strip()   # never read as a flag
    return one[:NAME_MAX]


def with_name(command: str, name: str) -> str:
    """A start command with `-n <name>` (quoted as _sh quotes), right after the channels flag's value, or after the claude
    word; left as it is when it already names its session (-n / --name) or has no claude word."""
    name = session_name(name)
    if not name or not isinstance(command, str) or re.search(r"(^|\s)(-n|--name)(\s|=|$)", command):
        return command
    flag = _sh(name) if not name.startswith("~") else "'" + name.replace("'", "'\\''") + "'"
    m = CHANNELS_VALUE.search(command)
    if m:
        return command[:m.end()] + f" -n {flag}" + command[m.end():]
    m = re.search(r"(^|&&\s*|;\s*|\s)claude\b", command)
    return command[:m.end()] + f" -n {flag}" + command[m.end():] if m else command


def config_path() -> Path:
    return slack_config.path()


def load_config(path: Path | None = None) -> tuple[dict, str | None]:
    """slack.json as stage 1 reads it (slack/config.load: 0600 and a regular file, merged over its defaults,
    checked): (the config, None), ({}, "missing"), or ({}, why it cannot be used)."""
    try:
        cfg = slack_config.load(path)
    except slack_config.ConfigError as exc:
        return {}, str(exc)
    return (cfg, None) if cfg is not None else ({}, "missing")


def read_json_file(path: Path) -> tuple[dict, str | None]:
    """A JSON object file of this room's own (a task, the board's state): (it, None), or ({}, why)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}, "missing"
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        return {}, f"unreadable: {type(exc).__name__}"
    return (data, None) if isinstance(data, dict) else ({}, "not a JSON object")


def factory_dir(cfg: dict) -> Path:
    return slack_config.orchestration_dir(cfg)


def inside(cwd: str | None, root: Path) -> bool:
    """Is this cwd (as the sessions slice has it: ~ for home) the root or under it?"""
    if not cwd or cwd == "?":
        return False
    full = os.path.expanduser(cwd)
    r = str(root).rstrip(os.sep)
    return full == r or full.startswith(r + os.sep)


def prompts_of(cfg: dict) -> dict:
    """The two prompts the room edits, as the config has them (strings; projects: id -> description)."""
    router = cfg.get("router") if isinstance(cfg.get("router"), dict) else {}
    prompt = router.get("prompt") if isinstance(router.get("prompt"), dict) else {}
    projects = prompt.get("projects") if isinstance(prompt.get("projects"), dict) else {}
    return {
        "instructions": prompt.get("instructions") if isinstance(prompt.get("instructions"), str) else "",
        "projects": {str(k): v for k, v in projects.items() if isinstance(v, str)},
        "chitchat": prompt.get("chitchat") if isinstance(prompt.get("chitchat"), str) else "",
        "taskPrompt": cfg.get("taskPrompt") if isinstance(cfg.get("taskPrompt"), str) else "",
    }


class Refused(Exception):
    def __init__(self, status: int, why: str) -> None:
        super().__init__(why)
        self.status = status


def _text(value, limit: int = PROMPT_MAX) -> str:
    if not isinstance(value, str):
        raise Refused(400, "a string is required")
    if len(value) > limit:
        raise Refused(413, "too long")
    return value


def clean_prompts(body: dict) -> dict:
    """The body of a prompts save, checked: four strings, projects an object of strings."""
    projects = body.get("projects")
    if not isinstance(projects, dict) or len(projects) > 255:
        raise Refused(400, "projects must be an object of at most 255 entries")
    out = {"instructions": _text(body.get("instructions")), "chitchat": _text(body.get("chitchat")),
           "taskPrompt": _text(body.get("taskPrompt")), "projects": {}}
    for key, value in projects.items():
        key = str(key).strip()
        if not slack_config.safe_name(key) or key in RESERVED_IDS:
            raise Refused(400, f"not a project id: {key[:40]!r}")
        out["projects"][key] = _text(value, 4000)
    return out


def write_json(path: Path, data: dict, mode: int | None = None) -> None:
    """Written whole to a temporary file beside it, then renamed over it (a reader sees the old file or the new)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        if mode is not None:
            os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def save_prompts(prompts: dict, path: Path | None = None) -> dict:
    """router.prompt and taskPrompt into slack.json; every other key as written (not stage 1's defaults merged in).
    Read only when stage 1 would read it (0600, a regular file, valid), written by its save (0600, a temporary file)."""
    path = path or config_path()
    _, why = load_config(path)
    if why not in (None, "missing"):
        raise Refused(409, f"slack.json cannot be used: not overwritten ({why})")
    cfg = json.loads(path.read_text(encoding="utf-8")) if why is None else {}
    router = cfg.get("router") if isinstance(cfg.get("router"), dict) else {}
    old = router.get("prompt") if isinstance(router.get("prompt"), dict) else {}
    router["prompt"] = {**old, "instructions": prompts["instructions"], "projects": prompts["projects"], "chitchat": prompts["chitchat"]}
    cfg["router"] = router
    cfg["taskPrompt"] = prompts["taskPrompt"]
    try:
        slack_config.save(cfg, path)
    except slack_config.ConfigError as exc:
        raise Refused(400, str(exc)) from None
    return cfg


# ---------------------------------------------------------------- the scan (a worker thread: files only)

def _read_small(path: Path, st) -> dict | None:
    if st.st_size > FILE_MAX:
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def plain_text(data: dict) -> str:
    """A projects/ file's text as written. Stage 1 writes it so (filters.apply); a file from before that still has
    Slack's &amp; and <@U…>, written out here too (on a written-out text this changes only a literal "&amp;")."""
    text = data.get("text") if isinstance(data, dict) else None
    return slack_filters.slack_plain(text) if isinstance(text, str) else ""


def _head(text) -> str:
    one = " ".join(str(text).split()) if isinstance(text, str) else ""
    return one if len(one) <= HEAD else one[: HEAD - 1] + "…"


def write_text(path: Path, text: str) -> None:
    """A private text file, written whole: a temporary file renamed over the old one, 0600 in a 0700 folder."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def excerpt_rows(items, since, until) -> list[tuple[str, int, str]]:
    """(who, when, text) of the person's prompts and the session's words between since and until. Tool calls, thoughts,
    other sessions' messages and the harness's texts are left out, and so is a turn with no time."""
    rows = []
    for item in items or []:
        at = item.get("at")
        if not isinstance(at, (int, float)) or at < since or (until is not None and at >= until):
            continue
        kind = item.get("kind")
        text = item.get("text")
        if not isinstance(text, str) or not text.strip() or kind not in ("user", "channel", "assistant"):
            continue
        if kind == "channel" and "jui-viz" not in str(item.get("server") or ""):
            continue
        rows.append(("session" if kind == "assistant" else "person", int(at), text))
    return rows


def excerpt_text(task_id: str, title: str, rows: list[tuple[str, int, str]]) -> str:
    """The excerpt's file: the note first, then the turns, oldest first, the newest kept up to CONTEXT_MAX."""
    head = i18n.tl("srv.slack.context_head", id=task_id, title=_head(title))
    note = i18n.tl("srv.slack.context_cut") + "\n"
    kept, room = [], CONTEXT_MAX - len(head) - len(note)
    for who, at, text in reversed(rows):
        body = text if len(text) <= CONTEXT_ITEM_MAX else text[:CONTEXT_ITEM_MAX] + "\n…"
        when = datetime.fromtimestamp(at / 1000).strftime("%m-%d %H:%M")
        label = i18n.tl("srv.slack.context_session") if who == "session" else i18n.tl("srv.slack.context_person")
        block = f"\n## {label} {when}\n{body}\n"
        if len(block) > room:
            break
        kept.append(block)
        room -= len(block)
    cut = len(kept) < len(rows)
    return head + (note if cut else "") + "".join(reversed(kept))


def _attr(value, limit: int = 200) -> str:
    """A value in the wrapper's opening tag: one line, nothing that could close the tag."""
    return re.sub(r'[\s"<>]+', " ", str(value or "")).strip()[:limit]


def reply_block(row: dict, text: str) -> str:
    """One Slack reply for the session, wrapped. The text cannot close the wrapper: a person in the thread writes it."""
    cut = len(text) > FORWARD_TEXT_MAX
    body = text[:FORWARD_TEXT_MAX] + ("\n…" if cut else "")
    body = re.sub(r"</?\s*slack-reply", "(slack-reply", body, flags=re.I)
    link = row.get("permalink") if str(row.get("permalink") or "").startswith("https://") else ""
    return (f'<slack-reply user="{_attr(row.get("user"))}" channel="{_attr(row.get("channel"))}" ts="{_attr(row.get("ts"))}"'
            f'{f" permalink={chr(34)}{_attr(link, 500)}{chr(34)}" if link else ""}>\n{body}\n</slack-reply>')


class Scanner:
    """Reads the folder; a file is read again only when its size or mtime changed."""

    def __init__(self) -> None:
        self._cache: dict[str, tuple[tuple, object]] = {}

    def _cached(self, path: Path, read):
        try:
            st = path.stat()
        except OSError:
            return None
        key = (st.st_size, st.st_mtime_ns)
        hit = self._cache.get(str(path))
        if hit and hit[0] == key:
            return hit[1]
        value = read(path, st)
        self._cache[str(path)] = (key, value)
        return value

    def scan(self, root: Path) -> dict:
        out: dict = {"exists": root.is_dir(), "arrivals": [], "tasks": [], "unsorted": 0, "broken": 0}
        if not out["exists"]:
            return out
        seen: set[str] = set()
        projects = root / "projects"
        for folder in sorted(projects.iterdir()) if projects.is_dir() else []:
            if not folder.is_dir() or folder.name.startswith("."):
                continue
            for f in folder.glob("*.json"):
                if f.name.startswith("."):
                    continue
                seen.add(str(f))
                rel = f"projects/{folder.name}/{f.name}"

                def read(path, st, rel=rel, project=folder.name):
                    data = _read_small(path, st)
                    row = {"path": rel, "projectId": project, "mtime": int(st.st_mtime * 1000)}
                    if data is None:
                        return {**row, "broken": True}
                    router = data.get("router") if isinstance(data.get("router"), dict) else {}
                    return {**row, "workspace": str(data.get("workspace") or ""), "channel": str(data.get("channel") or ""),
                            "user": str(data.get("user") or ""), "ts": str(data.get("ts") or ""), "head": _head(plain_text(data)),
                            "threadTs": str(data.get("threadTs") or data.get("ts") or ""),
                            "permalink": str(data.get("permalink") or ""),
                            "confidence": router.get("confidence") if isinstance(router.get("confidence"), (int, float)) else None}
                row = self._cached(f, read)
                if row:
                    out["arrivals"].append(row)
                    out["broken"] += 1 if row.get("broken") else 0
        unsorted = root / "_unsorted"
        out["unsorted"] = sum(1 for f in unsorted.glob("*.json")) if unsorted.is_dir() else 0
        tasks = root / "tasks"
        for f in tasks.glob("*.json") if tasks.is_dir() else []:
            if f.name.startswith(".") or not TASK_ID.match(f.stem):
                continue
            seen.add(str(f))

            def read_task(path, st):
                data = _read_small(path, st)
                return {"id": path.stem, "broken": True, "mtime": int(st.st_mtime * 1000)} if data is None else {**data, "id": path.stem, "mtime": int(st.st_mtime * 1000)}
            task = self._cached(f, read_task)
            if task:
                out["tasks"].append(task)
        for gone in set(self._cache) - seen:
            self._cache.pop(gone, None)
        out["arrivals"].sort(key=lambda r: (r["mtime"], r["path"]))
        out["tasks"].sort(key=lambda t: (-(t.get("createdAt") if isinstance(t.get("createdAt"), (int, float)) else t["mtime"]), t["id"]))
        out["tasks"] = out["tasks"][:TASKS_MAX]
        return out


# ---------------------------------------------------------------- the room (on the loop)

class SlackRoom:
    def __init__(self, world, config_file: Path | None = None) -> None:
        self.world = world
        self.config_file = config_file
        self.scanner = Scanner()
        self.cfg: dict = {}
        self.cfg_why: str | None = "missing"
        self.root: Path = factory_dir({})
        self.scanned: dict = {"exists": False, "arrivals": [], "tasks": [], "unsorted": 0, "broken": 0}
        # started: tasks 開始 sent (only these are followed); forwarded: a reply's path -> {task, at, state} (forward_replies)
        self.board: dict = {"notified": [], "sawBusy": {}, "started": {}, "forwarded": {}}
        self.held: set[str] = set()      # replies waiting to go to their session: the robot is not told of them
        self._board_read_for: str | None = None
        self.last_told_at = 0
        self.last_told: list[str] = []
        self.note: str | None = None     # why the robot was not told (no robot, it cannot take a prompt...)
        self.first_follow_at: int | None = None
        self.contexts: set[str] = set()  # the excerpts on disk (paths from the folder), read again before each notice

    # -- reading
    def load(self) -> None:
        """slack.json and the folder (run off the loop: files only)."""
        self.cfg, self.cfg_why = load_config(self.config_file)
        self.root = factory_dir(self.cfg)
        if self._board_read_for != str(self.root):
            self._board_read_for = str(self.root)
            got, _ = read_json_file(self.root / ".state" / "board.json")
            self.board = {"notified": [p for p in got.get("notified", []) if isinstance(p, str)],
                          "sawBusy": {k: v for k, v in (got.get("sawBusy") or {}).items() if isinstance(v, int)},
                          "started": {k: v for k, v in (got.get("started") or {}).items() if isinstance(v, int)},
                          "forwarded": {k: v for k, v in (got.get("forwarded") or {}).items() if isinstance(v, dict)}}
            for row in self.board["forwarded"].values():
                if row.get("state") == "sending":
                    # The server stopped between marking it and hearing back: it may have gone. It is not sent again, and
                    # it does not vanish: the robot gets it (2 度送らない, 黙って落とさない).
                    row.update(state="failed", why="the server stopped while it was being sent")
        self.scanned = self.scanner.scan(self.root)

    def _save_board(self) -> None:
        try:
            write_json(self.root / ".state" / "board.json", self.board)
        except OSError:
            pass

    def task_path(self, task_id) -> Path:
        if not isinstance(task_id, str) or not TASK_ID.match(task_id):
            raise Refused(400, "not a task id")
        return self.root / "tasks" / f"{task_id}.json"

    def _task(self, task_id) -> tuple[Path, dict]:
        path = self.task_path(task_id)
        got, why = read_json_file(path)
        if why == "missing":
            raise Refused(404, "no such task")
        if why:
            raise Refused(409, f"the task file is {why}")
        return path, got

    def _write_task(self, path: Path, task: dict) -> None:
        task.pop("mtime", None)
        task["id"] = path.stem
        write_json(path, task)
        self.scanner._cache.pop(str(path), None)

    # -- who
    def robot(self) -> str | None:
        """The robot's session: not ended, its cwd in the folder; one that can take a prompt first, then the newest."""
        rows = [s for s in self.world.sessions.values() if s.get("status") != "ended" and inside(s.get("cwd"), self.root)]
        rows.sort(key=lambda s: (self.world.prompt_refusal(s["id"]) is None, s.get("startedAt", 0)), reverse=True)
        return rows[0]["id"] if rows else None

    def targets(self) -> list[dict]:
        """The sessions a task can go to: every session not ended and not the factory's."""
        out = []
        projects = self.world.rooms.projects
        for s in sorted(self.world.sessions.values(), key=lambda s: s.get("startedAt", 0)):
            if s.get("status") == "ended" or inside(s.get("cwd"), self.root):
                continue
            refused = self.world.prompt_refusal(s["id"])
            out.append({"sessionId": s["id"], "label": s.get("label", ""), "title": s.get("title") or "", "cwd": s.get("cwd", ""),
                        "project": (projects.get(s.get("projectId")) or {}).get("name", ""), "status": s.get("status", ""),
                        "canPrompt": refused is None, "why": refused[1] if refused else ""})
        return out

    # -- telling the robot
    def pending(self) -> list[str]:
        told = set(self.board["notified"])
        named = {p for t in self.scanned["tasks"] for p in (t.get("sources") or []) if isinstance(p, str)}
        gone_on = {p for p, row in self.board["forwarded"].items() if row.get("state") != "failed"} | self.held
        return [a["path"] for a in self.scanned["arrivals"] if a["path"] not in told and a["path"] not in named and a["path"] not in gone_on and not a.get("broken")]

    def notify_text(self, files: list[str]) -> str:
        prompts = prompts_of(self.cfg)
        task_prompt = prompts["taskPrompt"].strip() or i18n.tl("srv.slack.task_prompt")
        sessions = "\n".join(f"- {t['label']} sessionId={t['sessionId']} cwd={t['cwd']} ({t['project']}"
                             f"{'' if t['canPrompt'] else ', ' + i18n.tl('srv.slack.no_channel')})" for t in self.targets()) or i18n.tl("srv.slack.no_sessions")
        listed = "\n".join(f"- {p}" for p in files)
        open_rows = [t for t in self.scanned["tasks"] if not t.get("broken") and t.get("status") != "done"][:OPEN_SHOWN]
        tasks = "\n".join(f"- {t['id']} [{t.get('status') if t.get('status') in STATUSES else 'draft'}] {_head(t.get('title') or '')}"
                          f" threads={','.join(str(x) for x in t.get('threads') or [])}"
                          f"{' promptEditedByUser' if t.get('promptEditedByUser') else ''}"
                          f"{' context=' + self.context_rel(t['id']) if self.context_rel(t['id']) in self.contexts else ''}" for t in open_rows) or i18n.tl("srv.slack.no_sessions")
        return i18n.tl("srv.slack.notify", prompt=task_prompt, dir=tilde(str(self.root)), files=listed, sessions=sessions,
                       launch=with_home(LAUNCH_COMMAND), tasks=tasks, next=self.next_id())

    def next_id(self) -> str:
        """The next short id: one past the highest T-<n> in tasks/ (T-0001 for the first)."""
        top = max((int(m.group(1)) for t in self.scanned["tasks"] if (m := SHORT_ID.match(t["id"]))), default=0)
        return f"T-{top + 1:04d}"

    async def tell_robot(self, at: int) -> bool:
        """Tell the robot of the new files, when there are some, it is idle and can take a prompt. True when told."""
        files = self.pending()
        if not files:
            self.note = None
            return False
        sid = self.robot()
        if sid is None:
            self.note = "no-robot"
            return False
        refused = self.world.prompt_refusal(sid)
        if refused is not None:
            self.note = "no-channel"
            return False
        if self.world.sessions[sid].get("status") != "idle" or at - self.last_told_at < NOTIFY_GAP_MS:
            self.note = "busy"
            return False
        batch = files[:NOTIFY_FILES_MAX]
        await asyncio.get_running_loop().run_in_executor(None, self.refresh_contexts)
        refused = await self.world.submit_prompt(sid, self.notify_text(batch), at)
        if refused is not None:
            self.note = "refused"
            return False
        self.note = None
        self.last_told_at, self.last_told = at, batch
        self.board["notified"] = (self.board["notified"] + batch)[-5000:]
        self._save_board()
        return True

    # -- what the robot may read: the settled session's talk
    @staticmethod
    def context_rel(task_id: str) -> str:
        return f"{CONTEXT_DIR}/{task_id}.md"

    def _settled_session(self, task: dict) -> str | None:
        """The session a person settled this task on: 開始 sent it there, and it is still working or ended. A status moved
        by hand sends nothing, so the robot's guess at a target is not settled by it."""
        target = task.get("target") if isinstance(task.get("target"), dict) else {}
        sid = target.get("sessionId")
        if task.get("broken") or task.get("status") not in ("working", "ended") or not task.get("assignedAt") or not isinstance(sid, str):
            return None
        return sid

    def refresh_contexts(self) -> None:
        """Write each settled task's excerpt (run off the loop: it reads transcripts), and remove the excerpt of a task that
        has none. A session the World cannot read any more keeps the excerpt it had."""
        folder = self.root / CONTEXT_DIR
        settled = [t for t in self.scanned["tasks"] if self._settled_session(t)]
        live = {t["id"] for t in settled} | {t["id"] for t in self.scanned["tasks"] if not t.get("broken") and t.get("status") == "done"}
        history = getattr(self.world, "history", None)
        for t in settled:
            sid = self._settled_session(t)
            since = t.get("assignedAt")
            later = [o.get("assignedAt") for o in settled if o["id"] != t["id"] and self._settled_session(o) == sid
                     and isinstance(o.get("assignedAt"), (int, float)) and o["assignedAt"] > since]
            until = min(later) if later else None    # the session's next task: from there it is that task's talk
            got = history(sid, stop=0) if history is not None else None
            if got is None:
                continue
            path = folder / f"{t['id']}.md"
            text = excerpt_text(t["id"], t.get("title") or "", excerpt_rows(got.get("items"), since, until))
            try:
                if not path.is_file() or path.read_text(encoding="utf-8") != text:
                    write_text(path, text)
            except OSError:
                continue
        self.contexts = set()
        for f in folder.glob("*.md") if folder.is_dir() else []:
            if f.stem in live:
                self.contexts.add(self.context_rel(f.stem))
            else:
                f.unlink(missing_ok=True)

    # -- a reply in a settled thread goes to its session
    def forward_on(self) -> bool:
        """slack.json autoForwardReplies; on unless it says false (the requester's addition, 11-06)."""
        return self.cfg.get("autoForwardReplies") is not False

    def _reply_task(self, arrival: dict, by_path: dict) -> dict | None:
        """The settled task this message is a reply to: the same thread in the same channel. A thread some open task also
        holds stays the robot's (a thread always goes in one task); of two settled tasks, the one started last."""
        ts = arrival.get("threadTs")
        if not ts:
            return None
        place = (arrival.get("workspace"), arrival.get("channel"))
        def holds(t):
            if ts not in [str(x) for x in t.get("threads") or []]:
                return False
            return place in {(by_path[p].get("workspace"), by_path[p].get("channel")) for p in t.get("sources") or [] if isinstance(p, str) and p in by_path}
        tasks = [t for t in self.scanned["tasks"] if not t.get("broken") and holds(t)]
        if any(t.get("status") in EDITABLE for t in tasks):
            return None
        settled = [t for t in tasks if self._settled_session(t)]
        return max(settled, key=lambda t: t["assignedAt"]) if settled else None

    async def forward_replies(self, at: int) -> bool:
        """Send the new replies of settled threads to their sessions, wrapped, a run of them as one prompt. A reply is
        marked before it is sent and never sent twice, also across a restart. One that cannot go is not lost: it goes back
        to the robot (a new task with relatedTaskId) and the note says so. True when a file changed."""
        self.held = set()
        if not self.forward_on():
            return False
        told = set(self.board["notified"])
        named = {p for t in self.scanned["tasks"] for p in (t.get("sources") or []) if isinstance(p, str)}
        by_path = {a["path"]: a for a in self.scanned["arrivals"]}
        waiting: dict[str, list[dict]] = {}
        for a in self.scanned["arrivals"]:
            p = a["path"]
            if p in told or p in named or p in self.board["forwarded"] or a.get("broken"):
                continue
            task = self._reply_task(a, by_path)
            if task:
                waiting.setdefault(task["id"], []).append(a)
                self.held.add(p)
        changed = False
        for task_id, rows in waiting.items():
            newest, oldest = max(r["mtime"] for r in rows), min(r["mtime"] for r in rows)
            if at - newest < FORWARD_QUIET_MS and at - oldest < FORWARD_QUIET_MAX_MS:
                continue
            changed = await self._forward(task_id, sorted(rows, key=lambda r: r["ts"]), at) or changed
        return changed

    async def _forward(self, task_id: str, rows: list[dict], at: int) -> bool:
        try:
            path, task = self._task(task_id)
        except Refused:
            return False
        sid = self._settled_session(task)
        if sid is None:
            self.held -= {r["path"] for r in rows}   # moved on since the scan: the robot's again
            return False
        blocks, batch, used = [], [], 0
        for r in rows:
            full = self.root / r["path"]
            try:
                data = _read_small(full, full.stat())
            except OSError:
                data = None
            if data is None:
                continue
            block = reply_block(r, plain_text(data))
            if batch and used + len(block) > FORWARD_BATCH_CHARS:
                break
            blocks.append(block)
            batch.append(r["path"])
            used += len(block)
        if not batch:
            return False
        refused = self.world.prompt_refusal(sid)
        if refused is not None:
            return self._forward_failed(path, task, batch, refused, at)
        for p in batch:
            self.board["forwarded"][p] = {"task": task_id, "at": at, "state": "sending"}
        self._save_board()
        text = i18n.tl("srv.slack.forward", id=task_id, title=_head(task.get("title") or ""), replies="\n".join(blocks))
        try:
            refused = await self.world.submit_prompt(sid, text, at)
        except Exception as exc:
            refused = (500, f"{type(exc).__name__}: {exc}")
        if refused is not None:
            for p in batch:
                self.board["forwarded"].pop(p, None)
            self._save_board()
            return self._forward_failed(path, task, batch, refused, at)
        for p in batch:
            self.board["forwarded"][p]["state"] = "sent"
        self.board["forwarded"] = dict(list(self.board["forwarded"].items())[-5000:])
        self._save_board()
        self.held -= set(batch)
        task["sources"] = [p for p in task.get("sources") or [] if isinstance(p, str)] + batch
        task["forwarded"] = (task.get("forwarded") if isinstance(task.get("forwarded"), list) else []) + [{"path": p, "at": at, "sessionId": sid} for p in batch]
        self._write_task(path, task)
        return True

    def _forward_failed(self, path: Path, task: dict, batch: list[str], refused: tuple[int, str], at: int) -> bool:
        """The session cannot take it. A full queue passes, so that is tried again for a while; anything else, or a queue
        full too long, goes to the robot, and the note says why."""
        first = min((self.scanned_mtime(p) for p in batch), default=at)
        if refused[0] == 429 and at - first < FORWARD_FULL_WAIT_MS:
            return False
        for p in batch:
            self.board["forwarded"][p] = {"task": task["id"], "at": at, "state": "failed", "why": str(refused[1])[:200]}
        self._save_board()
        self.held -= set(batch)
        task["forwardFailed"] = (task.get("forwardFailed") if isinstance(task.get("forwardFailed"), list) else []) + [{"path": p, "at": at, "why": str(refused[1])[:200]} for p in batch]
        self._write_task(path, task)
        return True

    def scanned_mtime(self, rel: str) -> int:
        return next((a["mtime"] for a in self.scanned["arrivals"] if a["path"] == rel), 0)

    # -- the started tasks
    def follow(self, at: int) -> bool:
        """working → ended once its session was seen at work and is idle again, or is gone. True when a file changed."""
        changed = False
        if self.first_follow_at is None:
            self.first_follow_at = at
        for task in self.scanned["tasks"]:
            if task.get("status") != "working" or task["id"] not in self.board["started"]:
                continue   # a task made working by hand (the status select) is not followed: nothing was sent
            sid = (task.get("target") or {}).get("sessionId") if isinstance(task.get("target"), dict) else None
            session = self.world.sessions.get(sid) if isinstance(sid, str) else None
            gone = (session is None and at - self.first_follow_at >= GONE_GRACE_MS) or (session is not None and session.get("status") == "ended")
            if session is None and not gone:
                continue
            if not gone and session.get("status") != "idle":
                if task["id"] not in self.board["sawBusy"]:
                    self.board["sawBusy"][task["id"]] = at
                    self._save_board()
                continue
            if gone or task["id"] in self.board["sawBusy"]:
                try:
                    path, fresh = self._task(task["id"])
                except Refused:
                    continue
                if fresh.get("status") != "working":
                    continue
                fresh.update(status="ended", endedAt=at)
                self._write_task(path, fresh)
                self.board["sawBusy"].pop(task["id"], None)
                self.board["started"].pop(task["id"], None)
                self._save_board()
                changed = True
        return changed

    # -- done tasks go (requester 11-02: 「いつまでもメッセージ保管したくない」)
    def robot_name(self) -> str:
        """The robot's session name in its start command (slack.json robotName; the room's name by default)."""
        return session_name(self.cfg.get("robotName")) or session_name(i18n.tl("page.sf.title"))

    def retention_ms(self) -> int:
        got = self.cfg.get("doneRetentionMinutes", DONE_RETENTION_MIN)
        return int(got * 60_000) if isinstance(got, (int, float)) and not isinstance(got, bool) and got >= 0 else DONE_RETENTION_MIN * 60_000

    def purge(self, at: int) -> list[str]:
        """Each task done for doneRetentionMinutes (slack.json, default 60) from its doneAt: its tasks/<id>.json and the
        projects/ files its sources name, but not one another task still names; a task tied to it (relatedTaskId) no
        longer points at it. Run by the server whether the room is open or not. Returns the ids removed."""
        keep = self.retention_ms()
        tasks = [t for t in self.scanned["tasks"] if not t.get("broken")]
        due = [t for t in tasks if t.get("status") == "done" and isinstance(t.get("doneAt"), (int, float)) and at - t["doneAt"] >= keep]
        if not due:
            return []
        gone_ids = {t["id"] for t in due}
        still = {p for t in tasks if t["id"] not in gone_ids for p in t.get("sources") or [] if isinstance(p, str)}
        top = (self.root / "projects").resolve()
        removed = []
        for t in due:
            try:
                path, fresh = self._task(t["id"])
            except Refused:
                continue
            if fresh.get("status") != "done" or not isinstance(fresh.get("doneAt"), (int, float)) or at - fresh["doneAt"] < keep:
                continue   # moved out of done (or done again) since the scan
            for rel in fresh.get("sources") or []:
                if not isinstance(rel, str) or rel in still:
                    continue
                full = (self.root / rel).resolve()
                if full.is_relative_to(top) and full.is_file():
                    full.unlink(missing_ok=True)
            path.unlink(missing_ok=True)
            (self.root / self.context_rel(t["id"])).unlink(missing_ok=True)
            self.contexts.discard(self.context_rel(t["id"]))
            self.scanner._cache.pop(str(path), None)
            removed.append(t["id"])
        for t in tasks:
            if t["id"] not in gone_ids and t.get("relatedTaskId") in removed:
                try:
                    path, fresh = self._task(t["id"])
                except Refused:
                    continue
                fresh["relatedTaskId"] = None
                self._write_task(path, fresh)
        for tid in removed:
            for k in ("sawBusy", "started"):
                self.board[k].pop(tid, None)
        if removed:
            self._save_board()
        return removed

    # -- the board's buttons
    async def act(self, body: dict, at: int) -> dict:
        op = body.get("op")
        path, task = self._task(body.get("id"))
        status = task.get("status") if task.get("status") in STATUSES else "draft"
        if op == "save":
            if status not in EDITABLE:
                raise Refused(409, "only a draft or a ready task is edited")
            if "title" in body:
                task["title"] = _text(body["title"])
            if "prompt" in body:
                text = _text(body["prompt"])
                if text != task.get("prompt"):
                    task.update(prompt=text, promptEditedByUser=True,
                                sourcesAtEdit=[p for p in task.get("sources") or [] if isinstance(p, str)])
            if "target" in body:
                task["target"] = self._target(body["target"])
        elif op == "status":
            # the note's status select (requester 11-02): any state, written at once; nothing is sent (only 開始 sends),
            # and a task moved by hand is no longer followed to ended. Done again starts its hour again; out of done, kept.
            want = body.get("status")
            if want not in STATUSES:
                raise Refused(400, "not a status")
            task["status"] = want
            for state, key in (("working", "startedAt"), ("ended", "endedAt")):
                if want == state and not task.get(key):
                    task[key] = at
            if want == "done":
                task["doneAt"] = at
            else:
                task.pop("doneAt", None)
            if want in EDITABLE:
                task.pop("assignedAt", None)   # back before 開始: nobody is settled on it any more
            self.board["sawBusy"].pop(task["id"], None)
            self.board["started"].pop(task["id"], None)
            self._save_board()
        elif op == "draft":
            if status != "talking":
                raise Refused(409, "only a talking task is raised to a draft")
            task["status"] = "draft"
        elif op == "ready":
            if status != "draft":
                raise Refused(409, "only a draft is made ready")
            task["status"] = "ready"
        elif op == "start":
            if status != "ready":
                raise Refused(409, "only a ready task is started")
            if "prompt" in body and _text(body["prompt"]) != task.get("prompt"):
                task.update(prompt=body["prompt"], promptEditedByUser=True,
                            sourcesAtEdit=[p for p in task.get("sources") or [] if isinstance(p, str)])
            target = self._target(body.get("target", task.get("target")))
            sid = target.get("sessionId")
            if not sid:
                raise Refused(400, "choose the session to send it to")
            text = task.get("prompt") if isinstance(task.get("prompt"), str) else ""
            if not text.strip():
                raise Refused(400, "the task has no prompt")
            refused = await self.world.submit_prompt(sid, text, at)
            if refused is not None:
                raise Refused(refused[0], refused[1])
            task.update(status="working", startedAt=at, target=target, assignedAt=at)
            self.board["sawBusy"].pop(task["id"], None)
            self.board["started"][task["id"]] = at
            self._save_board()
        elif op == "done":
            if status not in ("working", "ended"):
                raise Refused(409, "only a started task is done")
            task.update(status="done", doneAt=at)
            self.board["started"].pop(task["id"], None)
            if task.get("endedAt") is None:
                task["endedAt"] = at
        elif op == "revise":
            text = _text(body.get("text"), 4000).strip()
            if not text:
                raise Refused(400, "say what to change")
            sid = self.robot()
            if sid is None:
                raise Refused(409, "the sorting robot is not running")
            refused = await self.world.submit_prompt(sid, i18n.tl("srv.slack.revise", path=f"tasks/{task['id']}.json", text=text), at)
            if refused is not None:
                raise Refused(refused[0], refused[1])
            return {"ok": True}
        else:
            raise Refused(400, "unknown op")
        self._write_task(path, task)
        return {"ok": True, "status": task.get("status")}

    def messages(self, task_id) -> dict:
        """A task's source messages whole, for the page's side panel (POST /api/slack-room/messages): who, when, the
        text, the thread, the permalink, in thread order (each thread from its first message, then by ts). Only files
        under projects/ are read (a source path that leaves it, or is not there, is listed as missing)."""
        _, task = self._task(task_id)
        top = (self.root / "projects").resolve()
        rows, missing = [], []
        for rel in [p for p in task.get("sources") or [] if isinstance(p, str)][:200]:
            try:
                full = (self.root / rel).resolve()
                st = full.stat() if full.is_relative_to(top) else None
            except (OSError, ValueError):
                st = None
            data = _read_small(full, st) if st is not None and full.is_file() else None
            if data is None:
                missing.append(rel)
                continue
            ts = str(data.get("ts") or "")
            link = data.get("permalink") if isinstance(data.get("permalink"), str) and data["permalink"].startswith("https://") else ""
            rows.append({"path": rel, "user": str(data.get("user") or ""), "channel": str(data.get("channel") or ""),
                         "workspace": str(data.get("workspace") or ""), "ts": ts, "threadTs": str(data.get("threadTs") or ts),
                         "text": plain_text(data)[:MESSAGE_MAX], "permalink": link})
        def num(x):
            try:
                return float(x)
            except ValueError:
                return 0.0
        rows.sort(key=lambda r: (num(r["threadTs"]), num(r["ts"])))
        return {"id": task["id"], "title": task.get("title") or task["id"], "messages": rows, "missing": missing}

    def _target(self, value) -> dict:
        if not isinstance(value, dict):
            raise Refused(400, "target must be an object")
        sid = value.get("sessionId")
        if sid in (None, ""):
            return {"sessionName": _text(value.get("sessionName") or "", 200), "sessionId": None}
        if not isinstance(sid, str) or sid not in self.world.sessions:
            raise Refused(404, "no such session")
        if inside(self.world.sessions[sid].get("cwd"), self.root):
            raise Refused(409, "the sorting robot itself is not a target")
        s = self.world.sessions[sid]
        return {"sessionName": s.get("title") or s.get("label") or sid[:8], "sessionId": sid}

    # -- the page's slice
    def slice(self) -> dict:
        sid = self.robot()
        robot = None
        if sid:
            s = self.world.sessions[sid]
            refused = self.world.prompt_refusal(sid)
            robot = {"sessionId": sid, "label": s.get("label", ""), "title": s.get("title") or "", "status": s.get("status", ""),
                     "canPrompt": refused is None, "why": refused[1] if refused else ""}
        arrivals = self.scanned["arrivals"]
        by_project: dict[str, int] = {}
        for a in arrivals:
            by_project[a["projectId"]] = by_project.get(a["projectId"], 0) + 1
        tasks = []
        for t in self.scanned["tasks"]:
            row = {k: t.get(k) for k in ("id", "title", "projectId", "sources", "threads", "prompt", "target", "launchCommand", "status",
                                         "relatedTaskId", "promptEditedByUser", "sourcesAtEdit", "createdAt", "startedAt", "endedAt", "doneAt", "broken",
                                         "forwarded", "forwardFailed")}
            row["status"] = row["status"] if row["status"] in STATUSES else "draft"
            if row["status"] == "done" and isinstance(row.get("doneAt"), (int, float)):
                row["purgeAt"] = int(row["doneAt"] + self.retention_ms())
            if isinstance(row.get("launchCommand"), str):
                # the file keeps the robot's words; the page's line names the session "<project> <id>" when the robot did not
                named = with_name(row["launchCommand"], " ".join(x for x in (str(row.get("projectId") or ""), str(row.get("id") or "")) if x))
                row["launchCommand"] = with_home(home_to_tilde(named))
            tasks.append(row)
        # each task's source messages, as the room shows them (the newest tasks first, up to HEADS_MAX)
        by_path = {a["path"]: a for a in arrivals}
        heads: dict[str, dict] = {}
        for t in tasks:
            for p in t.get("sources") or []:
                if isinstance(p, str) and p in by_path and p not in heads and len(heads) < HEADS_MAX:
                    a = by_path[p]
                    heads[p] = {k: a.get(k) for k in ("user", "channel", "ts", "threadTs", "head", "broken")}
        return {
            "config": {"path": tilde(str(self.config_file or config_path())), "state": home_to_tilde(self.cfg_why) or "ok"},
            "dir": tilde(str(self.root)), "dirExists": self.scanned["exists"],
            "robot": robot, "robotLaunch": with_home(with_name(f"cd {_sh(tilde(str(self.root)))} && {LAUNCH_COMMAND}", self.robot_name())), "launch": with_home(LAUNCH_COMMAND),
            "arrivals": {"total": len(arrivals), "byProject": by_project, "unsorted": self.scanned["unsorted"],
                         "broken": self.scanned["broken"], "pending": len(self.pending()), "recent": arrivals[-RECENT_MAX:][::-1]},
            "toldAt": self.last_told_at, "told": len(self.last_told), "note": home_to_tilde(self.note),
            "tasks": tasks, "sourceHeads": heads, "targets": [dict(t, cwd=tilde(str(t["cwd"]))) for t in self.targets()],
            "prompts": prompts_of(self.cfg),
            # what the intake is doing (fetch / filter / route, with counts), for the robot's look and bubble
            "work": slack_intake.work(),
        }


def _sh(path: str) -> str:
    """A folder for a shell line: ~ kept outside the quotes so the shell expands it."""
    if re.fullmatch(r"[\w./~-]+", path):
        return path
    if path.startswith("~/"):
        return "~/" + "'" + path[2:].replace("'", "'\\''") + "'"
    return "'" + path.replace("'", "'\\''") + "'"
