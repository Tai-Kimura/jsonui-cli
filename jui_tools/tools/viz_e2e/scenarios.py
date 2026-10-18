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


# ---------------------------------------------------------------- P4 / P5: specs, tasks, tests, permissions
SECTION_KEYS = ["metadata", "structure", "stateManagement", "dataFlow", "userActions", "transitions", "branchContracts"]
SCREENS = ["login", "signup", "home", "search", "detail", "cart", "checkout", "orders", "mypage", "settings"]


def spec(name, state="written", items=None, impl=(0, 0), tests=(0, 0, 0, False), bucket="partial", by=None, writing=None):
    items = items or [5, 6, 3, 4, 2, 2, 3]
    sections = [{"key": k, "state": ("writing" if writing == k else state if n else "empty"), "items": n}
                for k, n in zip(SECTION_KEYS, items)]
    s = {"id": f"p-shop:docs/screens/json/{name}.spec.json", "projectId": "p-shop", "name": name.capitalize(),
         "file": f"docs/screens/json/{name}.spec.json", "sections": sections,
         "impl": {"total": impl[0], "done": impl[1]},
         "tests": {"total": tests[0], "passed": tests[1], "failed": tests[2], "running": tests[3]},
         "bucket": bucket, "updatedAt": T0}
    if by:
        s["by"] = by
    return s


def task(tid, subject, status="pending", owner=None, blocked_by=(), spec_id=None, sid=S_A0):
    t = {"key": f"{sid}#{tid}", "sessionId": sid, "id": str(tid), "subject": subject, "status": status,
         "blocks": [], "blockedBy": [str(b) for b in blocked_by], "createdAt": T0}
    if owner:
        t["owner"] = owner
    if spec_id:
        t["specId"] = spec_id
    if status in ("in_progress", "completed"):
        t["startedAt"] = T0 + 1000
    if status == "completed":
        t["completedAt"] = T0 + 5000
    return t


def perm(pid, agent_id, tool, summary, status="pending", can_relay=True, **kw):
    p = {"id": pid, "sessionId": S_A0, "agentId": agent_id, "toolName": tool, "summary": summary,
         "preview": f"{tool} {summary}", "status": status, "createdAt": T0 + 2000,
         "can": {"allowDeny": can_relay, "always": False, "reason": False}}
    p.update(kw)
    return p


def sheet_for(name):
    """spec.sheet's cards for one spec (the shape of sheet.py's build_doc)."""
    return {"metadata": {"name": name.capitalize(), "displayName": f"{name} 画面", "description": f"{name} の画面",
                         "platforms": ["ios", "android", "web"], "layoutFile": name},
            "components": [["View", f"{name}_root", "View"], ["Label", "title_label", "  Label"], ["TextField", "email_input", "  TextField"],
                           ["Button", "submit_button", "  Button"], ["Label", "<b>escaped</b>", "  Label"]],
            "layoutChildren": [f"{name}_root", "title_label", "email_input", "submit_button", "<b>escaped</b>"],
            "uiVariables": [["email", "String", '""'], ["isLoading", "Bool", "false"], ["error", "String?", "null"]],
            "eventHandlers": [["onSubmit", "送信する"]], "vmMethods": ["load()", "submit()", "validate()", "reset()"],
            "vmVars": ["email"], "repositories": ["AuthRepository"], "apis": [["login", "POST", "/auth/login"]],
            "userActions": [["送信を押す", "submit()"], ["入力する", "validate()"]],
            "transitions": [["submit() 成功", "Home"], ["戻る", "Top"]],
            "branches": [["submit", "成功", "Home へ"], ["submit", "失敗", "エラーを表示"], ["validate", "空", "ボタンを無効"]],
            "related": [["Layout", f"docs/screens/layouts/{name}.json", True], ["Test", f"tests/screens/{name}.test.json", False]],
            "impl": {"total": 12, "done": 4}}


def work():
    """One JsonUI project with ten specs (the big board), a session and its define subagent, three tasks (one
    waiting on another), a test run and two permission prompts (one through a relay, one without).
    Marks: start, progress, terminal, end."""
    P = [project("p-shop", "shop-app", 0), project("p-cli", "jsonui-cli", 1, jsonui=False)]
    S = [session(S_A0, "a0", "p-shop", "shop-app"), session(S_4F, "4f", "p-cli", "jsonui-cli")]
    A = [agent(S_A0, "a0", S_A0, state="phone", act="Bash xcodebuild test（iPhone 16（iOS 26.2））"),
         agent(SUB_A3, "a3", S_A0, kind="sub", role="define", state="typing", act="Write docs/screens/json/login.spec.json", agent_type="jsonui-define"),
         agent(S_4F, "4f", S_4F, state="idle", act="待機")]
    login = f"p-shop:docs/screens/json/login.spec.json"
    specs = [spec("login", by=SUB_A3, writing="stateManagement", bucket="live", items=[5, 6, 2, 0, 0, 0, 0], state="written")]
    specs += [spec(n, impl=(12, 4 + k), tests=(3, k % 4, 0, False)) for k, n in enumerate(SCREENS[1:])]
    tasks = [task(1, "文言を strings.json に登録"), task(2, "Login 画面の spec を書く", "in_progress", owner=SUB_A3, spec_id=login),
             task(3, "Login 画面を実装", blocked_by=[2], spec_id=login)]
    run = {"id": "run-1", "projectId": "p-shop", "agentId": S_A0, "platform": "ios", "command": "xcodebuild test -scheme ShopApp",
           "status": "running", "startedAt": T0 + 1000, "deviceId": "dev-1",
           "cases": [{"name": "初期表示", "status": "passed"}, {"name": "ログイン失敗", "status": "running"}, {"name": "<script>x</script>", "status": "pending"}]}
    devices = [{"id": "dev-1", "platform": "ios", "name": "iPhone 16（iOS 26.2）", "state": "booted", "busyBy": S_A0}]
    hook = {"allowDeny": True, "always": True, "reason": True}   # a synchronous --decide hook is waiting (P6)
    sugg = [{"type": "addRules", "rules": [{"toolName": "Bash", "ruleContent": "npm test:*"}], "behavior": "allow", "destination": "localSettings"},
            {"type": "addRules", "rules": [{"toolName": "Bash", "ruleContent": "npm:*"}], "behavior": "allow", "destination": "projectSettings"}]
    perms = [perm("perm-1", SUB_A3, "Write", "docs/screens/json/login.spec.json", can_relay=True),
             perm("perm-2", S_A0, "Bash", "xcodebuild test -scheme ShopApp", can_relay=False),
             perm("perm-3", S_4F, "Bash", "npm test -- --progress", sessionId=S_4F, can=hook, suggestions=sugg),
             perm("perm-4", S_4F, "Bash", "rm -rf build", sessionId=S_4F, can=dict(hook, always=False))]   # as the server: always = has suggestions
    items = [{"sheets": {s["id"]: sheet_for(s["id"].split("/")[-1].replace(".spec.json", "")) for s in specs}},
             {"mark": "start"}, slices(0, projects=P, sessions=S, agents=A, specs=specs, tasks=tasks, tests=[run], devices=devices, perms=perms, server=server_slice())]
    # progress: the spec is written, task 2 done (3 can start), the run finishes with one failure
    specs2 = [spec("login", items=[5, 6, 4, 3, 2, 2, 3], bucket="partial")] + specs[1:]
    tasks2 = [tasks[0], task(2, "Login 画面の spec を書く", "completed", owner=SUB_A3, spec_id=login), tasks[2]]
    run2 = dict(run, status="failed", summary="2 passed, 1 failed", endedAt=T0 + 9000,
                cases=[{"name": "初期表示", "status": "passed"}, {"name": "ログイン失敗", "status": "passed"}, {"name": "<script>x</script>", "status": "failed"}])
    items += [{"mark": "progress"}, slices(5, specs=specs2, tasks=tasks2, tests=[run2])]
    items += [{"mark": "terminal"}, slices(8, perms=[perm("perm-1", SUB_A3, "Write", "docs/screens/json/login.spec.json", status="sent", sentBehavior="allow"),
                                                      perm("perm-2", S_A0, "Bash", "xcodebuild test -scheme ShopApp", status="answered_in_terminal", can_relay=False,
                                                           terminalBehavior="allow", decidedAt=T0 + 7000, decidedBy="terminal")])]
    items.append({"mark": "end"})
    return items


def heavy(seconds=90, rate=5):
    """Load for P4 (plan 10 §7): 20 sessions (60 robots) in 6 projects, 300 tasks, 300 specs; `rate` times a
    second a spec section changes state, a task moves, a robot changes what it does. Played by --autoplay."""
    import random
    random.seed(11)
    names = ["shop-app", "jsonui-cli", "JsonUIDocument", "admin-web", "client-ios", "tools"]
    P = [project(f"p{k}", n, k, jsonui=k != 1) for k, n in enumerate(names)]
    S, A = [], []
    for i in range(20):
        sid = f"{i:02x}000000-0000-4000-8000-{i:012x}"
        S.append(session(sid, f"{i:02x}", f"p{i % 6}", names[i % 6]))
        A.append(agent(sid, f"{i:02x}", sid, state="typing", act="Edit docs/screens/layouts/x.json"))
        for k in range(2):
            A.append(agent(f"{i:02x}s{k}", f"{i:02x}{'ab'[k]}", sid, kind="sub", role=random.choice(["define", "implement", "test"]),
                           state=random.choice(["typing", "reading", "command"]), act="Read docs/screens/json/x.spec.json", agent_type="jsonui-define"))
    specs = []
    for j in range(300):
        pid = f"p{[0, 2, 3, 4, 5][j % 5]}"
        s = spec(f"s{j:03d}", impl=(10, j % 11), tests=(3, j % 4, 0, False), bucket=random.choice(["partial", "todo", "done"]))
        s.update(id=f"{pid}:docs/screens/json/s{j:03d}.spec.json", projectId=pid, file=f"docs/screens/json/s{j:03d}.spec.json")
        specs.append(s)
    tasks = []
    for j in range(300):
        sid = S[j % 20]["id"]
        t = task(j // 20 + 1, f"タスク {j}", random.choice(["pending", "in_progress", "completed"]), sid=sid,
                 blocked_by=[j // 20] if j // 20 and random.random() < 0.3 else ())
        tasks.append(t)
    items = [{"mark": "start"}, slices(0, projects=P, sessions=S, agents=A, specs=specs, tasks=tasks, server=server_slice())]
    t = 1.0
    for n in range(int(seconds * rate)):
        j = random.randrange(300)
        specs[j] = dict(specs[j], bucket="live", by=A[(j * 3) % 60]["id"],
                        sections=[dict(q, state="writing" if k == n % 7 else q["state"]) for k, q in enumerate(specs[j]["sections"])])
        tasks[n % 300] = dict(tasks[n % 300], status=random.choice(["pending", "in_progress", "completed"]))
        a = A[n % 60]
        A[n % 60] = dict(a, state=random.choice(["typing", "reading", "command", "idle"]), act=f"Edit docs/screens/layouts/s{n % 300:03d}.json")
        items.append(slices(t, specs=list(specs), tasks=list(tasks), agents=list(A)))
        t += 1 / rate
    return items


def floors():
    """The building (10-18 live check): 18 projects, one session each, every robot idle except the one in the last
    project by order (it works) and one in p13 that waits for permission — so 3 floors of six, and the two active
    rooms must be on 1F although they come late by order."""
    P = [project(f"p{k:02d}", f"proj-{k:02d}", k) for k in range(18)]
    S, A = [], []
    for k in range(18):
        sid = f"f{k:07x}-0000-4000-8000-{k:012x}"
        S.append(session(sid, f"f{k:x}", f"p{k:02d}", f"proj-{k:02d}", status="busy" if k == 17 else "idle"))
        A.append(agent(sid, f"f{k:x}", sid, state="typing" if k == 17 else "waiting" if k == 13 else "idle",
                       act="Edit src/app.ts" if k == 17 else ""))
    p13 = perm("perm-f13", S[13]["id"], "Bash", "npm test", sessionId=S[13]["id"])
    later = [dict(x) for x in A]
    later[16] = dict(later[16], state="typing", act="Edit src/late.ts")   # 1F is full: a room on 3F starts working
    return [{"mark": "start"}, slices(0, projects=P, sessions=S, agents=A, perms=[p13], server=server_slice()),
            {"mark": "later"}, slices(1, agents=later)]


def building():
    """The building's look (10-18): ten rooms with long, similar names (1F six, 2F four — two empty bays), first
    everyone idle, then rooms working and one waiting for permission."""
    names = ["harbor-booking-site", "harbor-booking-admin", "tea-finder-agent", "tea-finder-ios", "aurora_base_flutter",
             "aurora_base_android2", "nimbus_server", "nimbus_android", "JsonUI-Agents-for-claude", "jsonui-cli"]
    P = [project(f"b{k:02d}", n, k) for k, n in enumerate(names)]
    import time
    now = int(time.time() * 1000)
    since = {0: now - 9 * 3600_000, 1: now - 9 * 3600_000, 6: now - 9 * 3600_000, 2: now - 3600_000}   # the rest: none (not guessed)
    S, A = [], []
    for k, n in enumerate(names):
        sid = f"b{k:07x}-0000-4000-8000-{k:012x}"
        S.append(dict(session(sid, f"b{k:x}", f"b{k:02d}", n, status="idle"), **({"since": since[k]} if k in since else {})))
        A.append(agent(sid, f"b{k:x}", sid, state="idle"))
    mixed = [dict(a) for a in A]
    for k in (1, 4, 8):
        mixed[k] = dict(mixed[k], state="typing", act="Edit src/app.ts")
    mixed[6] = dict(mixed[6], state="waiting")
    mixed[9] = dict(mixed[9], state="thinking", act="考え中")              # busy and quiet: thinking (lit, its own pose)
    p6 = perm("perm-b6", S[6]["id"], "Bash", "npm test", sessionId=S[6]["id"])
    heavy = [dict(x) for x in S]
    heavy[1] = dict(heavy[1], heavy=["tokens"], heavyInfo={"tokensPerMin": 3200, "toolSec": 0, "subagents": 0})   # fast typing and sweat
    heavy[6] = dict(heavy[6], heavy=["tool"])            # heavy, but waiting for permission: no sweat
    return [{"mark": "idle"}, slices(0, projects=P, sessions=S, agents=A, server=server_slice()),
            {"mark": "mixed"}, slices(1, agents=mixed, perms=[p6], sessions=heavy)]
