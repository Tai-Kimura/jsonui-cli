"""Where ``jui viz`` keeps its runtime files and where Claude Code keeps its own.

Every path is built from the environment on each call, never at import time,
so a test can point HOME (or JUI_VIZ_HOME) at a temporary folder.

The runtime files live OUTSIDE the install folder (~/.jsonui-cli), because
the bootstrap installer replaces that folder wholesale on every release
(``rm -rf`` + clone): server.json and viz.pid vanished under a running server
(an orphan no command could stop), and backups/ — the only copy of
~/.claude/settings.json from before ``hooks install`` — went with them.

The folder, in order:
  1. ``$JUI_VIZ_HOME`` when it is an absolute path;
  2. ``$XDG_STATE_HOME/jui-viz`` when XDG_STATE_HOME is an absolute path
     (the XDG spec: a relative value is invalid and ignored);
  3. ``$HOME/.local/state/jui-viz``.

⚠️ The same rule is written out in four more places that cannot import this
module: viz/forward.py and viz/channel.py (run with ``python3 -I -S``, copied
byte for byte into plugins/jui-viz/scripts/), plugins/jui-viz/scripts/
session_env.sh, and installer/bootstrap.sh (``viz_state_home``).
tests/test_viz_state_home.py runs all of them against the same environments.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

HOME_ENV = "JUI_VIZ_HOME"
STATE_ENV = "XDG_STATE_HOME"


def viz_home() -> Path:
    override = os.environ.get(HOME_ENV, "")
    if os.path.isabs(override):
        return Path(override)
    state = os.environ.get(STATE_ENV, "")
    if os.path.isabs(state):
        return Path(state) / "jui-viz"
    return Path.home() / ".local" / "state" / "jui-viz"


def legacy_viz_home() -> Path:
    """Where 2.1.0 and earlier kept the runtime files: inside the install folder."""
    return Path.home() / ".jsonui-cli" / "viz"


def migrate_legacy() -> list[str]:
    """Move what the legacy folder holds into viz_home(). Returns the names moved.

    A name that already exists in the new folder is left where it is (never
    overwritten). The legacy folder is removed once it is empty. bootstrap.sh
    does the same before it deletes the install folder, since that runs
    before any viz command could.
    """
    old, new = legacy_viz_home(), viz_home()
    if not old.is_dir() or old.is_symlink():
        return []
    try:
        if old.resolve() == new.resolve():
            return []
    except OSError:
        return []
    new.mkdir(parents=True, exist_ok=True, mode=0o700)
    moved: list[str] = []
    for child in sorted(old.iterdir()):
        target = new / child.name
        if target.exists() or target.is_symlink():
            continue
        try:
            shutil.move(str(child), str(target))
            moved.append(child.name)
        except OSError:
            continue
    try:
        old.rmdir()
    except OSError:
        pass
    return moved


def pid_file() -> Path:
    return viz_home() / "viz.pid"


def server_json() -> Path:
    return viz_home() / "server.json"


def config_json() -> Path:
    return viz_home() / "config.json"


def backups_dir() -> Path:
    return viz_home() / "backups"


def progress_dir() -> Path:
    return viz_home() / "test-progress"


def legacy_progress_dir() -> Path:
    return legacy_viz_home() / "test-progress"


def claude_home() -> Path:
    return Path.home() / ".claude"


def claude_settings() -> Path:
    return claude_home() / "settings.json"


def claude_sessions_dir() -> Path:
    # Holds <pid>.json (read) and <pid>.<hash>.key (peer tokens: never read).
    return claude_home() / "sessions"


def claude_tasks_dir() -> Path:
    return claude_home() / "tasks"
