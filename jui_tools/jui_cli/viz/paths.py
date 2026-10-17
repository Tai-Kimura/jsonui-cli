"""Where ``jui viz`` keeps its runtime files and where Claude Code keeps its own.

Every path is built from ``Path.home()`` on each call, never at import time,
so a test can point HOME at a temporary folder.
"""
from __future__ import annotations

from pathlib import Path


def viz_home() -> Path:
    return Path.home() / ".jsonui-cli" / "viz"


def pid_file() -> Path:
    return viz_home() / "viz.pid"


def server_json() -> Path:
    return viz_home() / "server.json"


def config_json() -> Path:
    return viz_home() / "config.json"


def backups_dir() -> Path:
    return viz_home() / "backups"


def claude_home() -> Path:
    return Path.home() / ".claude"


def claude_settings() -> Path:
    return claude_home() / "settings.json"


def claude_sessions_dir() -> Path:
    # Holds <pid>.json (read) and <pid>.<hash>.key (peer tokens: never read).
    return claude_home() / "sessions"


def claude_tasks_dir() -> Path:
    return claude_home() / "tasks"
