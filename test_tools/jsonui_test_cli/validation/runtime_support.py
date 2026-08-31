"""Does the installed driver actually read the keys this file declares?

The schema can say a key is spelled correctly. It cannot say anything about
whether the thing that executes the test knows what the key means, because
the authoring side and the runtime ship as separate releases. `screenReady`
made that concrete: jsonui-cli 1.7.32 accepts it, driver 1.8.4 reads it, and
between those two releases a project could write a declaration that validated
green and was then silently ignored.

Silently is the expensive part. An ignored `screenReady: 'none'` falls back to
the default gate, so the file waits for exactly the marker it declared it
would not wait for and fails as a 15-second timeout naming the screen. There
is nothing in that output pointing at the declaration. It is the same failure
shape the value-checking in `screen.py` exists to prevent, one level up: that
one is closed within a release, this one crosses releases.

The requirement lives in the canonical schema (`x-requires-driver`) beside the
key it constrains, not in prose, so adding a key means stating its runtime
requirement in the same edit. `test_schema_drift.py` pins the two together.

Where the driver version is knowable this gates; where it is not it says so
and moves on. Guessing in either direction would be worse than the prose it
replaces — a check that assumed "absent means old" would red every project
that runs its tests from somewhere else, and one that assumed "absent means
fine" would be the silence it is here to remove.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

#: npm package name per platform. Only web is resolvable locally; the iOS and
#: Android drivers arrive through SPM and Maven, which leave nothing in the
#: project tree to read a version out of.
DRIVER_PACKAGES = {"web": "jsonui-test-runner-web"}


def parse_version(text: str) -> tuple[int, ...]:
    """`1.8.4` -> (1, 8, 4). Trailing pre-release text is dropped.

    So `1.8.4-beta.1` satisfies a requirement of `1.8.4`, which is the
    intent: ordering pre-releases strictly below the release they lead to
    would red every project validating against a beta, and shipping a beta
    to a lane that then cannot run its tests closes the only path by which
    a driver gets exercised before release.

    Stated because the behaviour was measured and asked about rather than
    designed — the original line described what the simplest parse does.
    A reader who finds a limit with no reason attached supplies one, and
    the reason they supply is usually that it was an oversight.
    """
    parts = re.findall(r"\d+", text.split("+")[0].split("-")[0])
    return tuple(int(p) for p in parts[:3]) or (0,)


def installed_driver_version(platform: str, project_root: Path) -> str | None:
    """Version of the installed driver, or None when it cannot be read.

    Searched from the project root outward: a monorepo may hoist
    node_modules above the package that declares the dependency.
    """
    package = DRIVER_PACKAGES.get(platform)
    if not package:
        return None
    root = Path(project_root).resolve()
    for directory in [root, *root.parents]:
        manifest = directory / "node_modules" / package / "package.json"
        if manifest.exists():
            try:
                version = json.loads(manifest.read_text(encoding="utf-8")).get("version")
            except (OSError, ValueError):
                return None
            return version if isinstance(version, str) else None
    return None


def check_declarations(declared: dict[str, list[Path]],
                       requirements: dict[str, dict[str, str]],
                       project_root: Path | None) -> tuple[list[str], list[str]]:
    """Compare declared keys against the installed drivers.

    `declared` maps a top-level key to the files that use it. Returns
    (errors, notes): errors are declarations measured to be unsupported,
    notes are the ones whose runtime could not be measured.

    There are three ways the runtime can be unknowable, and the third one
    arrives here rather than inside `installed_driver_version`: the caller
    resolves the project root from the config or the enclosing `.git`, and
    returns None when it finds neither. The two handled below it — an
    unsearchable platform, an unreadable manifest — made this one look
    handled too, and it crashed instead (docsite, 1.7.33).

    It gets its own wording. "The installed version could not be read"
    points at the driver, and the reader installs one; here nothing was
    read because nowhere was searched, and what the reader needs is to
    pass --config or run from the project root.
    """
    errors: list[str] = []
    notes: list[str] = []
    for key in sorted(declared):
        needed = requirements.get(key)
        if not needed:
            continue
        files = declared[key]
        for platform in sorted(needed):
            required = needed[platform]
            if not project_root:
                notes.append(
                    f"'{key}' requires the {platform} driver {required} or newer; "
                    f"no project root could be resolved (no config was passed and "
                    f"no enclosing .git was found), so the installed driver was "
                    f"never looked for and this is not checked. Pass --config or "
                    f"run from the project root. An older driver ignores the "
                    f"declaration silently ({len(files)} file(s) declare it)."
                )
                continue
            found = installed_driver_version(platform, project_root)
            if found is None:
                notes.append(
                    f"'{key}' requires the {platform} driver {required} or newer; "
                    f"the installed version could not be read, so this is not "
                    f"checked. An older driver ignores the declaration silently "
                    f"({len(files)} file(s) declare it)."
                )
                continue
            if parse_version(found) < parse_version(required):
                errors.append(
                    f"'{key}' requires the {platform} driver {required} or newer, "
                    f"but {found} is installed — it does not read this key, and "
                    f"ignores it without saying so. Upgrade the driver, or remove "
                    f"the declaration: {', '.join(str(f) for f in sorted(files)[:3])}"
                    f"{' …' if len(files) > 3 else ''}"
                )
    return errors, notes


def collect_declared_keys(files: list[Path],
                          keys: set[str]) -> dict[str, list[Path]]:
    """Which of `keys` each file declares at the top level."""
    found: dict[str, list[Path]] = {}
    for path in files:
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        for key in keys & data.keys():
            found.setdefault(key, []).append(Path(path))
    return found
