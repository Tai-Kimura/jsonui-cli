"""Hard gate for the width conditions of an inline ``responsive`` block.

``minWidth:N`` holds when the window is at least N wide, ``maxWidth:N`` when it
is narrower than N (N itself is not included, so ``maxWidth:700`` and
``minWidth:700`` split the widths with no gap and no overlap, fractional widths
included). N is a non-negative whole number in the platform's logical unit
(iOS pt, Android dp, web CSS px); the width is the window's, not the parent's.
⚠️ jsonui-test-runner's responsive *test conditions* read maxWidth as "at most
N"; a layout key's maxWidth is "less than N".

The renderers (shared/core/responsive_resolver.rb and both Dynamic runtimes)
draw the most narrowing condition that holds, alone. That is one answer only
when the block is shaped so that it can be (user ruling 2026-10-13,
jui-responsive-width-threshold-conditions):

- a key that looks like a width condition is spelled as one — no landscape
  combination (``minWidth:700-landscape``), no unit, no fraction;
- one block holds width conditions or size classes (compact / medium /
  regular / landscape and their combinations), never both;
- every maxWidth's N is at most every minWidth's N, so a maxWidth and a
  minWidth never hold at once.

Anything else is refused before a file is written (``ERROR [responsive]``).
The parse is ``responsive_resolver.rb``'s ``WIDTH_CONDITION``; both read
``shared/core/responsive_resolution_vectors.json`` ``key_cases`` in their tests.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

# responsive_resolver.rb VALID_SIZE_CLASSES
SIZE_CLASSES = (
    "compact", "medium", "regular", "landscape",
    "compact-landscape", "medium-landscape", "regular-landscape",
)

_WIDTH_CONDITION = re.compile(r"(minWidth|maxWidth):(0|[1-9][0-9]*)")
# What a reader would take for a width condition: refused unless it is one.
_LOOKS_LIKE_WIDTH = re.compile(r"\s*(min|max)\s*-?\s*width", re.IGNORECASE)

SEMANTICS = ("minWidth:N holds when the window is at least N wide, maxWidth:N when it is "
             "narrower than N (N is not included); N is a whole number of pt / dp / CSS px")


def width_condition(key: str) -> tuple[str, int] | None:
    """``("min" | "max", N)`` for a width-condition key, else None."""
    match = _WIDTH_CONDITION.fullmatch(key)
    if not match:
        return None
    return ("min" if match.group(1) == "minWidth" else "max", int(match.group(2)))


def block_errors(responsive: dict) -> list[str]:
    """What is wrong with one ``responsive`` object, as sentences."""
    errors: list[str] = []
    conditions: dict[str, tuple[str, int]] = {}
    for key in responsive:
        if not isinstance(key, str):
            continue
        parsed = width_condition(key)
        if parsed:
            conditions[key] = parsed
        elif _LOOKS_LIKE_WIDTH.match(key):
            errors.append(f"'{key}' is not a width condition — write minWidth:N or maxWidth:N "
                          f"with N a whole number, and no landscape combination ({SEMANTICS})")
    if not conditions:
        return errors

    size_classes = [k for k in responsive if k in SIZE_CLASSES]
    if size_classes:
        errors.append(f"width conditions ({', '.join(sorted(conditions))}) and size classes "
                      f"({', '.join(size_classes)}) in one responsive block — use one or the other")

    maxes = sorted((n, k) for k, (kind, n) in conditions.items() if kind == "max")
    mins = sorted((n, k) for k, (kind, n) in conditions.items() if kind == "min")
    if maxes and mins and maxes[-1][0] > mins[0][0]:
        errors.append(f"'{maxes[-1][1]}' and '{mins[0][1]}' both hold between "
                      f"{mins[0][0]} and {maxes[-1][0]} — every maxWidth's N must be at most every "
                      f"minWidth's N, so one condition holds at a time ({SEMANTICS})")
    return errors


def tree_errors(node, path: str = "") -> list[str]:
    """Every responsive block under ``node`` (a parsed layout or style), with its path."""
    found: list[str] = []
    if isinstance(node, dict):
        responsive = node.get("responsive")
        if isinstance(responsive, dict):
            where = path or "(root)"
            label = f"{where} id '{node['id']}'" if isinstance(node.get("id"), str) else where
            found.extend(f"{label}: {e}" for e in block_errors(responsive))
        for key, value in node.items():
            if key == "responsive":
                continue
            found.extend(tree_errors(value, f"{path}.{key}" if path else key))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            found.extend(tree_errors(value, f"{path}[{index}]"))
    return found


def directory_errors(directories: list[Path]) -> list[str]:
    """Every refused block in the JSON files under ``directories`` (layouts, styles)."""
    errors: list[str] = []
    seen: set[Path] = set()
    for directory in directories:
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*.json")):
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                continue  # the build reports a file it cannot read on its own path
            errors.extend(f"{path.relative_to(directory).as_posix()}: {e}" for e in tree_errors(data))
    return errors
