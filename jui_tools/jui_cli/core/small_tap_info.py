"""INFO lines for a small tappable element, on a build that builds iOS.

On iOS a small tappable element can lose its taps to a larger tappable element
behind it: SwiftUI's own hit testing reads a touch as an area, and over a big
card the card wins. Measured on an iPhone 17 simulator (iOS 27.2), a button at a
card's corner, nine points inside it: 8 pt took none, 16 pt four, 20 pt eight,
22 pt and up all nine — the same in Dynamic, in the generated code and in plain
SwiftUI, and the same placed directly or inside one or two frames (ticket
swiftjsonui-nested-relative-small-child-tap-falls-through). The library is not
changed (the user's ruling, 2026-11-10): a build says where to look, nothing
more, and asks for no change.

The line is INFO, not a warning: it is not counted with the warnings, does not
change the exit code and is not a stage failure. It names an element whose
width or height is a NUMBER below ``SMALL_TAP_PT`` (a rough mark: the boundary
moves with the device, the OS and simulator against device), with its style
merged as the build draws it. A size the build does not know — wrapContent,
matchParent, none, a binding — is not named.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

from .normalizer.style_merger import StyleMerger

#: The rough mark, in pt: an element with a fixed side below it is named.
SMALL_TAP_PT = 26

TAG = "INFO [ios-tap]"


def _fixed(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _pt(value) -> str:
    fixed = _fixed(value)
    if fixed is None:
        return "?"
    return str(int(fixed)) if fixed == int(fixed) else str(fixed)


def small_tap(node: dict) -> tuple[str, str] | None:
    """(width, height) as written in the line when *node* is a small tappable element, else None."""
    if not node.get("onClick"):
        return None
    sides = [_fixed(node.get("width")), _fixed(node.get("height"))]
    if not any(side is not None and side < SMALL_TAP_PT for side in sides):
        return None
    return _pt(node.get("width")), _pt(node.get("height"))


def tree_lines(node, where: str) -> list[str]:
    """The INFO lines for every small tappable element under *node* (a parsed, style-merged layout)."""
    found: list[str] = []
    if isinstance(node, dict):
        size = small_tap(node)
        if size:
            ident = node.get("id") if isinstance(node.get("id"), str) else "(no id)"
            kind = node.get("type") if isinstance(node.get("type"), str) else "?"
            found.append(
                f"{TAG}: {where}: '{ident}' ({kind}) is a small tappable element ({size[0]} x {size[1]} pt). "
                f"On iOS a larger element behind it can take its taps (roughly when a side is under "
                f"{SMALL_TAP_PT} pt; it varies with the device and the OS). If it does not respond to taps, "
                f"suspect this.")
        for key, value in node.items():
            if key == "responsive":
                continue
            found.extend(tree_lines(value, where))
    elif isinstance(node, list):
        for value in node:
            found.extend(tree_lines(value, where))
    return found


def directory_lines(layouts_dir: Path, styles_dir: Path) -> list[str]:
    """Every INFO line for the layouts under *layouts_dir*, each drawn with its styles merged."""
    if not layouts_dir.is_dir():
        return []
    merger = StyleMerger(styles_dir)
    lines: list[str] = []
    for path in sorted(layouts_dir.rglob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue  # the build reports a file it cannot read on its own path
        drawn = merger.resolve(copy.deepcopy(data))
        lines.extend(tree_lines(drawn, path.relative_to(layouts_dir).as_posix()))
    return lines
