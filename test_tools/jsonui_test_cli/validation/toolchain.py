"""Is the toolchain this project vendored the one that is running?

`jui sync_tool` copies the platform tools into a project and stamps
`<project>/.jsonui-cli/sync-meta.json` with the version it copied. The CLI
running the gate knows its own version. When the two disagree, the
distribution arrived and the sync was never run — the project is building
with one toolchain and being validated by another.

Nothing checked it, so consumers were about to. Seven faces asked whether to
add `sync-meta.version != $(jsonui-test --version)` to their pretest, which
is the signal that the tool is missing a feature: the same shell line copied
into N projects is N places to keep in step, and both values already live
inside the tool. A project should not have to recompute what the tool knows.

Reported as a WARNING and counted, unlike the notice a declined check
prints. The difference is that this one names a command that clears it. A
warning nobody can act on is the kind that teaches people to stop reading;
a warning with a one-line remedy is supposed to keep saying so until the
line is run.
"""

from __future__ import annotations

import json
from pathlib import Path

SYNC_META_RELPATH = Path(".jsonui-cli") / "sync-meta.json"

#: What `jui sync_tool` writes when it cannot name a version. Comparing
#: against it would report a mismatch on every run of a project whose stamp
#: predates versioned stamping, which is not the state this looks for.
UNKNOWN = "unknown"


def sync_meta_mismatches(project_root, running_version: str) -> list[str]:
    """One message per platform whose stamped version is not the running one.

    Silent when there is no stamp: a project that does not vendor the tools
    has nothing to keep in step, and a gate that fires on the absence of an
    optional file would be reporting on the majority of projects.
    """
    if project_root is None or not running_version:
        return []
    meta_path = Path(project_root) / SYNC_META_RELPATH
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    platforms = meta.get("platforms")
    if not isinstance(platforms, dict):
        return []

    out: list[str] = []
    for platform in sorted(platforms):
        entry = platforms[platform]
        if not isinstance(entry, dict):
            continue
        stamped = entry.get("version")
        if not isinstance(stamped, str) or not stamped or stamped == UNKNOWN:
            continue
        if stamped == running_version:
            continue
        tool = entry.get("tool") or platform
        out.append(
            f"{tool} in this project was synced from {stamped}, but this "
            f"CLI is {running_version} — the distribution arrived and "
            f"`jui sync_tool` was not run, so the project builds with one "
            f"toolchain and is validated by another. Run `jui sync_tool` "
            f"(then re-run this gate), or ignore it if the older tools are "
            f"deliberate."
        )
    return out
