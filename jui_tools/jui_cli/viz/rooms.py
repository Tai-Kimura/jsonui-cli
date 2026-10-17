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

    def project_for(self, cwd: str) -> dict:
        if cwd not in self._roots:
            self._roots[cwd] = find_root(cwd)
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
        return project

    def root_of(self, project_id: str) -> str | None:
        for root, _ in self._roots.values():
            if hashlib.sha1(root.encode("utf-8")).hexdigest()[:12] == project_id:
                return root
        return None
