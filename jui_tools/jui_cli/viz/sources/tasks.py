"""Tasks for the task board. Design: 09 §5.

Three ways in, all optional:
  * TodoWrite — what models actually use here (P0: the Task tools were off
    and ~/.claude/tasks/ did not exist even with CLAUDE_CODE_ENABLE_TODO_TOOLS=1).
    Each call carries the session's whole list, so it replaces that session's
    TodoWrite tasks.
  * TaskCreated / TaskCompleted hooks.
  * ~/.claude/tasks/<session id>/<n>.json files, when present.
"""
from __future__ import annotations

import json
from pathlib import Path

STATUSES = ("pending", "in_progress", "completed")
MAX_TEXT = 200


def _t(value, n: int = MAX_TEXT) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    value = " ".join(value.split())
    return value if len(value) <= n else value[: n - 1] + "…"


class TaskBook:
    def __init__(self) -> None:
        self.tasks: dict[str, dict] = {}

    def _put(self, sid: str, tid: str, at: int, **fields) -> dict:
        key = f"{sid}#{tid}"
        task = self.tasks.get(key)
        if task is None:
            task = {"key": key, "sessionId": sid, "id": tid, "subject": "", "status": "pending",
                    "blocks": [], "blockedBy": [], "createdAt": at}
            self.tasks[key] = task
        before = task.get("status")
        for k, v in fields.items():
            if v is not None:
                task[k] = v
        if task["status"] == "in_progress" and before != "in_progress":
            task.setdefault("startedAt", at)
        if task["status"] == "completed" and before != "completed":
            task["completedAt"] = at
        return task

    def from_todowrite(self, sid: str, owner: str, todos, at: int) -> None:
        if not isinstance(todos, list):
            return
        keep = set()
        for i, todo in enumerate(todos):
            if not isinstance(todo, dict):
                continue
            status = todo.get("status") if todo.get("status") in STATUSES else "pending"
            tid = f"todo-{i + 1}"
            keep.add(f"{sid}#{tid}")
            self._put(sid, tid, at, subject=_t(todo.get("content")) or "", status=status,
                      activeForm=_t(todo.get("activeForm")), owner=owner)
        for key in [k for k, t in self.tasks.items() if t["sessionId"] == sid and t["id"].startswith("todo-") and k not in keep]:
            del self.tasks[key]

    def created(self, sid: str, payload: dict, owner: str, at: int) -> None:
        tid = payload.get("task_id")
        if isinstance(tid, (str, int)):
            self._put(sid, str(tid), at, subject=_t(payload.get("task_subject")) or "",
                      description=_t(payload.get("task_description"), 500), owner=owner)

    def completed(self, sid: str, payload: dict, at: int) -> None:
        tid = payload.get("task_id")
        if isinstance(tid, (str, int)) and f"{sid}#{tid}" in self.tasks:
            self._put(sid, str(tid), at, status="completed")

    def from_file(self, path: Path, at: int) -> None:
        """~/.claude/tasks/<session id>/<n>.json"""
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if not isinstance(data, dict):
            return
        sid = path.parent.name
        tid = str(data.get("id") or path.stem)
        status = data.get("status") if data.get("status") in STATUSES else None
        self._put(sid, tid, at, subject=_t(data.get("subject")) or "", status=status,
                  activeForm=_t(data.get("activeForm")), description=_t(data.get("description"), 500),
                  owner=_t(data.get("owner")),
                  blocks=[str(x) for x in data.get("blocks") or [] if isinstance(x, (str, int))],
                  blockedBy=[str(x) for x in data.get("blockedBy") or [] if isinstance(x, (str, int))])

    def drop_session(self, sid: str) -> None:
        for key in [k for k, t in self.tasks.items() if t["sessionId"] == sid]:
            del self.tasks[key]

    def link_specs(self, names: dict[str, str]) -> None:
        """Set specId when exactly one spec name appears in the task's text. names: lowercase name -> spec id."""
        for task in self.tasks.values():
            text = f"{task.get('subject', '')} {task.get('description', '')}".lower()
            hits = {sid for name, sid in names.items() if len(name) >= 3 and name in text}
            if len(hits) == 1:
                task["specId"] = next(iter(hits))
            else:
                task.pop("specId", None)

    def items(self) -> list[dict]:
        return sorted((dict(t) for t in self.tasks.values()), key=lambda t: (t["sessionId"], t.get("createdAt", 0), t["id"]))
