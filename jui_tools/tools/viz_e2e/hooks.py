"""Hook bodies in the shape Claude Code sends them (tests/fixtures/viz/probe/), written as a `serve --record`
file (`{"t": ms, "body": {...}}` per line) so `jui viz serve --replay FILE --speed N` plays them.

Paths are `/work/...` (no real machine's home). The ids start with the labels the view shows (a0…, b4…).
"""

from __future__ import annotations

import json
import pathlib

T0 = 1_760_000_000_000


def base(sid, cwd, event, **kw):
    b = {"session_id": sid, "transcript_path": f"/work/home/.claude/projects/x/{sid}.jsonl", "cwd": cwd,
         "hook_event_name": event, "permission_mode": "default"}
    b.update(kw)
    return b


def pre(sid, cwd, tool, tool_input, n, agent=None):
    b = base(sid, cwd, "PreToolUse", tool_name=tool, tool_input=tool_input, tool_use_id=f"toolu_{sid[:4]}{n:06d}")
    if agent:
        b.update(agent_id=agent[0], agent_type=agent[1])
    return b


def post(sid, cwd, tool, tool_input, n, agent=None):
    b = base(sid, cwd, "PostToolUse", tool_name=tool, tool_input=tool_input, tool_use_id=f"toolu_{sid[:4]}{n:06d}",
             tool_response={"ok": True}, duration_ms=120)
    if agent:
        b.update(agent_id=agent[0], agent_type=agent[1])
    return b


S_A0 = "a07c09fe-2f17-530c-add4-737ff77c3934"
S_B4 = "b47e2d19-6c3a-4f80-9e25-1d8b7c4a0f62"
S_4F = "4f2b91c0-8d3e-4a51-9b7e-0c6d2a5e8f13"
SUB = ("a3f19c2e8b7d4a601", "jsonui-define")
SHOP, CLI = "/work/shop-app", "/work/jsonui-cli"


def two_projects():
    """(seconds, body): three sessions in two folders; a0 writes a spec; a subagent comes and goes; 4f moves."""
    spec = {"file_path": f"{SHOP}/docs/screens/json/login.spec.json", "content": "{}"}
    home = {"file_path": f"{SHOP}/docs/screens/json/home.spec.json"}
    out = [
        (0.0, base(S_A0, SHOP, "SessionStart", source="startup")),
        (0.1, base(S_B4, SHOP, "SessionStart", source="startup")),
        (0.2, base(S_4F, CLI, "SessionStart", source="startup")),
        (0.3, pre(S_4F, CLI, "Bash", {"command": "jui build --ios-only", "description": "build"}, 1)),
        (3.0, pre(S_A0, SHOP, "Write", spec, 2)),
        (5.0, post(S_A0, SHOP, "Write", spec, 2)),
        (6.0, base(S_A0, SHOP, "SubagentStart", agent_id=SUB[0], agent_type=SUB[1])),
        (6.5, pre(S_A0, SHOP, "Read", home, 3, agent=SUB)),
        (12.0, post(S_A0, SHOP, "Read", home, 3, agent=SUB)),
        (12.5, base(S_A0, SHOP, "SubagentStop", agent_id=SUB[0], agent_type=SUB[1],
                    last_assistant_message="Login の spec を書き終えた", stop_hook_active=False)),
        (20.0, base(S_4F, SHOP, "CwdChanged")),   # `cwd` is the new folder (plan 03, the common field)
        (20.5, pre(S_4F, SHOP, "Read", {"file_path": f"{SHOP}/README.md"}, 4)),
    ]
    return out


def write(items, path: pathlib.Path) -> pathlib.Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for sec, body in items:
            f.write(json.dumps({"t": T0 + int(sec * 1000), "body": body}, ensure_ascii=False) + "\n")
    return path
