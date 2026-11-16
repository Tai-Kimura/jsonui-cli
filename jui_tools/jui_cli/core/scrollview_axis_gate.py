"""Hard gate for a ScrollView whose ``orientation`` and ``horizontalScroll`` disagree.

A ScrollView scrolls sideways when ``horizontalScroll`` is true or
``orientation`` is ``horizontal``, and vertically otherwise — never from its
children (user ruling 2026-10-14, jui-scrollview-axis-from-child-web-disagrees
and its two siblings; attribute_definitions.json ScrollView). Two spellings
then say opposite things, and the renderers answered them differently
(kjui read ``horizontalScroll`` first, sjui and rjui ``orientation``):

- ``orientation: horizontal`` with ``horizontalScroll: false``;
- ``orientation: vertical`` with ``horizontalScroll: true``.

Refused before a file is written (``ERROR [scrollview]``), in layouts and in
styles, as the node is drawn: with its ``style`` merged (StyleMerger, the
build's own), and for every ``responsive`` key, the base with that key's
override on top — a pair that disagrees only under one key is named with it.
A bound value (``@{…}``) is not judged: what it holds is known when drawn.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

from .normalizer.alias_table import load_type_synonyms
from .normalizer.style_merger import StyleMerger

RULE = ("a ScrollView scrolls sideways when horizontalScroll is true or orientation is horizontal, "
        "and vertically otherwise — write one of them, or both saying the same")


def _is_scroll_view(node: dict, synonyms: dict) -> bool:
    kind = node.get("type")
    if not isinstance(kind, str):
        return False
    return kind == "ScrollView" or synonyms.get(kind, {}).get("canonical") == "ScrollView"


def disagreement(attrs: dict) -> str | None:
    """The sentence for an orientation / horizontalScroll pair that disagree, else None."""
    orientation = attrs.get("orientation")
    horizontal_scroll = attrs.get("horizontalScroll")
    if orientation == "horizontal" and horizontal_scroll is False:
        return "orientation 'horizontal' with horizontalScroll false"
    if orientation == "vertical" and horizontal_scroll is True:
        return "orientation 'vertical' with horizontalScroll true"
    return None


def node_errors(node: dict) -> list[str]:
    """The disagreements of one ScrollView node: as written, and under each responsive key."""
    errors: list[str] = []
    base = {k: v for k, v in node.items() if k != "responsive"}
    found = disagreement(base)
    if found:
        errors.append(found)
    responsive = node.get("responsive")
    if isinstance(responsive, dict):
        for key, override in responsive.items():
            if not isinstance(override, dict):
                continue
            found = disagreement({**base, **override})
            if found:
                errors.append(f"under responsive '{key}': {found}")
    return errors


def tree_errors(node, path: str = "", synonyms: dict | None = None) -> list[str]:
    """Every disagreeing ScrollView under ``node`` (a parsed, style-merged layout or style)."""
    if synonyms is None:
        synonyms = load_type_synonyms()
    found: list[str] = []
    if isinstance(node, dict):
        if _is_scroll_view(node, synonyms):
            where = path or "(root)"
            label = f"{where} id '{node['id']}'" if isinstance(node.get("id"), str) else where
            found.extend(f"{label}: {e}" for e in node_errors(node))
        for key, value in node.items():
            if key == "responsive":
                continue
            found.extend(tree_errors(value, f"{path}.{key}" if path else key, synonyms))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            found.extend(tree_errors(value, f"{path}[{index}]", synonyms))
    return found


def directory_errors(layouts_dir: Path, styles_dir: Path) -> list[str]:
    """Every refused ScrollView in the layouts (styles merged) and in the styles."""
    synonyms = load_type_synonyms()
    errors: list[str] = []
    seen: set[Path] = set()
    for directory, merge in ((layouts_dir, True), (styles_dir, False)):
        if not directory.is_dir():
            continue
        merger = StyleMerger(styles_dir)
        for path in sorted(directory.rglob("*.json")):
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                continue  # the build reports a file it cannot read on its own path
            drawn = merger.resolve(copy.deepcopy(data)) if merge else data
            errors.extend(f"{path.relative_to(directory).as_posix()}: {e}"
                          for e in tree_errors(drawn, synonyms=synonyms))
    return errors
