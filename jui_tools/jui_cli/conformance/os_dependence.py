"""Which pictures depend on the OS that drew them, and under which key.

`glass` resolves through `#available(iOS 26.0, *)` — that asks the RUNNING
OS, so the same fixture is a different picture on iOS 25 and 26. A baseline
keyed only by `<env>/<platform>` cannot separate those: two runs on different
runtimes compare against each other and every such fixture reports `moved`
with nothing wrong.

🔻 WHY THE KEY IS PER-ENTRY AND NOT PER-FILE. Splitting the manifest into
`<platform>-<os>.hashes.json` was the first design and it says something
false: that the whole corpus depends on the OS. Measured on the 2026-09-14
re-bake, it does not — 61 of 856 entries moved when the toolchain changed, and
every one of them is a system-DRAWN control (26 Switch / 12 TabView /
10 Segment / 6 control_* / 5 Slider / 2 Collection, and zero others). That is
the SDK the host links against, a different axis from `#available`. Keying the
file by OS would fold the two together and make each re-bake look like it
answered a question it did not ask.

So the OS enters the KEY of exactly the entries that resolve through an
availability check, and nothing else moves.

⚠️ THE MEMBERSHIP TEST IS DERIVED, NEVER A LIST OF NAMES. An attribute earns
membership by saying so in its own declaration. A hardcoded "glass" here would
be a second spelling of the vocabulary — the defect this train spent a day on —
and `test_an_os_dependent_baseline_needs_the_os_in_its_key` derives the same
set the same way, from the same file, so the guard and the guarded cannot
drift apart.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

#: A declaration earns OS-dependence by naming one of these. They are the
#: spellings an availability-gated attribute uses to describe itself.
_MARKERS = ("#available", "UIGlassEffect", "glassEffect")


def os_dependent_attributes(definitions: dict) -> set[str]:
    """`Component.attribute` names whose rendering depends on the running OS."""
    found: set[str] = set()
    for component, attrs in definitions.items():
        if component.startswith("_") or not isinstance(attrs, dict):
            continue
        for attribute, defn in attrs.items():
            if not isinstance(defn, dict):
                continue
            blob = json.dumps(defn, ensure_ascii=False)
            if any(m in blob for m in _MARKERS):
                found.add(f"{component}.{attribute}")
    return found


def os_dependent_screenshots(definitions: dict, manifest: dict) -> set[str]:
    """Artifact filenames whose picture depends on the running OS."""
    wanted = {a.split(".", 1)[1].lower() for a in os_dependent_attributes(definitions)}
    if not wanted:
        return set()
    fixtures = manifest["fixtures"] if isinstance(manifest, dict) else manifest
    out: set[str] = set()
    for f in fixtures:
        fid = f["id"]
        stem = fid.rsplit("/", 1)[-1].split("__")[0].lower()
        if stem in wanted:
            out.add(fid.replace("/", "_") + ".png")
    return out


def os_key_from_runner(runner: dict | None) -> str | None:
    """The OS segment of the key, from the run's own `runner` block.

    `{"name": "xcuitest", "version": "ios-26.2"}` -> `"26"`.

    MAJOR ONLY, deliberately. The dependence is `#available(iOS 26.0, *)`, so
    26.2 and 26.3 answer it identically; keying on the full version would split
    the baseline on a patch bump that cannot change the branch taken, and every
    split costs a re-bake that proves nothing.

    Returns None when the runner does not name an OS at all — android reports
    `uiautomator 2.3.0` and web `playwright 1.61.1`, which are tool versions.
    A platform with no OS in its runner gets no OS key, rather than one
    invented from a tool's version number.
    """
    version = (runner or {}).get("version")
    if not isinstance(version, str):
        return None
    m = re.fullmatch(r"(?:ios|ipados|tvos|watchos|visionos)-(\d+)(?:\.\d+)*", version.strip(), re.I)
    return m.group(1) if m else None


def os_dependent_screenshots_for(conformance_dir) -> set[str]:
    """The same set, resolved from a conformance directory.

    Both inputs are read here rather than passed in, so every caller asks the
    question the same way. A missing file yields the empty set: a tree without
    a manifest or a declaration has no OS-dependent pictures to protect, and
    failing here would turn a packaging question into a comparison failure.
    """
    conformance_dir = Path(conformance_dir)
    manifest_path = conformance_dir / "manifest.json"
    ssot_path = conformance_dir.parent / "shared" / "core" / "attribute_definitions.json"
    if not manifest_path.is_file() or not ssot_path.is_file():
        return set()
    return os_dependent_screenshots(
        json.loads(ssot_path.read_text(encoding="utf-8")),
        json.loads(manifest_path.read_text(encoding="utf-8")),
    )
