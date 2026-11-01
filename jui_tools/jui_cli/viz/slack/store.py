"""The folders of <orchestrationDir> (design §7) and the small state files under .state/.

    inbox/<ts>-<workspace>-<channel>.json            raw, as fetched (local only); deleted once filtered and placed
    projects/<projectId>/<ts>-<workspace>-<channel>.json
    _unsorted/<ts>-<workspace>-<channel>.json        confidence under router.confidenceMin, or a choice not in the list
    tasks/                                           stage 2/3
    .state/cursor.json                               {"<workspace>/<channel>": "<last ts>"}
    .state/threads.json                              threads watched for new replies: {"<ws>/<ch>/<threadTs>": "<last reply ts>"}
    .state/routes.json                               where a thread went: {"<ws>/<ch>/<threadTs>": {to, choice, confidence}}
                                                     (no text; a thread routed as chitchat is never written here)
    .state/status.json                               last run, failures (written by the intake only)

Every write is a temporary dot-file renamed into place (the watcher skips dot-files), files 0600, folders 0700.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path

INBOX, PROJECTS, UNSORTED, TASKS, STATE = "inbox", "projects", "_unsorted", "tasks", ".state"
_TS = re.compile(r"^\d{1,12}\.\d{1,9}$")


def ensure(root: Path) -> None:
    for sub in ("", INBOX, PROJECTS, UNSORTED, TASKS, STATE):
        (root / sub).mkdir(parents=True, exist_ok=True, mode=0o700)


def valid_ts(ts) -> bool:
    return isinstance(ts, str) and bool(_TS.match(ts))


def file_name(ts: str, workspace: str, channel: str) -> str:
    return f"{ts}-{workspace}-{channel}.json"


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, tmp = tempfile.mkstemp(prefix=".w-", suffix=".json", dir=str(path.parent))
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return default


def inbox_files(root: Path) -> list[Path]:
    folder = root / INBOX
    try:
        return sorted(p for p in folder.iterdir() if p.suffix == ".json" and not p.name.startswith(".") and p.is_file())
    except OSError:
        return []


def counts(root: Path) -> dict:
    def n(folder: Path) -> int:
        try:
            return sum(1 for p in folder.iterdir() if p.suffix == ".json" and not p.name.startswith("."))
        except OSError:
            return 0
    projects = {}
    try:
        for d in sorted((root / PROJECTS).iterdir()):
            if d.is_dir() and not d.name.startswith("."):
                projects[d.name] = n(d)
    except OSError:
        pass
    return {"inbox": n(root / INBOX), "projects": projects, "unsorted": n(root / UNSORTED)}


class Cursor:
    def __init__(self, root: Path):
        self.path = root / STATE / "cursor.json"
        got = read_json(self.path, {})
        self.data: dict[str, str] = got if isinstance(got, dict) else {}

    def get(self, workspace: str, channel: str) -> str | None:
        value = self.data.get(f"{workspace}/{channel}")
        return value if valid_ts(value) else None

    def set(self, workspace: str, channel: str, ts: str) -> None:
        old = self.get(workspace, channel)
        if old is None or float(ts) > float(old):
            self.data[f"{workspace}/{channel}"] = ts
            write_json(self.path, self.data)


class KeyedState:
    """A small {key: value} file under .state/ whose keys end in a thread's ts (threads.json, routes.json)."""

    def __init__(self, root: Path, name: str):
        self.path = root / STATE / name
        got = read_json(self.path, {})
        self.data: dict = got if isinstance(got, dict) else {}
        self.dirty = False

    @staticmethod
    def key(workspace: str, channel: str, thread_ts: str) -> str:
        return f"{workspace}/{channel}/{thread_ts}"

    def get(self, key: str):
        return self.data.get(key)

    def set(self, key: str, value) -> None:
        if self.data.get(key) != value:
            self.data[key] = value
            self.dirty = True

    def prune(self, before: float) -> None:
        """Drop the threads started before ``before`` (epoch seconds)."""
        for key in list(self.data):
            ts = key.rsplit("/", 1)[-1]
            if not valid_ts(ts) or float(ts) < before:
                del self.data[key]
                self.dirty = True

    def save(self) -> None:
        if self.dirty:
            write_json(self.path, self.data)
            self.dirty = False
