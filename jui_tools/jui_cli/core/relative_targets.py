"""A relative constraint names a sibling (ticket jui-relative-constraint-target-not-a-sibling).

``alignTopOfView`` / ``alignBottomOfView`` / ``alignLeftOfView`` /
``alignRightOfView`` / ``alignTopView`` / ``alignBottomView`` /
``alignLeftView`` / ``alignRightView`` / ``alignCenterVerticalView`` /
``alignCenterHorizontalView`` place an element against ANOTHER CHILD OF THE
SAME CONTAINER. Every platform lays the container's children out together
and looks the target up among them; a target that is not one of them is a
different thing on each face. Measured on jsonui-cli 2.5.25 (a parent, a
sibling's child, the parent's sibling, another container's child, a sibling
of the include from inside it, an id nothing carries, the element itself,
an include's root by the spelling it had before the include's id prefixed
it): Compose did not compile (``Unresolved reference``) for seven of the
eight, SwiftUI ignored the constraint (and drew the element against itself
20pt down), the web found a sibling's child (its helper searches the whole
container) and drew the element against itself 80px up out of its frame.

The check reads a layout the way the codegen does — its includes expanded,
with the prefixes an include's id gives the ids inside it (and the targets
that name them) — and names each element of THAT layout whose target is not
a sibling, with what the target is. An element inside a partial the layout
includes is named when the partial's own layout is checked; the root of an
include is named here, where its siblings are. A layout's own root has no
siblings in that layout: when something includes it, the include is where it
is checked; when nothing does, a constraint on it names nothing.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .normalizer.include_expander import CONSTRAINT_TARGET_KEYS, _combine_with_prefix

#: The marker the check writes on the layout's own nodes before expanding it:
#: an include node's attributes land on its partial's root, so the root
#: carries "include"; a node of an included partial carries none.
MARK = "_jui_constraint_owner"


@dataclass(frozen=True)
class Finding:
    layout: str
    element: str
    attribute: str
    target: str
    what: str            # itself / parent / inside <id> / elsewhere / missing / root
    suggestion: str | None = None

    def line(self, platforms: list[str]) -> str:
        where = f" ({', '.join(platforms)})" if platforms and platforms != ["all"] else ""
        if self.what.startswith("inside "):
            described = f"inside the sibling '{self.what[len('inside '):]}', not a sibling"
        else:
            described = DESCRIBE[self.what]
        text = f"{self.layout}{where}: '{self.element}' {self.attribute}: '{self.target}' — {described}"
        if self.suggestion:
            text += (f"; under the include's id that element is '{self.suggestion}' "
                     f"(an include's id prefixes the ids inside it)")
        return text


DESCRIBE = {
    "itself": "the element itself, not a sibling",
    "parent": "its container, not a sibling",
    "elsewhere": "an element of another container, not a sibling",
    "missing": "no element of this layout has that id",
    "root": "the layout's root has no siblings and nothing includes this layout",
}


def _mark(node) -> None:
    if isinstance(node, dict):
        node[MARK] = "include" if "include" in node else "own"
        if "include" in node:
            return
        for key in ("child", "children"):
            kids = node.get(key)
            for kid in kids if isinstance(kids, list) else [kids] if isinstance(kids, dict) else []:
                _mark(kid)
    elif isinstance(node, list):
        for item in node:
            _mark(item)


def _children(node) -> list:
    kids = node.get("child", node.get("children")) if isinstance(node, dict) else None
    if isinstance(kids, dict):
        return [kids]
    return [k for k in kids if isinstance(k, dict)] if isinstance(kids, list) else []


def _ids_under(node, out: set) -> set:
    for kid in _children(node):
        if isinstance(kid.get("id"), str):
            out.add(kid["id"])
        _ids_under(kid, out)
    return out


def _all_ids(tree) -> set:
    out = {tree["id"]} if isinstance(tree, dict) and isinstance(tree.get("id"), str) else set()
    return _ids_under(tree, out)


def findings_in(name: str, tree: dict, *, included: bool) -> list[Finding]:
    """The constraints of expanded *tree* (layout *name*, its own nodes marked)
    whose target is not a sibling. *included*: something includes this layout
    (its root is checked at the include)."""
    found: list[Finding] = []
    every = _all_ids(tree)

    def check(node, container, siblings: list) -> None:
        if node.get(MARK) not in ("own", "include"):
            return
        own_id = node.get("id")
        for key in CONSTRAINT_TARGET_KEYS:
            target = node.get(key)
            if not isinstance(target, str) or not target or "@{" in target:
                continue
            element = own_id if isinstance(own_id, str) else f"<{node.get('type', 'node')}>"
            if container is None:
                if not included:
                    found.append(Finding(name, element, key, target, "root"))
                continue
            sibling_ids = {s.get("id") for s in siblings if s is not node}
            if target in sibling_ids:
                continue
            if target == own_id:
                what = "itself"
            elif target == container.get("id"):
                what = "parent"
            else:
                holder = next((s.get("id") for s in siblings if s is not node
                               and target in _ids_under(s, set())), None)
                if holder is not None:
                    what = f"inside {holder}"
                elif target in every:
                    what = "elsewhere"
                else:
                    what = "missing"
            suggestion = None
            if what != "itself":
                for s in siblings:
                    sid = s.get("id")
                    if s is node or not isinstance(sid, str) or s.get(MARK) != "include":
                        continue
                    if sid.endswith(_combine_with_prefix("x", target)[1:]) and sid != target:
                        suggestion = sid
            found.append(Finding(name, element, key, target, what, suggestion))

    def walk(node, container) -> None:
        kids = _children(node)
        if container is None:
            check(node, None, [])
        for kid in kids:
            check(kid, node, kids)
            walk(kid, node)

    walk(tree, None)
    return found


def constraint_target_findings(name: str, platform: str | None, *, layouts_dir: Path,
                               styles_dir: Path, included: bool) -> list[Finding]:
    """Layout *name* (a path under *layouts_dir* without ``.json``) on
    *platform*, expanded as the codegen expands it."""
    from .normalizer import normalize

    path = Path(layouts_dir) / f"{name}.json"
    try:
        tree = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(tree, dict):
        return []
    _mark(tree)
    try:
        resolved = normalize(tree, "L2", platform=platform, styles_dir=Path(styles_dir),
                             layouts_dir=Path(layouts_dir), source=str(path)).tree
    except RecursionError:
        return []
    if not isinstance(resolved, dict):
        return []
    return findings_in(name, resolved, included=included)


def included_stems(trees: dict) -> set:
    """The layouts an include names, as include paths (``parts/panel``)."""
    out: set = set()

    def walk(node) -> None:
        if isinstance(node, dict):
            if isinstance(node.get("include"), str):
                out.add(node["include"])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    for tree in trees.values():
        walk(tree)
    return out
