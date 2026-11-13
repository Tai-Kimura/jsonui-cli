"""INFO lines for a reorderable Collection on a build that builds iOS (ticket jui-collection-drag-to-reorder, ruling B
2026-11-13).

SwiftUI reorders a stack's rows with ``reorderable()`` and ``reorderContainer(for:)`` from iOS 27 only. A reorderable
Collection on the stack paths (no listStyle: ScrollView with LazyVStack / VStack, or none) uses them from iOS 27 and the
library's own drag below it, so an app whose minimum iOS is below 27 runs two implementations of the same gesture. A
Collection with a reorderHandle is not named: it uses the library's drag on every iOS, since reorderable() picks a row up
anywhere and has no handle-only form (support 1's measurement on iOS 27.2; the orchestrator's ruling, 2026-11-13). The
user asked for that to be said at build time as INFO, not as a warning (2026-11-13: "ビルドの時はInfoでiOS 27以上でしか
意味ないよって出す形で"): it is not counted with the warnings, does not change the exit code and is not a stage
failure, the same as core/small_tap_info.py. The List path (listStyle declared) uses onMove on every iOS and is not
named.

The app's minimum iOS is read, in order, from jui.config.json's ``platforms.ios.minimumOS``, the Xcode project's
``IPHONEOS_DEPLOYMENT_TARGET`` (the smallest of its values: <ios root>/<sjui.config project_file_name>.xcodeproj, or
the only .xcodeproj there) and Package.swift's ``.iOS(.vNN)`` / ``.iOS("NN.N")``. When none of them reads, the line says
so and how to set it.
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path

from .normalizer.style_merger import StyleMerger

TAG = "INFO [ios-reorder]"
#: The iOS where SwiftUI's reorderable() / reorderContainer(for:) begin (@available(iOS 27.0, *) in SDK 27.2).
STANDARD_FROM = 27.0

_TARGET = re.compile(r"IPHONEOS_DEPLOYMENT_TARGET\s*=\s*\"?([0-9]+(?:\.[0-9]+)?)\"?\s*;")
_PACKAGE = re.compile(r"\.iOS\(\s*(?:\.v([0-9]+)(?:_([0-9]+))?|\"([0-9]+(?:\.[0-9]+)?)\")\s*\)")


def _version(text: str) -> float | None:
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def minimum_ios(project_root: Path, ios_config: dict) -> tuple[float | None, str]:
    """(the app's minimum iOS, where it was read), or (None, why not)."""
    declared = ios_config.get("minimumOS")
    if declared is not None:
        version = _version(str(declared))
        if version is not None:
            return version, "jui.config.json platforms.ios.minimumOS"
    root = project_root / str(ios_config.get("root") or ".")
    project = None
    try:
        name = json.loads((root / "sjui.config.json").read_text(encoding="utf-8")).get("project_file_name") or ""
    except (OSError, ValueError, AttributeError):
        name = ""
    if name and (root / f"{name}.xcodeproj").is_dir():
        project = root / f"{name}.xcodeproj"
    else:
        found = sorted(root.glob("*.xcodeproj")) if root.is_dir() else []
        project = found[0] if len(found) == 1 else None
    if project is not None:
        try:
            values = [_version(v) for v in _TARGET.findall((project / "project.pbxproj").read_text(encoding="utf-8"))]
        except (OSError, UnicodeDecodeError):
            values = []
        values = [v for v in values if v is not None]
        if values:
            return min(values), f"{project.name}/project.pbxproj IPHONEOS_DEPLOYMENT_TARGET"
    try:
        package = (root / "Package.swift").read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        package = ""
    found = _PACKAGE.search(package)
    if found:
        major, minor, quoted = found.groups()
        version = _version(quoted) if quoted else _version(f"{major}.{minor or 0}")
        if version is not None:
            return version, "Package.swift .iOS(...)"
    return None, "no IPHONEOS_DEPLOYMENT_TARGET, no Package.swift .iOS(...) and no platforms.ios.minimumOS"


def _on(value) -> bool:
    """reorderable is on, or may be (a binding)."""
    return value is True or (isinstance(value, str) and value.strip() not in ("", "false"))


def on_the_stack_path(node: dict) -> bool:
    """A reorderable Collection that iOS draws as a stack, vertical and in one column (the v1 shape).

    sjui and SwiftJsonUI's Dynamic route a vertical single column as (support 1, collection_converter.rb and
    CollectionConverter.swift): lazy "none" is a VStack whatever else is declared; otherwise a listStyle, or no
    `sections` (the cellClasses / items shape), is a List, and sections without a listStyle are CollectionStackView. A
    List reorders with onMove on every iOS and is not named."""
    if node.get("type") != "Collection" or not _on(node.get("reorderable")):
        return False
    if node.get("lazy") != "none" and (node.get("listStyle") or not node.get("sections")):
        return False
    if node.get("reorderHandle"):   # the library's drag on every iOS: SwiftUI's reorderable() has no handle-only form
        return False
    horizontal = node.get("orientation") == "horizontal" or node.get("horizontalScroll") is True \
        or node.get("layout") == "horizontal"
    columns = node.get("columns", 1)
    return not horizontal and (columns in (None, 1) or not isinstance(columns, int))


def tree_lines(node, where: str, minimum: float | None, source: str) -> list[str]:
    """The INFO lines under *node* (a parsed, style-merged layout) for an app whose minimum iOS is *minimum*."""
    found: list[str] = []
    if isinstance(node, dict):
        if on_the_stack_path(node) and (minimum is None or minimum < STANDARD_FROM):
            ident = node.get("id") if isinstance(node.get("id"), str) else "(no id)"
            if minimum is None:
                floor = f"the app's minimum iOS could not be read ({source}; set platforms.ios.minimumOS in jui.config.json)"
                below = "below iOS 27"
            else:
                shown = f"{minimum:g}" if minimum != int(minimum) else f"{int(minimum)}"
                floor = f"the app's minimum iOS is {shown} ({source})"
                below = f"iOS {shown} to 26"
            found.append(
                f"{TAG}: {where}: '{ident}' (Collection) is reorderable: from iOS 27 it uses SwiftUI's standard "
                f"reordering (reorderable / reorderContainer), and on {below} the library's own drag; "
                f"{floor}.")
        for key, value in node.items():
            if key == "responsive":
                continue
            found.extend(tree_lines(value, where, minimum, source))
    elif isinstance(node, list):
        for value in node:
            found.extend(tree_lines(value, where, minimum, source))
    return found


def directory_lines(layouts_dir: Path, styles_dir: Path, project_root: Path, ios_config: dict) -> list[str]:
    """Every INFO line for the layouts under *layouts_dir*, each drawn with its styles merged."""
    if not layouts_dir.is_dir():
        return []
    minimum, source = None, ""
    merger = StyleMerger(styles_dir)
    lines: list[str] = []
    for path in sorted(layouts_dir.rglob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue  # the build reports a file it cannot read on its own path
        drawn = merger.resolve(copy.deepcopy(data))
        if not source:   # read once, and only when a layout may need it
            minimum, source = minimum_ios(project_root, ios_config)
        lines.extend(tree_lines(drawn, path.relative_to(layouts_dir).as_posix(), minimum, source))
    return lines
