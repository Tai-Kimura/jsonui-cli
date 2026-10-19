"""One probe per ledger entry: the current shape of what we rely on, as a small JSON value.

A probe never judges; the watcher compares its shape with the one saved last time, and any difference (or a probe
that raised) is red. Two kinds:

* help probes read the CLI's own help text (``claude --help``, ``claude plugin --help``, ``claude mcp --help``):
  read-only, no session, no quota;
* session probes read what one short throwaway session left behind (Session, from watch.live_session): its transcript,
  the hook inputs and environment its own hooks recorded, the statusLine input, and whether SIGTERM ended it with a
  SessionEnd. Without a session (the watcher run without --live, and every test) they report ``{"skipped": ...}``,
  which is a shape like any other: a probe that stops being run is a change too.

Each shape lists only what our code reads (the keys, flags, events and sub-commands named here), so a release that
adds things we do not use stays green, and one that renames or drops something we use turns red.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

#: Options of the main command our code passes or tells the user to pass (sources/launch.py, viz_cmd.py, the page).
CLI_FLAGS = ["-n", "--name", "-p", "--print", "-r", "--resume", "--settings", "--setting-sources", "--plugin-dir",
             "--mcp-config", "--session-id", "--channels", "--dangerously-load-development-channels"]
PLUGIN_SUBCOMMANDS = ["marketplace", "install", "update", "list", "enable", "disable"]
MCP_SUBCOMMANDS = ["add", "get", "list", "remove"]
#: Transcript record fields read by viz (sources/transcripts.py, sources/history.py, ingest usage).
TRANSCRIPT_KEYS = {"*": ["type", "timestamp", "message", "sessionId", "cwd", "uuid"],
                   "assistant": ["message.id", "message.content", "message.usage", "message.model"],
                   "user": ["message.content", "isMeta"]}
CONTENT_BLOCKS = ["text", "tool_use", "tool_result", "thinking", "image"]
#: Hook payload fields read by forward.py / ingest.py / the session-recovery and agents hooks.
HOOK_KEYS = {"*": ["session_id", "transcript_path", "cwd", "hook_event_name", "permission_mode"],
             "SessionStart": ["source"], "SessionEnd": ["reason"], "UserPromptSubmit": ["prompt"],
             "PreToolUse": ["tool_name", "tool_input", "tool_use_id"],
             "PostToolUse": ["tool_name", "tool_input", "tool_response", "tool_use_id"], "Stop": []}
#: CLAUDECODE: set by the CLI for what it starts; vitest picks its agent reporter on it (test_tools branch_tests.py).
ENV_NAMES = ["CLAUDE_PROJECT_DIR", "CLAUDE_PLUGIN_ROOT", "CLAUDE_CODE_ENTRYPOINT", "CLAUDECODE"]
STATUSLINE_KEYS = ["session_id", "transcript_path", "cwd", "model", "workspace", "version"]
CONFIG_PATHS = ["settings.json", "projects", "sessions", "plugins"]
#: Tool names viz keys on (robots.py, questions.py, permissions.py, config.py, the page): present in the session's tools.
TOOL_NAMES = ["AskUserQuestion", "Bash", "Edit", "Write", "Read", "NotebookEdit", "Agent", "SendMessage", "TodoWrite",
              "WebFetch", "WebSearch", "Glob", "Grep"]


@dataclass
class Session:
    """What one throwaway session left: its config folder, its hook inputs and env, its statusLine input, its end."""
    config_dir: Path
    hook_inputs: list[dict] = field(default_factory=list)
    hook_env: dict[str, str] = field(default_factory=dict)
    statusline: dict | None = None
    sigterm_exit: int | None = None
    sigterm_session_end: bool | None = None
    result: dict | None = None          # the -p run's outcome: ok, result text, terminal_reason, cost, usage
    init: dict | None = None            # the stream's system/init record: tools, mcp_servers, …


@dataclass
class Context:
    run: Callable[[list[str]], tuple[int, str]]      # argv -> (exit code, stdout + stderr); the watcher's is a subprocess
    session: Session | None = None
    #: The machine's own transcripts folder (the config folder's projects/), read only by the talk probes: SendMessage
    #: needs two live sessions, which a throwaway -p session cannot be, while this machine's sessions send hundreds a
    #: day with the installed CLI (measured 10-20: 688 in 24 h). None (every test, and the watcher without --live):
    #: the talk probes report skipped.
    transcripts: Path | None = None
    _talk: dict | None = None


def _help_options(text: str) -> set[str]:
    return set(re.findall(r"(?<![\w-])(--?[a-zA-Z][\w-]*)", text))


def _subcommands(text: str) -> set[str]:
    lines = text.split("Commands:", 1)[1].splitlines() if "Commands:" in text else []
    return {m.group(1) for ln in lines if (m := re.match(r"\s{2,}([a-z][\w-]*)", ln))}


def cli_flags(ctx: Context):
    rc, text = ctx.run(["--help"])
    found = _help_options(text)
    return {"exit": rc, "flags": {f: f in found for f in CLI_FLAGS}}


def plugin_cli(ctx: Context):
    rc, text = ctx.run(["plugin", "--help"])
    found = _subcommands(text)
    return {"exit": rc, "subcommands": {c: c in found for c in PLUGIN_SUBCOMMANDS}}


def mcp_cli(ctx: Context):
    rc, text = ctx.run(["mcp", "--help"])
    found = _subcommands(text)
    return {"exit": rc, "subcommands": {c: c in found for c in MCP_SUBCOMMANDS}}


def channels_flags(ctx: Context):
    rc, text = ctx.run(["--help"])
    found = _help_options(text)
    return {"exit": rc, "flags": {f: f in found for f in ("--channels", "--dangerously-load-development-channels")}}


def _skipped(ctx: Context):
    return None if ctx.session is not None else {"skipped": "no session (run with --live)"}


def _has(record: dict, dotted: str) -> bool:
    cur = record
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return False
        cur = cur[part]
    return True


def transcript_shape(ctx: Context):
    if (s := _skipped(ctx)) is not None:
        return s
    files = sorted((ctx.session.config_dir / "projects").glob("*/*.jsonl"))
    records = [json.loads(ln) for f in files for ln in f.read_text().splitlines() if ln.strip()]
    shape = {"files": len(files) > 0, "keys": {}}
    for kind, keys in TRANSCRIPT_KEYS.items():
        chosen = [r for r in records if kind == "*" or r.get("type") == kind]
        shape["keys"][kind] = {k: bool(chosen) and all(_has(r, k) for r in chosen) for k in keys} if kind != "*" else \
            {k: any(_has(r, k) for r in chosen) for k in keys}
    blocks = {b.get("type") for r in records for b in ((r.get("message") or {}).get("content") or [])
              if isinstance((r.get("message") or {}).get("content"), list) and isinstance(b, dict)}
    shape["blocks_seen"] = sorted(b for b in CONTENT_BLOCKS if b in blocks)
    return shape


def hook_input_shape(ctx: Context):
    if (s := _skipped(ctx)) is not None:
        return s
    by_event: dict[str, dict] = {}
    for payload in ctx.session.hook_inputs:
        by_event.setdefault(payload.get("hook_event_name", "?"), payload)
    shape = {}
    for event, keys in HOOK_KEYS.items():
        if event == "*":
            shape["*"] = {k: all(k in p for p in ctx.session.hook_inputs) and bool(ctx.session.hook_inputs) for k in keys}
        else:
            p = by_event.get(event)
            shape[event] = None if p is None else {k: k in p for k in keys}
    return shape


def env_vars(ctx: Context):
    if (s := _skipped(ctx)) is not None:
        return s
    return {name: name in ctx.session.hook_env for name in ENV_NAMES}


def statusline_input(ctx: Context):
    if (s := _skipped(ctx)) is not None:
        return s
    data = ctx.session.statusline
    return None if data is None else {k: k in data for k in STATUSLINE_KEYS}


def sigterm_session_end(ctx: Context):
    if (s := _skipped(ctx)) is not None:
        return s
    return {"exited": ctx.session.sigterm_exit is not None, "session_end": bool(ctx.session.sigterm_session_end)}


def config_paths(ctx: Context):
    if (s := _skipped(ctx)) is not None:
        return s
    return {p: (ctx.session.config_dir / p).exists() for p in CONFIG_PATHS}


def agents_cli(ctx: Context):
    """`claude agents --json` (sources/agents_cli.py): the sub-command and its --json option."""
    rc, text = ctx.run(["agents", "--help"])
    return {"exit": rc, "json": "--json" in _help_options(text)}


def tool_names(ctx: Context):
    """The tools the session offers (the stream's init record), by the names viz keys on; and that MCP tools are still
    named mcp__<server>__<tool> (only when the session has an MCP server: otherwise None)."""
    if (s := _skipped(ctx)) is not None:
        return s
    tools = (ctx.session.init or {}).get("tools")
    if not isinstance(tools, list):
        return {"tools": None}
    mcp = [t for t in tools if isinstance(t, str) and t.startswith("mcp__")]
    return {"tools": {t: t in tools for t in TOOL_NAMES},
            "mcp_prefix": (all(t.count("__") >= 2 for t in mcp) if mcp else None)}


# ------------------------------------------------------------------ the talk view (viz/talk.py, sources/talk_records.py)
#: How far back and how much the talk probes read: the newest files first, records of the last TALK_DAYS days only.
TALK_DAYS = 7
TALK_FILES = 80
TALK_BYTES = 256 * 1_048_576
TALK_FILE_BYTES = 16 * 1_048_576
TALK_KEEP = 40
SEND_INPUT_KEYS = ["to", "message", "summary"]
PEER_ORIGIN_KEYS = ["kind", "msg_id", "from", "verifiedPeerPid", "name", "body"]
CHILD_ORIGIN_KEYS = ["kind", "senderTaskId", "from", "body"]
_ENVELOPE = re.compile(r'^<cross-session-message\b[^>]*\bfrom-name="[^"]*"[^>]*>\n')


def _talk_scan(ctx: Context) -> dict | None:
    """The newest SendMessage records of this machine's transcripts, by kind (read once per run, only lines with a
    needle parsed; the bodies are looked at only to compare the two sides, never kept in a shape)."""
    if ctx.transcripts is None:
        return None
    if ctx._talk is not None:
        return ctx._talk
    import os
    import time
    root, since = Path(ctx.transcripts), time.time() - TALK_DAYS * 86_400
    files = []
    for pattern in ("*/*.jsonl", "*/*/subagents/**/agent-*.jsonl"):
        for f in root.glob(pattern):
            try:
                st = f.lstat()
            except OSError:
                continue
            if not f.is_symlink() and st.st_mtime >= since:
                files.append((st.st_mtime, f))
    got = {"sends": [], "results": [], "peer": [], "queued": [], "child": [], "coordinator": [], "enqueue": [], "agent_msg": []}
    sends: set = set()
    read = 0
    for _m, f in sorted(files, reverse=True)[:TALK_FILES]:
        if read >= TALK_BYTES:
            break
        try:
            fd = os.open(f, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(fd, "rb") as fh:          # the newest records: the file's tail
                size = os.fstat(fh.fileno()).st_size
                want = min(size, TALK_FILE_BYTES, TALK_BYTES - read)
                fh.seek(size - want)
                data = fh.read(want)
        except OSError:
            continue
        read += len(data)
        lines = data.split(b"\n")
        if len(data) < size:
            lines = lines[1:]                           # the first line is cut
        for line in lines:
            if not (b'"SendMessage"' in line or b'"origin"' in line or b'"enqueue"' in line or (sends and b'"tool_result"' in line)):
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            t = r.get("type")
            if t == "assistant":
                for b in (r.get("message") or {}).get("content") or []:
                    if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") == "SendMessage":
                        sends.add(b.get("id"))
                        got["sends"].append(b.get("input") if isinstance(b.get("input"), dict) else {})
            elif t == "user":
                content = (r.get("message") or {}).get("content")
                for b in content if isinstance(content, list) else []:
                    if isinstance(b, dict) and b.get("type") == "tool_result" and b.get("tool_use_id") in sends:
                        got["results"].append(r.get("toolUseResult"))
                o = r.get("origin")
                if isinstance(o, dict) and o.get("kind") == "peer" and not o.get("handback"):
                    got["child" if o.get("senderTaskId") else "peer"].append(o)
                elif isinstance(o, dict) and o.get("kind") == "coordinator":
                    got["coordinator"].append(o)
            elif t == "attachment":
                a = r.get("attachment") or {}
                if a.get("type") == "queued_command" and isinstance(a.get("origin"), dict):
                    got["queued"].append(a)
            elif t == "queue-operation" and r.get("operation") == "enqueue" and isinstance(r.get("content"), str):
                c = r["content"]
                if c.startswith("<cross-session-message"):
                    got["enqueue"].append(c)
                elif c.startswith("<agent-message"):
                    got["agent_msg"].append(c)
    ctx._talk = {k: v[-TALK_KEEP:] for k, v in got.items()}
    return ctx._talk


def _talk_skipped(ctx: Context):
    return {"skipped": "no transcripts folder (run with --live)"} if _talk_scan(ctx) is None else None


def _all_any(items: list, test) -> str:
    """'all' / 'some' / 'none' / 'unseen' (no record of the kind in the window): a shape, not a judgement."""
    if not items:
        return "unseen"
    n = sum(1 for i in items if test(i))
    return "all" if n == len(items) else "some" if n else "none"


def talk_send_input(ctx: Context):
    """SendMessage's tool input as talk_records reads it: to, message (the body), summary."""
    if (s := _talk_skipped(ctx)) is not None:
        return s
    sends = [i for i in ctx._talk["sends"] if "message" in i]
    shape = {k: _all_any(sends, lambda i, k=k: k in i) for k in SEND_INPUT_KEYS if k != "summary"}
    # summary is optional (measured 10-19: 156 sends without one): only whether it is still written at all
    shape["summary"] = "unseen" if not sends else "seen" if any("summary" in i for i in sends) else "none"
    return shape


def talk_msg_id(ctx: Context):
    """The match key: toolUseResult.msg_id on the sender's result and origin.msg_id on the receiver's record, the same
    value (one msg_id seen on both sides in the window)."""
    if (s := _talk_skipped(ctx)) is not None:
        return s
    results = [r for r in ctx._talk["results"] if isinstance(r, dict) and "msg_id" in r]
    sent = {r["msg_id"] for r in results if isinstance(r.get("msg_id"), str)}
    origins = ctx._talk["peer"] + [a["origin"] for a in ctx._talk["queued"] if a["origin"].get("kind") == "peer"]
    seen = {o.get("msg_id") for o in origins if isinstance(o.get("msg_id"), str)}
    return {"result_has_msg_id": bool(sent), "origin_has_msg_id": bool(seen),
            "uuid_like": _all_any(sorted(sent | seen), lambda v: re.fullmatch(r"[0-9a-f-]{36}", v) is not None),
            "both_sides": bool(sent & seen) if sent and seen else "unseen"}


def talk_origin(ctx: Context):
    """The receiver's record of a message read: origin {kind peer: msg_id, from, verifiedPeerPid, name, body} on an
    isMeta user record or a queued_command attachment; a subagent's send to main (senderTaskId); the parent's send to
    a subagent (kind coordinator, the queued prompt the body)."""
    if (s := _talk_skipped(ctx)) is not None:
        return s
    peer = ctx._talk["peer"] + [a["origin"] for a in ctx._talk["queued"] if a["origin"].get("kind") == "peer" and not a["origin"].get("senderTaskId")]
    peer = [o for o in peer if "members" not in o]
    queued = ctx._talk["queued"]
    return {"peer": {k: _all_any(peer, lambda o, k=k: k in o) for k in PEER_ORIGIN_KEYS},
            "child": {k: _all_any(ctx._talk["child"], lambda o, k=k: k in o) for k in CHILD_ORIGIN_KEYS},
            "coordinator": "seen" if ctx._talk["coordinator"] or any(a["origin"].get("kind") == "coordinator" for a in queued) else "unseen",
            "queued_command": _all_any(queued, lambda a: isinstance(a.get("prompt"), str) and isinstance(a.get("origin"), dict))}


def talk_envelope(ctx: Context):
    """The enqueue of a message: <cross-session-message … from-name="…">, the body between two newlines (the arrival
    is matched by it); a subagent's to main: <agent-message …>."""
    if (s := _talk_skipped(ctx)) is not None:
        return s
    env = ctx._talk["enqueue"]
    return {"cross_session": _all_any(env, lambda c: _ENVELOPE.match(c) is not None),
            "closed": _all_any(env, lambda c: c.rstrip().endswith("\n</cross-session-message>")),
            "agent_message": "seen" if ctx._talk["agent_msg"] else "unseen"}


def session_ran(ctx: Context):
    """Whether the throwaway session ran at all (a lost login turns every session probe into an empty shape)."""
    if (s := _skipped(ctx)) is not None:
        return s
    r = ctx.session.result or {}
    if r.get("leaks"):     # the session reached the user's real state: red, whatever else it did
        return {"ok": False, "leaks": r["leaks"]}
    return {"ok": bool(r.get("ok"))} if r.get("ok") else {"ok": False, "result": r.get("result"),
                                                         "terminal_reason": r.get("terminal_reason")}


def _price_table() -> dict:
    """The table viz prices responses with: the shipped one and the user's (<viz home>/prices.json) together."""
    import sys
    tools_root = str(Path(__file__).resolve().parents[2])        # jui_tools
    if tools_root not in sys.path:
        sys.path.insert(0, tools_root)
    from jui_cli.viz import prices
    book = prices.PriceBook()
    book.read_now()
    return book.table


def price_table_models(ctx: Context, table: dict | None = None):
    """The models the session's responses name (message.model, its own and its subagents' transcripts) that the price
    table of the bill over a robot (jui_cli/viz/prices.py) has no row for: a new model is red until it is priced."""
    if (s := _skipped(ctx)) is not None:
        return s
    table = _price_table() if table is None else table
    models: set[str] = set()
    for f in sorted((ctx.session.config_dir / "projects").rglob("*.jsonl")):
        for ln in f.read_text(errors="replace").splitlines():
            try:
                rec = json.loads(ln)
            except ValueError:
                continue
            msg = rec.get("message") if isinstance(rec, dict) and rec.get("type") == "assistant" else None
            model = msg.get("model") if isinstance(msg, dict) else None
            if isinstance(model, str) and model and not model.startswith("<"):    # <synthetic>: no API call
                models.add(model)
    return {"responses": bool(models), "unpriced": sorted(m for m in models if m not in table)}


PROBES: dict[str, Callable[[Context], object]] = {
    "cli_flags": cli_flags, "plugin_cli": plugin_cli, "mcp_cli": mcp_cli, "channels_flags": channels_flags,
    "transcript_shape": transcript_shape, "hook_input_shape": hook_input_shape, "env_vars": env_vars,
    "statusline_input": statusline_input, "sigterm_session_end": sigterm_session_end, "config_paths": config_paths,
    "session_ran": session_ran, "agents_cli": agents_cli, "tool_names": tool_names,
    "price_table_models": price_table_models,
    "talk_send_input": talk_send_input, "talk_msg_id": talk_msg_id, "talk_origin": talk_origin,
    "talk_envelope": talk_envelope,
}
