"""Is the toolchain a project vendored the one that is running?

`jui sync_tool` copies the platform tools into a project and stamps
`<project>/.jsonui-cli/sync-meta.json` with the version it copied. The CLI
running knows its own version. When the two disagree, the distribution
arrived and the sync was never run — the project builds with one toolchain
and is validated by another.

🚨 THIS LIVES HERE BECAUSE TWO COMMANDS MUST ANSWER IT THE SAME WAY. Until
2026-09-08 the rule sat inside `jsonui_test_cli`, and its ONLY production
caller was `jsonui-test` (`cli.py:201`; references from `jui_tools`: 0).
`jui build` never asked. That matters because `jui build` is the first stage
of the delivery script, so the path that ships was the path that could not
see the split:

    face measured 2026-09-08   sync-meta 1.8.54 / running CLI 1.8.55
    `jui build`                EXIT 0, warnings 0, tree diff 0

⚠️ That `warnings 0` did not mean "not split". It meant "the split was not
looked at" — the delivery lane's phrasing, and the reason this moved rather
than being copied. A rule written twice becomes two rules; the two callers
here disagree by construction unless they read one module.

The distribution carries `shared/core/*.py`, so both callers can reach this
in an installed tree, not only in a checkout.
"""

from __future__ import annotations

import json
from pathlib import Path

#: Where `jui sync_tool` stamps what it copied, relative to the project root.
SYNC_META_RELPATH = Path(".jsonui-cli") / "sync-meta.json"

#: What `jui sync_tool` writes when it cannot name a version. Comparing
#: against it would report a mismatch on every run of a project whose stamp
#: predates versioned stamping, which is not the state this looks for.
UNKNOWN = "unknown"


def sync_meta_mismatches(project_root, running_version: str) -> list[str]:
    """One message per platform whose stamped version is not the running one.

    Silent when there is no stamp: a project that does not vendor the tools
    has nothing to keep in step, and a check that fired on the absence of an
    optional file would be reporting on the majority of projects.

    ⚠️ Silence here is therefore "nothing to compare", not "they agree". A
    caller that prints a clean bill of health on an empty list is making the
    stronger claim the data does not support.
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
