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
ENV_NAMES = ["CLAUDE_PROJECT_DIR", "CLAUDE_PLUGIN_ROOT", "CLAUDE_CODE_ENTRYPOINT"]
STATUSLINE_KEYS = ["session_id", "transcript_path", "cwd", "model", "workspace", "version"]
CONFIG_PATHS = ["settings.json", "projects", "sessions", "plugins"]


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


@dataclass
class Context:
    run: Callable[[list[str]], tuple[int, str]]      # argv -> (exit code, stdout + stderr); the watcher's is a subprocess
    session: Session | None = None


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


def session_ran(ctx: Context):
    """Whether the throwaway session ran at all (a lost login turns every session probe into an empty shape)."""
    if (s := _skipped(ctx)) is not None:
        return s
    r = ctx.session.result or {}
    return {"ok": bool(r.get("ok"))} if r.get("ok") else {"ok": False, "result": r.get("result"),
                                                         "terminal_reason": r.get("terminal_reason")}


PROBES: dict[str, Callable[[Context], object]] = {
    "cli_flags": cli_flags, "plugin_cli": plugin_cli, "mcp_cli": mcp_cli, "channels_flags": channels_flags,
    "transcript_shape": transcript_shape, "hook_input_shape": hook_input_shape, "env_vars": env_vars,
    "statusline_input": statusline_input, "sigterm_session_end": sigterm_session_end, "config_paths": config_paths,
    "session_ran": session_ran,
}
