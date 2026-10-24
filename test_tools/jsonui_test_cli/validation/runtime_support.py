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

#: npm package name per platform: web's version is read from node_modules.
#: The iOS and Android drivers arrive through SPM and Maven, and their
#: version is read from the project's pin instead (`read_pinned_driver`).
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


def installed_driver_version(platform: str, project_root: Path,
                             platform_root: Path | None = None) -> str | None:
    """Version of the installed driver, or None when it cannot be read.

    Searched from the platform's own root (`platforms.<platform>.root`) and
    then from the project root, each outward: a monorepo may hoist
    node_modules above the package that declares the dependency. The
    platform root comes first, so a project with a driver in both places is
    judged by the one its platform actually resolves.

    The platform root is not optional in practice: `jui init` puts the web
    app under `platforms.web.root` (`web/`), with its node_modules inside it,
    and a search from the project root alone never reached it — the check
    said "could not be read" on every standard layout (2026-10-16, jsonui-cli
    1.9.33).
    """
    if platform in _PIN_READERS:
        return read_pinned_driver(platform, project_root, platform_root)[0]
    package = DRIVER_PACKAGES.get(platform)
    if not package:
        return None
    starts: list[Path] = []
    for start in (platform_root, project_root):
        if start is not None and Path(start).resolve() not in starts:
            starts.append(Path(start).resolve())
    for root in starts:
        for directory in [root, *root.parents]:
            manifest = directory / "node_modules" / package / "package.json"
            if manifest.exists():
                try:
                    version = json.loads(manifest.read_text(encoding="utf-8")).get("version")
                except (OSError, ValueError):
                    return None
                return version if isinstance(version, str) else None
    return None


# ---------------------------------------------------------------- iOS / Android
#
# The mobile drivers arrive through SPM and Maven, so the version is the PIN
# the project resolved, not an installed package. Measured on the consumers
# (2026-10-16): the iOS projects that commit a Package.resolved keep it in
# `<app>.xcodeproj/project.xcworkspace/xcshareddata/swiftpm/`, and both pin
# the driver by branch or revision, not by version; the Android projects pin
# it in the version catalog (`gradle/libs.versions.toml`, `version.ref`). A
# coordinate string written directly in a build file is read too. The plugins
# DSL is not: the driver is a library, not a Gradle plugin, so no spelling of
# it can appear there.
#
# Searched in the platform root, then the project root — not outward: there
# is no hoisting in SPM or Gradle, and a parent directory holds OTHER
# projects, whose pins are not this one's.

IOS_PACKAGE = "jsonui-test-runner-ios"
ANDROID_MODULE = "io.github.tai-kimura:jsonui-test-runner-android"


def _distinct(found: list, where: Path, what: str):
    """(version, why) from the pins one directory holds: one answer, or
    unreadable when they disagree."""
    answers = list(dict.fromkeys(found))
    if not answers:
        return None
    if len(answers) == 1:
        return answers[0]
    return None, (f"{len(answers)} {what} under {where} pin it differently "
                  f"({'; '.join(v or w for v, w in answers)})")


def _ios_pin(root: Path):
    files = [root / "Package.resolved",
             *sorted(root.glob("*.xcworkspace/xcshareddata/swiftpm/Package.resolved")),
             *sorted(root.glob("*.xcodeproj/project.xcworkspace/xcshareddata/swiftpm/Package.resolved"))]
    found = []
    for path in files:
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        pins = data.get("pins") or (data.get("object") or {}).get("pins") or []
        for pin in pins if isinstance(pins, list) else []:
            if not isinstance(pin, dict):
                continue
            url = str(pin.get("location") or pin.get("repositoryURL") or "").rstrip("/")
            if pin.get("identity") != IOS_PACKAGE and not url.removesuffix(".git").endswith("/" + IOS_PACKAGE):
                continue
            state = pin.get("state") if isinstance(pin.get("state"), dict) else {}
            if isinstance(state.get("version"), str) and state["version"]:
                found.append((state["version"], None))
            else:
                how = (f"branch '{state['branch']}'" if state.get("branch")
                       else f"revision {str(state.get('revision', '?'))[:12]}")
                found.append((None, f"{path} pins {IOS_PACKAGE} to {how}, not a version"))
    return _distinct(found, root, "Package.resolved files")


_DIRECT = re.compile(r"""["']""" + re.escape(ANDROID_MODULE) + r""":([^"']+)["']""")


def _catalog_version(value, versions: dict):
    """A catalog library's version: a string, `{ref = ...}`, or a rich
    version (`strictly` / `require` / `prefer`)."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        if "ref" in value:
            return _catalog_version(versions.get(value["ref"]), versions)
        for key in ("strictly", "require", "prefer"):
            if isinstance(value.get(key), str):
                return value[key]
    return None


def _android_pin(root: Path):
    import tomllib
    found = []
    for path in sorted(root.glob("gradle/*.versions.toml")):
        try:
            catalog = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        versions = catalog.get("versions") or {}
        for entry in (catalog.get("libraries") or {}).values():
            if isinstance(entry, str):
                if entry.startswith(ANDROID_MODULE + ":"):
                    found.append((entry[len(ANDROID_MODULE) + 1:], None))
                continue
            if not isinstance(entry, dict):
                continue
            module = entry.get("module") or f"{entry.get('group')}:{entry.get('name')}"
            if module != ANDROID_MODULE:
                continue
            version = _catalog_version(entry.get("version"), versions)
            found.append((version, None) if version else
                         (None, f"{path} declares {ANDROID_MODULE} with no version it can resolve"))
    builds = [root / "build.gradle", root / "build.gradle.kts",
              *sorted(root.glob("*/build.gradle")), *sorted(root.glob("*/build.gradle.kts"))]
    for path in builds:
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for m in _DIRECT.finditer(text):
            version = m.group(1)
            found.append((None, f"{path} builds the {ANDROID_MODULE} version from a variable "
                                f"({version})") if "$" in version else (version, None))
    return _distinct(found, root, "pins")


_PIN_READERS = {"ios": _ios_pin, "android": _android_pin}


def read_pinned_driver(platform: str, project_root: Path | None,
                       platform_root: Path | None = None) -> tuple[str | None, str | None]:
    """(version, None), (None, why the pin has no version), or (None, None)
    when no pin was found — the mobile drivers' counterpart of the web
    search, from the same two roots, the platform root first."""
    reader = _PIN_READERS[platform]
    starts: list[Path] = []
    for start in (platform_root, project_root):
        if start is not None and Path(start).resolve() not in starts:
            starts.append(Path(start).resolve())
    for root in starts:
        answer = reader(root)
        if answer is not None:
            return answer
    return None, None


def runs_on(path: Path, platform: str) -> bool:
    """Does this test file run on *platform*? Its top-level `platform`
    (`ios` / `android` / `web` / `all`, or a list); absent means every one."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return True
    value = data.get("platform") if isinstance(data, dict) else None
    if isinstance(value, str):
        return value in ("all", platform)
    if isinstance(value, list):
        return platform in value
    return True


def platform_roots_from_config(config: dict, project_root: Path | None) -> dict[str, Path]:
    """`platforms.<name>.root` per platform, resolved against the project root.

    Empty when there is no project root, or the config declares no platforms
    or declares them as a plain list (no roots) — the search is then the
    project root's, as before.
    """
    if project_root is None:
        return {}
    platforms = config.get("platforms") if isinstance(config, dict) else None
    if not isinstance(platforms, dict):
        return {}
    roots: dict[str, Path] = {}
    for name, spec in platforms.items():
        root = spec.get("root") if isinstance(spec, dict) else None
        if isinstance(root, str) and root:
            roots[name] = Path(project_root) / root
    return roots


def check_declarations(declared: dict[str, list[Path]],
                       requirements: dict[str, dict[str, str]],
                       project_root: Path | None,
                       platform_roots: dict[str, Path] | None = None) -> tuple[list[str], list[str]]:
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
        for platform in sorted(needed):
            required = needed[platform]
            # A file that does not run on this platform has nothing for its
            # driver to ignore.
            files = [f for f in declared[key] if runs_on(f, platform)]
            if not files:
                continue
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
            found = installed_driver_version(
                platform, project_root, (platform_roots or {}).get(platform))
            why = (read_pinned_driver(platform, project_root,
                                      (platform_roots or {}).get(platform))[1]
                   if platform in _PIN_READERS else None)
            if found is None and why:
                notes.append(
                    f"'{key}' requires the {platform} driver {required} or newer; "
                    f"{why}, so this is not checked. An older driver ignores the "
                    f"declaration silently ({len(files)} file(s) declare it)."
                )
                continue
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


def _declares(key: str, value) -> bool:
    """Is `key: value` a declaration a driver has to read?

    An empty initialState is not one: spec §10.2 makes it the same as none
    (no payload, no launch), so an older driver ignoring it changes nothing.
    """
    if key == "initialState":
        from .initial_state import is_empty
        return not is_empty(value)
    return True


#: Keys a driver reads on a step (or a step's condition), not on a file or
#: case: collected from every step object in the file.
STEP_LEVEL_KEYS = frozenset({"within"})


def _step_objects(node):
    """Every object under `node` that is a step or a condition: it has
    `action` / `assert`, or a condition key."""
    if isinstance(node, dict):
        if "action" in node or "assert" in node or {"visible", "notVisible", "hidden"} & node.keys():
            yield node
        for value in node.values():
            yield from _step_objects(value)
    elif isinstance(node, list):
        for value in node:
            yield from _step_objects(value)


def collect_declared_keys(files: list[Path],
                          keys: set[str]) -> dict[str, list[Path]]:
    """Which of `keys` each file declares, at the top level or on a case.

    A case-level key is a declaration of the same key: a screen-test case's
    `initialState` needs the same driver as the file's (both schemas carry
    one floor per key, pinned by test_schema_drift). Reading the top level
    alone let a file whose only initialState sits on a case pass an old
    driver in silence. A file is listed once per key however many of its
    cases declare it.
    """
    found: dict[str, list[Path]] = {}
    for path in files:
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        cases = data.get("cases") if isinstance(data.get("cases"), list) else []
        objects = [data, *(case for case in cases if isinstance(case, dict))]
        declared = {key for obj in objects for key in keys & obj.keys()
                    if _declares(key, obj[key])}
        # A step key (`within`): on any step or condition, however nested
        # (cases, setup / teardown, a flow's steps, repeat / retry blocks).
        declared |= {key for obj in _step_objects(data) for key in keys & obj.keys()
                     if key in STEP_LEVEL_KEYS and _declares(key, obj[key])}
        for key in sorted(declared):
            found.setdefault(key, []).append(Path(path))
    return found
