"""Flatten-install valid test files into platform test locations.

`jsonui-test validate` reads the cross-platform SSoT `.test.json` files that live
under `tests/screens/**`. On-device the driver loaders are non-recursive at the
packaged-resource layer (Android `assetManager.list` lists direct children only;
iOS synchronized groups flatten resources into the bundle root), so the
hierarchical SSoT never reaches them.

This module copies the validated `.test.json` files *flat* into each configured
platform location, running automatically as a side effect of a successful
`validate` so the sync can never be forgotten.

Distribution is platform-aware: each target gets a *shaped* copy that contains
only the tests and cases that run on that platform. Shaping is purely
subtractive — it drops whole files, prunes screen-test cases, and drops whole
flows whose file references were shaped out — it never rewrites or strips
fields inside a file it emits. Unmodified files are copied byte-for-byte.
"""

from __future__ import annotations

import json
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
    collisions: list = field(default_factory=list)     # [(platform, basename, [source_str, ...])]
    installed: dict = field(default_factory=dict)      # platform -> [dest_file_str]
    skipped_files: dict = field(default_factory=dict)  # platform -> [source_str]
    pruned_cases: dict = field(default_factory=dict)   # platform -> [(source_str, case_name)]
    skipped_flows: dict = field(default_factory=dict)  # platform -> [reason_str]

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
    """Return [(platform_token, dest_dir_Path)] from the `test.install` config.

    The platform token defaults to the install key (`ios` / `android` / `web`);
    an explicit `"platform"` key in the entry overrides it (for variant keys).
    Relative destination paths resolve against `project_root` (the directory of
    the config file). Platforms without a usable destination are skipped.
    """
    install = (test_config or {}).get("install") or {}
    targets = []
    for key, entry in install.items():
        dest = _dest_of(entry)
        if not dest:
            continue
        platform = key
        if isinstance(entry, dict) and isinstance(entry.get("platform"), str) and entry["platform"]:
            platform = entry["platform"]
        dest_path = Path(dest)
        if not dest_path.is_absolute():
            dest_path = project_root / dest_path
        targets.append((platform, dest_path))
    return targets


def _platform_matches(value, target: str) -> bool:
    """Normative platform-membership spec, shared by all shaping decisions.

    Mirrors the runtime filters in all three drivers (iOS TestModels.swift,
    Android TestModels.kt, web types.ts platformIncludes):
    - missing (None) -> runs everywhere (default "all")
    - scalar "all"   -> matches every target
    - scalar token   -> matches itself only
    - array          -> LITERAL contains, no special-casing of "all"
      ("all" is not a legal array item per the schema enum)
    """
    if value is None:
        return True
    if isinstance(value, str):
        return value == "all" or value == target
    if isinstance(value, list):
        return target in value
    # Malformed value: the validator rejects it before install runs.
    return True


def _file_key(name: str) -> str:
    """Loader-style key for a test file basename (strip .test.json / .json)."""
    for suffix in (".test.json", ".json"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def _ref_key(file_ref: str) -> str:
    """Loader-style key for a fileStep reference.

    Drivers resolve references by basename with automatic screens/ lookup, so
    'login', 'screens/login' and 'login.test.json' all name the same file
    (see validation/step.py:_resolve_file_reference for the canonical rules).
    """
    normalized = file_ref.replace("\\", "/").rstrip("/")
    return _file_key(normalized.rsplit("/", 1)[-1])


@dataclass
class _PlannedFile:
    """One source file surviving shaping for a single target."""
    src: Path
    data: dict | None            # parsed source (None: unparseable, copy as-is)
    shaped: dict | None          # re-serialized content; None -> byte-copy src
    case_names: set | None       # surviving case names (screen tests only)


def _shape_for_platform(data, platform: str):
    """Pass 1 shaping decision for one parsed file on one target.

    Returns (survives, shaped_or_None, surviving_case_names_or_None,
    pruned_case_names). Purely subtractive: either the file is dropped, or
    screen-test cases are filtered; no field is ever rewritten or stripped.
    """
    if not isinstance(data, dict):
        return True, None, None, []

    if "platform" in data and not _platform_matches(data.get("platform"), platform):
        return False, None, None, []

    if data.get("type") == "screen" and isinstance(data.get("cases"), list):
        kept, pruned_names = [], []
        for case in data["cases"]:
            if isinstance(case, dict) and not _platform_matches(case.get("platform"), platform):
                pruned_names.append(case.get("name", "?"))
            else:
                kept.append(case)
        case_names = {c.get("name") for c in kept if isinstance(c, dict)}
        if not kept:
            # Zero cases left: don't write an empty suite.
            return False, None, None, pruned_names
        if pruned_names:
            # Shallow copy preserves key order; replacing an existing key
            # keeps its position, so only `cases` content changes.
            shaped = dict(data)
            shaped["cases"] = kept
            return True, shaped, case_names, pruned_names
        return True, None, case_names, []

    return True, None, None, []


def _file_steps(flow_data: dict):
    """Yield every fileStep in a flow's setup, steps, and teardown arrays."""
    for section in ("setup", "steps", "teardown"):
        steps = flow_data.get(section)
        if not isinstance(steps, list):
            continue
        for step in steps:
            if isinstance(step, dict) and "file" in step:
                yield step


def _dangling_ref_reason(flow_data: dict, platform: str, surviving_by_key: dict,
                         source_keys: set, source_case_names: dict) -> str | None:
    """Return why a surviving flow must be dropped on this target, or None.

    A flow is dropped when an un-gated fileStep references a screen test (or a
    named case) that was shaped out on this platform. Individual fileSteps are
    never dropped — flow steps are sequential and state-dependent.
    """
    for step in _file_steps(flow_data):
        when = step.get("when")
        if (isinstance(when, dict) and "platform" in when
                and not _platform_matches(when["platform"], platform)):
            continue  # self-gated: the runtime skips this step on this target
        if not isinstance(step["file"], str):
            continue
        ref = _ref_key(step["file"])
        if ref not in surviving_by_key:
            if ref in source_keys:
                return ref  # shaped out on this target -> dangling reference
            continue  # never existed in the source set; validator already warned
        ref_cases = surviving_by_key[ref].case_names
        if ref_cases is None:
            continue  # referenced file has no case objects to select from
        if "case" in step:
            names = [step["case"]]
        elif isinstance(step.get("cases"), list):
            names = step["cases"]
        else:
            continue  # no selector: file-level survival is enough
        for name in names:
            if name not in ref_cases and name in source_case_names.get(ref, set()):
                return f"{ref}[{name}]"  # named case pruned on this target
    return None


def _plan_target(files: list, parsed: dict, platform: str, report: InstallReport) -> list:
    """Shape the source set for one target. Returns surviving [_PlannedFile]."""
    surviving: list = []
    source_keys = {_file_key(f.name) for f in files}
    source_case_names: dict = {}

    # Pass 1 — per-file shaping (purely subtractive).
    for f in files:
        data = parsed[f]
        key = _file_key(f.name)
        if isinstance(data, dict) and isinstance(data.get("cases"), list):
            source_case_names[key] = {
                c.get("name") for c in data["cases"] if isinstance(c, dict)}
        survives, shaped, case_names, pruned_names = _shape_for_platform(data, platform)
        for name in pruned_names:
            report.pruned_cases.setdefault(platform, []).append((str(f), name))
        if not survives:
            report.skipped_files.setdefault(platform, []).append(str(f))
            continue
        surviving.append(_PlannedFile(src=f, data=data, shaped=shaped, case_names=case_names))

    # Pass 2 — flow reference closure at (file, case-name) granularity.
    # Dropping a flow can dangle references in other flows, so iterate to a
    # fixed point.
    changed = True
    while changed:
        changed = False
        by_key = {_file_key(e.src.name): e for e in surviving}
        for entry in list(surviving):
            if not isinstance(entry.data, dict) or entry.data.get("type") != "flow":
                continue
            reason = _dangling_ref_reason(
                entry.data, platform, by_key, source_keys, source_case_names)
            if reason is not None:
                surviving.remove(entry)
                flow_key = _file_key(entry.src.name)
                report.skipped_flows.setdefault(platform, []).append(f"{flow_key} → {reason}")
                changed = True

    return surviving


def flatten_install(test_files, targets) -> InstallReport:
    """Flatten-copy each `.test.json` in `test_files` into every target dir.

    Per target, the source set is shaped first (see module docstring): files
    whose test-level `platform` excludes the target are skipped, screen-test
    cases are pruned by case-level `platform`, and flows whose file references
    were shaped out are dropped whole. Unmodified files are byte-copied; only
    screen tests with pruned cases are re-serialized.

    Full sync: existing `*.test.json` in each target dir are removed first so
    renamed/deleted SSoT tests leave no stale copies. Basename collisions among
    the files actually written to the same destination abort the install — the
    flat layout requires screen-unique names per target.
    """
    files = [Path(f) for f in test_files]

    report = InstallReport(targets=[(p, str(d)) for p, d in targets])

    # Parse each source once; shaping decisions need the JSON content.
    # Unparseable files are copied as-is (validate gates real installs).
    parsed: dict = {}
    for f in files:
        try:
            parsed[f] = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            parsed[f] = None

    # Plan every target before touching any destination.
    plans = []
    for platform, dest_dir in targets:
        plans.append((platform, dest_dir, _plan_target(files, parsed, platform, report)))

    # Detect basename collisions per destination, post-shaping: only files
    # actually written to the same target can collide.
    for platform, dest_dir, surviving in plans:
        by_name: dict = {}
        for entry in surviving:
            by_name.setdefault(entry.src.name, []).append(str(entry.src))
        for name, srcs in by_name.items():
            if len(srcs) > 1:
                report.collisions.append((platform, name, srcs))
    if report.collisions:
        return report

    for platform, dest_dir, surviving in plans:
        dest_dir.mkdir(parents=True, exist_ok=True)
        # Clean stale flattened tests only — leave any other files in place.
        for stale in dest_dir.glob("*.test.json"):
            stale.unlink()
            report.removed += 1
        for entry in surviving:
            target = dest_dir / entry.src.name
            if entry.shaped is None:
                shutil.copy2(entry.src, target)
            else:
                with open(target, "w", encoding="utf-8") as fp:
                    json.dump(entry.shaped, fp, indent=2, ensure_ascii=False)
            report.copied.append((platform, str(target)))
            report.installed.setdefault(platform, []).append(str(target))

    return report
