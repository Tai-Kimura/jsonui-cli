"""Hook payloads, the agents list and session files → projects / sessions / agents / events.

Every entry point takes the time as an argument (``at``, epoch ms) instead of
reading a clock, so a recording replayed with its own timestamps rebuilds
the same state (the recorder's test depends on it).

Design: 03 (fields), 04 §1–§4 (slices, robot states, rooms).
"""
from __future__ import annotations

from typing import Any

from pathlib import Path

from . import robots
from .rooms import Rooms, tilde
from .sources.jsonui_project import JsonUIProject
from .sources.tasks import TaskBook
from .state import VizState

#: The 18 events the hooks are installed for; anything else is dropped.
KNOWN_EVENTS = frozenset({
    "SessionStart", "SessionEnd", "UserPromptSubmit", "PreToolUse", "PostToolUse",
    "PostToolUseFailure", "PermissionRequest", "PermissionDenied", "Notification",
    "SubagentStart", "SubagentStop", "TaskCreated", "TaskCompleted", "Stop",
    "StopFailure", "CwdChanged", "PreCompact", "PostCompact",
})
TOOL_EVENTS = frozenset({"PreToolUse", "PostToolUse", "PostToolUseFailure", "PermissionRequest", "PermissionDenied"})

PROMPT_MAX = 200
MESSAGE_MAX = 300
SUBAGENT_LINGER_MS = 5_000
DONE_TO_IDLE_MS = 3_000
CARRY_MS = 3_000
THINKING_AFTER_MS = 30_000
ENDED_LINGER_MS = 60_000
TEST_RUNS_KEPT = 50
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


def _head(text: Any, n: int) -> str | None:
    if not isinstance(text, str) or not text:
        return None
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1] + "…"


class World:
    def __init__(self, state: VizState, tool_input_max: int = 2000) -> None:
        self.state = state
        self.tool_input_max = tool_input_max
        self.rooms = Rooms()
        self.sessions: dict[str, dict] = {}
        self.agents: dict[str, dict] = {}
        # Robot bookkeeping the page does not need: open tool_use_ids, timers.
        self._open: dict[str, list[str]] = {}
        self._until: dict[str, tuple[int, str]] = {}  # agent id -> (time, state to go to)
        # The tool_use_id an agent was asking permission for. PermissionRequest
        # carries no tool_use_id and a refusal may send no PostToolUse (nor
        # PermissionDenied: measured in -p), so the next PreToolUse from that
        # agent settles it — otherwise the id stays open and the robot never idles.
        self._asking: dict[str, str] = {}
        self.pid_to_session: dict[int, str] = {}
        self.tasks = TaskBook()
        self.tests: dict[str, dict] = {}
        self.jsonui: dict[str, JsonUIProject] = {}
        self.jsonui_errors: dict[str, str] = {}
        self._dirty: set[str] = set()
        self._now = 0
        # Called with each JsonUIProject once it is loaded (serve starts its file watcher).
        self.on_project_loaded = None

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
                "cwd": tilde(cwd) if cwd else "?", "status": "idle", "relay": False,
                "startedAt": at, "updatedAt": at,
            }
            self.sessions[sid] = session
            self._dirty |= {"sessions", "projects"}
            self._main(sid, at)
            if project["jsonui"]:
                self.jsonui_project(project["id"], at)
        elif cwd and session["cwd"] == "?":
            self._move(session, cwd)
        return session

    def _move(self, session: dict, cwd: str) -> None:
        project = self.rooms.project_for(cwd)
        if session["projectId"] != project["id"] or session["cwd"] != tilde(cwd):
            session["projectId"] = project["id"]
            session["cwd"] = tilde(cwd)
            self._dirty |= {"sessions", "projects"}

    def _main(self, sid: str, at: int) -> dict:
        agent = self.agents.get(sid)
        if agent is None:
            agent = {
                "id": sid, "label": self.sessions[sid]["label"], "sessionId": sid, "kind": "main",
                "role": "main", "state": "idle", "act": "待機", "startedAt": at, "updatedAt": at,
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
                "state": "idle", "act": "起動", "startedAt": at, "updatedAt": at,
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
        if act is not None:
            agent["act"] = act
        for k, v in extra.items():
            if v is None:
                agent.pop(k, None)
            else:
                agent[k] = v
        agent["updatedAt"] = at
        self._dirty.add("agents")

    def _status(self, session: dict, status: str, at: int, waiting_for: str | None = None) -> None:
        if session["status"] != status or session.get("waitingFor") != waiting_for:
            session["status"] = status
            if waiting_for:
                session["waitingFor"] = waiting_for
            else:
                session.pop("waitingFor", None)
            self._dirty.add("sessions")
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
        self._dirty |= {"specs", "tasks"}
        if self.on_project_loaded is not None:
            self.on_project_loaded(loaded)
        return loaded

    def file_changed(self, project_id: str, path: str, at: int, by: str | None = None) -> None:
        """A spec, layout or test file changed (an edit by a robot, or the watcher)."""
        project = self.jsonui.get(project_id)
        if project is None:
            return
        target = Path(path)
        if target.name.endswith(".spec.json"):
            project.reload_spec(target, at, by)
        elif target.name.endswith(".test.json"):
            project.load_tests()
        for sid in project.specs_touching(path):
            if by:
                entry = project.specs[sid]
                entry.by, entry.by_until = by, at + 10_000
        self._dirty.add("specs")

    def _touch_files(self, session: dict, agent: dict, tool_input: dict, at: int, after: bool) -> None:
        path = tool_input.get("file_path") or tool_input.get("notebook_path")
        if not isinstance(path, str):
            return
        project = self.jsonui_project(session["projectId"], at)
        if project is None:
            return
        if after:
            self.file_changed(session["projectId"], path, at, by=agent["id"])
        else:
            hits = project.specs_touching(path)
            for sid in hits:
                entry = project.specs[sid]
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
        root = self.rooms.root_of(session["projectId"])
        aid = _s(payload.get("agent_id"))
        agent_type = _s(payload.get("agent_type"))
        agent = self._sub(sid, aid, agent_type, at) if aid else self._main(sid, at)
        tool = _s(payload.get("tool_name"))
        tool_input = payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {}
        use_id = _s(payload.get("tool_use_id"))
        cat = "tool" if kind in TOOL_EVENTS else "session"
        text = kind

        if kind == "SessionStart":
            if _s(payload.get("model")):
                session["model"] = payload["model"]
            if _s(payload.get("session_title")):
                session["title"] = _head(payload["session_title"], 120)
            self._status(session, "idle", at)
            self._open.pop(agent["id"], None)
            self._set(agent, at, "idle", "待機")
            text = f"出勤 {payload.get('source') or ''}".strip()
        elif kind == "SessionEnd":
            self._status(session, "ended", at)
            self._set(agent, at, "idle", "退勤", leftAt=at)
            text = f"退勤 {payload.get('reason') or ''}".strip()
        elif kind == "UserPromptSubmit":
            session["lastPrompt"] = _head(payload.get("prompt"), PROMPT_MAX)
            self._status(session, "busy", at)
            self._set(agent, at, "idle", "指示を受けた")
            text = f"指示 {session['lastPrompt'] or ''}".strip()
        elif kind == "PreToolUse" and tool:
            self._status(session, "busy", at)
            self._settle_asking(agent["id"])
            state = robots.state_for_tool(tool, tool_input)
            act = robots.act_for_tool(tool, tool_input, root)
            if use_id:
                self._open.setdefault(agent["id"], []).append(use_id)
            target = {"file": robots._rel(str(tool_input["file_path"]), root)} if _s(tool_input.get("file_path")) else None
            self._set(agent, at, state, act, target=target)
            if state == "carry":
                self._until[agent["id"]] = (at + CARRY_MS, "idle")
            if tool in EDIT_TOOLS:
                self._touch_files(session, agent, tool_input, at, after=False)
            if tool == "TodoWrite":
                self.tasks.from_todowrite(sid, agent["id"], tool_input.get("todos"), at)
                self._dirty.add("tasks")
            if state == "phone" and use_id:
                command = str(tool_input.get("command", ""))
                self.tests[use_id] = {
                    "id": use_id, "projectId": session["projectId"], "agentId": agent["id"],
                    "platform": robots.test_platform(command), "command": robots._clip(command, 200),
                    "status": "running", "startedAt": at,
                }
                for old in sorted(self.tests, key=lambda k: self.tests[k]["startedAt"])[:-TEST_RUNS_KEPT]:
                    del self.tests[old]
                self._dirty.add("tests")
            text = act
        elif kind in ("PostToolUse", "PostToolUseFailure") and tool:
            opened = self._open.get(agent["id"], [])
            if use_id in opened:
                opened.remove(use_id)
            if self._asking.get(agent["id"]) == use_id:
                self._asking.pop(agent["id"], None)
            if not opened and agent["state"] not in ("carry",):
                self._set(agent, at, "idle", agent["act"])
            failed = kind == "PostToolUseFailure"
            if tool in EDIT_TOOLS and not failed:
                self._touch_files(session, agent, tool_input, at, after=True)
            run = self.tests.get(use_id) if use_id else None
            if run is not None and run["status"] == "running":
                response = payload.get("tool_response")
                output = ""
                if isinstance(response, dict):
                    output = f"{response.get('stdout') or ''}\n{response.get('stderr') or ''}"
                elif isinstance(response, str):
                    output = response
                summary, passed, n_failed = robots.test_summary(output[-200_000:])
                run["status"] = "failed" if failed or (n_failed or 0) > 0 else "passed"
                if summary:
                    run["summary"] = summary
                run["endedAt"] = at
                self._dirty.add("tests")
            text = f"{'失敗' if failed else '完了'} {robots.act_for_tool(tool, tool_input, root)}"
        elif kind == "PermissionRequest":
            opened = self._open.get(agent["id"])
            if opened:
                self._asking[agent["id"]] = opened[-1]
            self._status(session, "waiting", at, "permission prompt")
            self._set(agent, at, "waiting", f"許可待ち {robots.act_for_tool(tool or '?', tool_input, root)}")
            cat = "perm"
            text = agent["act"]
        elif kind == "PermissionDenied":
            self._settle_asking(agent["id"])
            self._status(session, "busy", at)
            self._set(agent, at, "idle", f"拒否 {tool or ''}".strip())
            cat = "perm"
            text = agent["act"]
        elif kind == "Notification":
            ntype = _s(payload.get("notification_type")) or ""
            if ntype == "permission_prompt":
                self._status(session, "waiting", at, "permission prompt")
                self._set(agent, at, "waiting")
            elif ntype == "idle_prompt":
                self._status(session, "idle", at)
            text = f"通知 {ntype} {_head(payload.get('message'), 120) or ''}".strip()
        elif kind == "SubagentStart":
            self._set(agent, at, "idle", f"起動 {agent_type or ''}".strip())
            text = f"登場 {agent_type or aid}"
        elif kind == "SubagentStop":
            message = _head(payload.get("last_assistant_message"), MESSAGE_MAX)
            self._set(agent, at, "done", "完了", lastMessage=message, leftAt=at)
            self._until[agent["id"]] = (at + SUBAGENT_LINGER_MS, "gone")
            text = f"退場 {agent_type or aid}"
        elif kind in ("TaskCreated", "TaskCompleted"):
            if kind == "TaskCreated":
                self.tasks.created(sid, payload, agent["id"], at)
            else:
                self.tasks.completed(sid, payload, at)
            self._dirty.add("tasks")
            subject = _head(payload.get("task_subject"), 120) or ""
            if kind == "TaskCreated":
                self._set(agent, at, "carry", f"タスク {subject}")
                self._until[agent["id"]] = (at + CARRY_MS, "idle")
            else:
                self._set(agent, at, "done", f"完了 {subject}")
                self._until[agent["id"]] = (at + DONE_TO_IDLE_MS, "idle")
            cat = "task"
            text = f"{'タスク作成' if kind == 'TaskCreated' else 'タスク完了'} {subject}"
        elif kind in ("Stop", "StopFailure"):
            background = payload.get("background_tasks")
            busy = isinstance(background, list) and len(background) > 0
            self._status(session, "busy" if busy else "idle", at)
            message = _head(payload.get("last_assistant_message"), MESSAGE_MAX)
            self._open.pop(agent["id"], None)
            self._asking.pop(agent["id"], None)
            self._set(agent, at, "done", "バックグラウンド作業中" if busy else "完了", lastMessage=message)
            self._until[agent["id"]] = (at + DONE_TO_IDLE_MS, "idle")
            text = "停止（失敗）" if kind == "StopFailure" else "停止"
        elif kind == "CwdChanged" and cwd:
            self._move(session, cwd)
            self._set(agent, at, "carry", f"移動 {tilde(cwd)}")
            self._until[agent["id"]] = (at + CARRY_MS, "idle")
            text = f"移動 {tilde(cwd)}"
        elif kind in ("PreCompact", "PostCompact"):
            self._set(agent, at, act="整理中" if kind == "PreCompact" else agent["act"])
            text = "整理中" if kind == "PreCompact" else "整理完了"

        event = {
            "at": at, "sessionId": sid, "agentId": agent["id"], "kind": kind, "cat": cat,
            "text": robots._clip(text, 200),
        }
        if tool:
            event["tool"] = tool
        if tool_input:
            event["detail"] = clip_strings(tool_input, self.tool_input_max)
        return self.state.add_event(event)

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
            status = row.get("status")
            if status in ("busy", "idle", "waiting"):
                waiting_for = _s(row.get("waitingFor")) if status == "waiting" else None
                self._status(session, status, at, waiting_for)
            if isinstance(row.get("pid"), int):
                self.pid_to_session[row["pid"]] = sid
            if _s(row.get("name")) and not session.get("title"):
                session["title"] = _head(row["name"], 120)
                self._dirty.add("sessions")

    def apply_session_file(self, data: dict, at: int) -> None:
        """~/.claude/sessions/<pid>.json (never a .key file)."""
        self.apply_agents_list([data], at)

    # ---------------------------------------------------------------- time

    def tick(self, at: int) -> None:
        self._now = max(self._now, at)
        for project in self.jsonui.values():
            for entry in project.specs.values():
                due = [t for t in (entry.by_until, *entry.writing_until.values()) if t and t <= at]
                if due:
                    if entry.by_until and entry.by_until <= at:
                        entry.by, entry.by_until = None, 0
                    entry.writing_until = {k: t for k, t in entry.writing_until.items() if t > at}
                    self._dirty.add("specs")
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
                agent = self.agents.get(sid)
                if agent and agent["state"] == "idle" and at - agent["updatedAt"] >= THINKING_AFTER_MS and agent["act"] != "考え中":
                    agent["act"] = "考え中"
                    self._dirty.add("agents")

    # ---------------------------------------------------------------- publish

    def publish(self) -> None:
        """Write the changed slices into the state store (sorted for stable output)."""
        if "projects" in self._dirty:
            used = {s["projectId"] for s in self.sessions.values()}
            projects = [p for p in self.rooms.projects.values() if p["id"] in used]
            self.state.set_slice("projects", sorted(projects, key=lambda p: p["order"]))
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
            self.state.set_slice("tests", sorted((dict(t) for t in self.tests.values()), key=lambda t: t["startedAt"]))
        self._dirty.clear()
