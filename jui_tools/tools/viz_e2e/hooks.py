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


LATE = "0ad0000a-0000-4000-8000-00000000000a"


def rooms_doors():
    """(seconds, body): four rooms on one floor (three across, two deep), robots coming in, one moving from the back
    row to the front row and back, one leaving and one coming in late in the back row, prompts and Stops for the turn cards, a
    permission request."""
    folders = ["shop-app", "jsonui-cli", "JsonUIDocument", "admin-web"]
    sids = [f"{k:02x}d0{k:04x}-0000-4000-8000-{k:012x}" for k in range(10)]
    room = [f"/work/{folders[k % 4]}" for k in range(10)]
    out = []
    for k, sid in enumerate(sids):
        out.append((0.1 * k, base(sid, room[k], "SessionStart", source="startup")))
        out.append((0.1 * k + 0.05, base(sid, room[k], "UserPromptSubmit", prompt=f"<cross-session-message from=\"x\">\n画面 {k} を仕上げて\n詳細…")))
    out += [
        (1.0, pre(sids[0], room[0], "Read", {"file_path": f"{room[0]}/README.md"}, 1)),
        (2.0, base(sids[1], room[1], "Stop")),
        (3.0, pre(sids[2], room[2], "Write", {"file_path": f"{room[2]}/a.txt", "content": "x"}, 2)),
        (3.2, base(sids[2], room[2], "PermissionRequest", tool_name="Write", tool_input={"file_path": f"{room[2]}/a.txt"})),
        (4.0, base(sids[5], room[0], "CwdChanged")),     # jsonui-cli/ to shop-app/: the room next door
        (12.0, base(sids[4], room[3], "CwdChanged")),    # shop-app/ (back row) to admin-web/ in front of it
        (14.0, base(sids[8], room[0], "SessionEnd", reason="exit")),   # out of a back-row room: through the room in front
        (15.0, base(LATE, room[0], "SessionStart", source="startup")),   # and one comes in there late
        (20.0, base(sids[5], room[1], "CwdChanged")),    # and back
    ]
    return out


def write(items, path: pathlib.Path) -> pathlib.Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for sec, body in items:
            f.write(json.dumps({"t": T0 + int(sec * 1000), "body": body}, ensure_ascii=False) + "\n")
    return path
