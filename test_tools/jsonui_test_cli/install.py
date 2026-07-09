"""Flatten-install valid test files into platform test locations.

`jsonui-test validate` reads the cross-platform SSoT `.test.json` files that live
under `tests/screens/**`. On-device the driver loaders are non-recursive at the
packaged-resource layer (Android `assetManager.list` lists direct children only;
iOS synchronized groups flatten resources into the bundle root), so the
hierarchical SSoT never reaches them.

This module copies the validated `.test.json` files *flat* into each configured
platform location, running automatically as a side effect of a successful
`validate` so the sync can never be forgotten.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

# Keys accepted for a platform's destination directory, in priority order.
# `target_dir` (iOS synchronized group) / `assets_dir` (Android assets) are the
# documented spellings; `dir` / `path` are convenience aliases.
_DEST_KEYS = ("target_dir", "assets_dir", "dir", "path")


@dataclass
class InstallReport:
    """Outcome of a flatten-install run."""
    targets: list = field(default_factory=list)      # [(platform, dest_dir_str)]
    copied: list = field(default_factory=list)        # [(platform, dest_file_str)]
    removed: int = 0                                   # stale files cleaned
    collisions: list = field(default_factory=list)     # [(basename, [source_str, ...])]

    @property
    def has_collision(self) -> bool:
        return bool(self.collisions)


def _dest_of(entry) -> str | None:
    """Extract the destination dir from a platform config entry."""
    if isinstance(entry, str):
        return entry or None
    if isinstance(entry, dict):
        for key in _DEST_KEYS:
            value = entry.get(key)
            if value:
                return value
    return None


def resolve_targets(test_config: dict | None, project_root: Path) -> list:
    """Return [(platform, dest_dir_Path)] from the `test.install` config.

    Relative destination paths resolve against `project_root` (the directory of
    the config file). Platforms without a usable destination are skipped.
    """
    install = (test_config or {}).get("install") or {}
    targets = []
    for platform, entry in install.items():
        dest = _dest_of(entry)
        if not dest:
            continue
        dest_path = Path(dest)
        if not dest_path.is_absolute():
            dest_path = project_root / dest_path
        targets.append((platform, dest_path))
    return targets


def flatten_install(test_files, targets) -> InstallReport:
    """Flatten-copy each `.test.json` in `test_files` into every target dir.

    Full sync: existing `*.test.json` in each target dir are removed first so
    renamed/deleted SSoT tests leave no stale copies. Basename collisions (two
    source files sharing a name) abort the install — the flat layout requires
    screen-unique names.
    """
    files = [Path(f) for f in test_files]

    # Detect basename collisions before touching any destination.
    by_name: dict = {}
    for f in files:
        by_name.setdefault(f.name, []).append(str(f))
    collisions = [(name, srcs) for name, srcs in by_name.items() if len(srcs) > 1]

    report = InstallReport(
        targets=[(p, str(d)) for p, d in targets],
        collisions=collisions,
    )
    if collisions:
        return report

    for platform, dest_dir in targets:
        dest_dir.mkdir(parents=True, exist_ok=True)
        # Clean stale flattened tests only — leave any other files in place.
        for stale in dest_dir.glob("*.test.json"):
            stale.unlink()
            report.removed += 1
        for f in files:
            target = dest_dir / f.name
            shutil.copy2(f, target)
            report.copied.append((platform, str(target)))

    return report
