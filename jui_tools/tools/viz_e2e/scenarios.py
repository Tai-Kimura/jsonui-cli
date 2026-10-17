"""Scenarios for fake_server.py, written out by run.py (and by gen_load.py for the load test).

Slices have the shapes of plan 04 §1 (Project, Session, Agent) and are sent whole, as the server does. Paths are
display paths (`~/work/...`): nothing here names a real machine.
"""

from __future__ import annotations

import json
import pathlib

T0 = 1_760_000_000_000   # a fixed epoch-ms start; the view shows times of day, the tests compare states


def project(pid, name, order, jsonui=True):
    return {"id": pid, "name": f"{name}/", "displayRoot": f"~/work/{name}", "jsonui": jsonui, "order": order}


def session(sid, label, pid, root, status="busy", title=""):
    return {"id": sid, "label": label, "projectId": pid, "cwd": f"~/work/{root}", "title": title, "status": status,
            "relay": False, "startedAt": T0, "updatedAt": T0}


def agent(aid, label, sid, kind="main", role="main", state="idle", act="", agent_type=None, left_at=None):
    a = {"id": aid, "label": label, "sessionId": sid, "kind": kind, "role": role, "state": state, "act": act,
         "startedAt": T0, "updatedAt": T0}
    if agent_type:
        a["agentType"] = agent_type
    if left_at:
        a["leftAt"] = left_at
    return a


def event(seq, sid, aid, kind, cat, text, tool=None, detail=None):
    e = {"seq": seq, "at": T0 + seq * 1000, "sessionId": sid, "agentId": aid, "kind": kind, "cat": cat, "text": text}
    if tool:
        e["tool"] = tool
    if detail is not None:
        e["detail"] = detail
    return e


def slices(t, **changed):
    return {"t": t, "msg": {"type": "slices", "changed": changed}}


def server_slice(errors=None):
    sources = {"agents_cli": {"state": "ok"}, "session_files": {"state": "ok"}}
    for k, msg in (errors or {}).items():
        sources[k] = {"state": "error", "error": msg}
    return {"version": "fake", "startedAt": T0, "pid": 0, "port": 0, "sources": sources, "at": T0}


S_A0, S_B4, S_4F, S_C9 = ("a07c09fe-2f17-530c-add4-737ff77c3934", "b47e2d19-6c3a-4f80-9e25-1d8b7c4a0f62",
                          "4f2b91c0-8d3e-4a51-9b7e-0c6d2a5e8f13", "c91e7a44-5b20-4f6d-8e19-3a7b2c0d9e55")
SUB_A3 = "a3f19c2e8b7d4a601"


def two_projects():
    """Two projects, three sessions; a tool call, a subagent coming and going, a session moving rooms, a third
    project, a source failing and recovering. Marks: start, tool, sub-enter, sub-done, sub-gone, move, third,
    broken, mended."""
    P = [project("p-shop", "shop-app", 0), project("p-cli", "jsonui-cli", 1, jsonui=False)]
    S = [session(S_A0, "a0", "p-shop", "shop-app"), session(S_B4, "b4", "p-shop", "shop-app", status="idle"),
         session(S_4F, "4f", "p-cli", "jsonui-cli")]
    main = lambda sid, label, **kw: agent(sid, label, sid, **kw)  # noqa: E731
    A = [main(S_A0, "a0", state="idle", act="待機"), main(S_B4, "b4", state="idle", act="待機"),
         main(S_4F, "4f", state="command", act="Bash jui build --ios-only")]
    items = [{"mark": "start"}, slices(0, projects=P, sessions=S, agents=A, server=server_slice()),
             {"t": 0.1, "msg": {"type": "events", "items": [event(1, S_4F, S_4F, "PreToolUse", "tool", "Bash jui build --ios-only", "Bash", {"command": "jui build --ios-only"})]}}]
    items.append({"mark": "tool"})
    A1 = [main(S_A0, "a0", state="typing", act="Write docs/screens/json/login.spec.json"), A[1], A[2]]
    items += [slices(3, agents=A1),
              {"t": 3, "msg": {"type": "events", "items": [event(2, S_A0, S_A0, "PreToolUse", "tool", "Write docs/screens/json/login.spec.json", "Write",
                                                               {"tool_name": "Write", "tool_input": {"file_path": "docs/screens/json/login.spec.json", "content": "<script>alert(1)</script>"}})]}}]
    items.append({"mark": "sub-enter"})
    sub = agent(SUB_A3, "a3", S_A0, kind="sub", role="define", state="reading", act="Read docs/screens/json/home.spec.json", agent_type="jsonui-define")
    A2 = [main(S_A0, "a0", state="idle", act="サブエージェントの報告待ち"), A[1], A[2], sub]
    items += [slices(6, agents=A2),
              {"t": 6, "msg": {"type": "events", "items": [event(3, S_A0, SUB_A3, "SubagentStart", "session", "jsonui-define を呼んだ")]}}]
    items.append({"mark": "sub-done"})
    done = dict(sub, state="done", act="Login の spec を書き終えた", leftAt=T0 + 20000)
    A3 = [A2[0], A[1], A[2], done]
    items += [slices(14, agents=A3),
              {"t": 14, "msg": {"type": "events", "items": [event(4, S_A0, SUB_A3, "SubagentStop", "session", "Login の spec を書き終えた")]}}]
    items.append({"mark": "sub-gone"})
    items += [slices(20, agents=[A2[0], A[1], A[2]])]
    items.append({"mark": "move"})
    S2 = [S[0], S[1], dict(S[2], projectId="p-shop", cwd="~/work/shop-app")]
    items += [slices(24, sessions=S2),
              {"t": 24, "msg": {"type": "events", "items": [event(5, S_4F, S_4F, "CwdChanged", "session", "~/work/shop-app に移動")]}}]
    items.append({"mark": "third"})
    P3 = P + [project("p-doc", "JsonUIDocument", 2)]
    S3 = S2 + [session(S_C9, "c9", "p-doc", "JsonUIDocument")]
    A4 = [A2[0], A[1], A[2], main(S_C9, "c9", state="reading", act="Read docs/screens/json/spec-anatomy.spec.json")]
    items += [slices(30, projects=P3, sessions=S3, agents=A4)]
    items.append({"mark": "broken"})
    items += [slices(34, server=server_slice({"agents_cli": "claude agents --json が見つからない"}))]
    items.append({"mark": "mended"})
    items += [slices(38, server=server_slice())]
    items.append({"mark": "end"})
    return items


def empty():
    """The server is up and has no session yet."""
    return [{"mark": "start"}, slices(0, projects=[], sessions=[], agents=[], server=server_slice()), {"mark": "end"}]


def write(items, path: pathlib.Path) -> pathlib.Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in items), encoding="utf-8")
    return path
