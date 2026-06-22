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


def _rbenv_version_installed(version: str) -> bool:
    """Return True if *version* is installed under rbenv.

    rbenv keeps each Ruby at ``$RBENV_ROOT/versions/<version>`` (default
    ``~/.rbenv/versions/<version>``) — the same directory rbenv itself
    consults — so a cheap ``is_dir()`` check avoids shelling out to rbenv
    (which may not even be on $PATH at this point).
    """
    rbenv_root = os.environ.get("RBENV_ROOT") or os.path.join(
        os.path.expanduser("~"), ".rbenv"
    )
    return (Path(rbenv_root) / "versions" / version).is_dir()


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
    local Ruby toolchain is used — but ONLY when that exact version is
    actually installed under rbenv. ``extra`` is merged on top (e.g.
    ``JUI_SKIP_EXISTING=1`` for non-interactive invocations).
    """
    env_overrides: dict[str, str] = {}

    if resolved != tool_name:
        tool_dir = Path(resolved).resolve().parent.parent  # bin/{tool} -> {tool}_tools/
        ruby_version_file = tool_dir / ".ruby-version"
        if ruby_version_file.exists():
            pinned = ruby_version_file.read_text().strip()
            # Only force RBENV_VERSION when that exact Ruby is installed.
            # The bundled `.ruby-version` pins the maintainer's dev Ruby
            # (e.g. 3.2.2); forcing it unconditionally hard-fails `jui build`
            # for every consumer who lacks that exact patch
            # ("rbenv: version `3.2.2' is not installed (set by
            # RBENV_VERSION environment variable)"). When it's absent we omit
            # the override and let rbenv resolve the consumer's own
            # .ruby-version / global Ruby, which runs the tool fine.
            if pinned and _rbenv_version_installed(pinned):
                env_overrides["RBENV_VERSION"] = pinned

    if extra:
        env_overrides.update(extra)

    if not env_overrides:
        return None
    return {**os.environ, **env_overrides}
