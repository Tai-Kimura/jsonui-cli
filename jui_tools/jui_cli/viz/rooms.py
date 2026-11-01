"""cwd → project (a room). Design: 04 §4.

The root is the nearest folder upwards holding jui.config.json (a JsonUI
project), else the nearest holding .git, else the cwd itself. Each cwd is
walked once and cached. The id is a hash of the root, so the path itself is
not sent to the page; ``displayRoot`` shows it with the home folder as ``~``.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path


def tilde(path: str) -> str:
    home = str(Path.home())
    if path == home:
        return "~"
    if path.startswith(home + os.sep):
        return "~" + path[len(home):]
    return path


def find_root(cwd: str) -> tuple[str, bool]:
    """(root, is_jsonui) for a cwd. Never raises: an unreadable cwd is its own root."""
    try:
        start = Path(cwd)
        if not start.is_absolute():
            return cwd, False
        git_root = None
        for folder in (start, *start.parents):
            if (folder / "jui.config.json").is_file():
                return str(folder), True
            if git_root is None and (folder / ".git").exists():
                git_root = folder
        return (str(git_root) if git_root else cwd), False
    except OSError:
        return cwd, False


class Rooms:
    def __init__(self) -> None:
        self._roots: dict[str, tuple[str, bool]] = {}
        self.projects: dict[str, dict] = {}
        # The Slack intake's folder (slack_room.py): a session working anywhere in it is the sorting factory's robot,
        # in a room of its own marked "factory" (the page reaches it from the header's Slack, never from the floors).
        self.factory_dir: str | None = None

    def _factory_root(self, cwd: str) -> str | None:
        top = (self.factory_dir or "").rstrip(os.sep)
        return top if top and (cwd == top or cwd.startswith(top + os.sep)) else None

    def set_factory_dir(self, folder: str | None) -> bool:
        """The intake's folder changed: its cwds are walked again. True when it changed."""
        if folder == self.factory_dir:
            return False
        old = self.factory_dir
        self.factory_dir = folder
        for cwd in [c for c in self._roots if any(t and (c == t or c.startswith(t.rstrip(os.sep) + os.sep)) for t in (old, folder))]:
            del self._roots[cwd]
        return True

    def project_for(self, cwd: str) -> dict:
        if cwd not in self._roots:
            factory = self._factory_root(cwd)
            self._roots[cwd] = (factory, False) if factory else find_root(cwd)
        root, jsonui = self._roots[cwd]
        pid = hashlib.sha1(root.encode("utf-8")).hexdigest()[:12]
        project = self.projects.get(pid)
        if project is None:
            name = (os.path.basename(root.rstrip(os.sep)) or root) + "/"
            project = {
                "id": pid, "name": name, "displayRoot": tilde(root),
                "jsonui": jsonui, "order": len(self.projects),
            }
            self.projects[pid] = project
        factory = root == (self.factory_dir or "").rstrip(os.sep)
        if project.get("factory", False) != factory:
            if factory:
                project["factory"] = True
            else:
                project.pop("factory", None)
        return project

    def root_of(self, project_id: str) -> str | None:
        for root, _ in self._roots.values():
            if hashlib.sha1(root.encode("utf-8")).hexdigest()[:12] == project_id:
                return root
        return None
