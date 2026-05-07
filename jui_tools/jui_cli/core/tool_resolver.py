"""Shared helpers for invoking project-local platform tools.

Each JsonUI project may install `sjui_tools/bin/sjui`, `kjui_tools/bin/kjui`,
or `rjui_tools/bin/rjui` *locally* rather than on $PATH. Both the
per-platform build step and the auto-converter step need the same lookup
logic, so it lives here.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping


# Max number of parent directories to walk when searching for a local
# `{tool}_tools/bin/{tool}` installation. Ten is deep enough to cover
# nested monorepos without risking an unbounded walk.
_MAX_PARENT_HOPS = 10


def resolve_tool(tool_name: str, cwd: Path) -> str:
    """Return an absolute path to a project-local tool, or the bare name.

    Walks up from ``cwd`` looking for ``{tool_name}_tools/bin/{tool_name}``
    and also ``jsonui-cli/{tool_name}_tools/bin/{tool_name}`` (used when
    the jsonui-cli checkout is a sibling of the project). Falls back to
    ``tool_name`` so the caller's ``subprocess.run`` can still do a
    $PATH lookup when no local install is present.
    """
    search = cwd
    for _ in range(_MAX_PARENT_HOPS):
        local = search / f"{tool_name}_tools" / "bin" / tool_name
        if local.exists():
            return str(local)
        cli_local = search / "jsonui-cli" / f"{tool_name}_tools" / "bin" / tool_name
        if cli_local.exists():
            return str(cli_local)
        parent = search.parent
        if parent == search:
            break
        search = parent
    return tool_name


def build_tool_env(
    resolved: str,
    tool_name: str,
    *,
    extra: Mapping[str, str] | None = None,
) -> dict[str, str] | None:
    """Build a subprocess env that includes ``RBENV_VERSION`` when relevant.

    Returns ``None`` when no env tweaking is needed and there are no
    ``extra`` vars — callers pass ``env=None`` to ``subprocess.run`` so the
    child inherits the parent env unmodified.

    When ``resolved`` is a project-local tool path and the tool directory
    has a ``.ruby-version`` file, ``RBENV_VERSION`` is exported so the
    local Ruby toolchain is used. ``extra`` is merged on top (e.g.
    ``JUI_SKIP_EXISTING=1`` for non-interactive invocations).
    """
    env_overrides: dict[str, str] = {}

    if resolved != tool_name:
        tool_dir = Path(resolved).resolve().parent.parent  # bin/{tool} -> {tool}_tools/
        ruby_version_file = tool_dir / ".ruby-version"
        if ruby_version_file.exists():
            env_overrides["RBENV_VERSION"] = ruby_version_file.read_text().strip()

    if extra:
        env_overrides.update(extra)

    if not env_overrides:
        return None
    return {**os.environ, **env_overrides}
