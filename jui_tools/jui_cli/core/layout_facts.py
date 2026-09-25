"""What a screen's Layout JSON holds: its ids and the roots of its bindings.

Design v4.10+ §6.1 (P2.5). At least six Python mouths read a screen's layout
(spec-doc import, `jui verify`, `jui g project`'s orphan check, `jui build`'s
binding roots, lint-strings, the hotload normalizer), and they differ in how
they find the file, treat includes, filter platforms and cut `@{}` apart.
This is not a seventh: it is ONE function over the existing normalizer, and
the contracts-coverage data axis reads nothing else. Moving the six onto it
is out of scope — their outputs would change where consumers can see them.

- The file is the spec's `metadata.layoutFile` and nothing else. Without it
  the screen is `layout not linked` — no guessing (verify and generate fall
  back differently, and a guess read as a fact is the defect this replaces).
- Resolution is the normalizer's L2 (style merge -> include expansion with
  id and binding prefixes -> platform filter), not a second resolver. Where
  it differs from the runtime's Ruby expander, this says so instead of
  silently agreeing with either:
    * a MISSING include is dropped by the normalizer; here it is returned in
      `unresolved_includes`, and the data axis does not evaluate the screen;
    * nested includes resolve from the layouts ROOT (the normalizer), not
      from the including file's directory (Ruby). Kept: the normalizer is
      also the hotloader's, and moving it moves that too.
- Binding roots follow the Ruby validator's grammar
  (`shared/core/binding_validator_core.rb`): every `@{...}` occurrence in a
  string — interpolation included — string literals removed, each dotted or
  indexed path counted as its ROOT, keywords and numbers skipped, and an
  expression that starts with `data.` (a cell's item scope) skipped whole.
  The port is held to Ruby by an arm that runs one corpus through both and
  compares the root sets both ways (a transcription agreeing is not proof).
- Cell layouts (`cellClasses`, a collection's `cell`/`header`/`footer`) are
  another scope, not the screen's view model: counted, never descended into.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

#: One `@{...}` occurrence, as the Ruby validator scans for it.
BINDING_OCCURRENCE = re.compile(r"@\{([^}]*)\}")
_STRING_LITERALS = re.compile(r"'[^']*'|\"[^\"]*\"")
#: A dotted / indexed path — Ruby's `\b[a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*|\[\d+\])*`.
_PATH = re.compile(r"\b[a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*|\[\d+\])*")
#: Ruby's EXTRACTION_KEYWORDS: never a data-property reference.
EXTRACTION_KEYWORDS = frozenset(("true", "false", "nil", "null", "undefined",
                                 "visible", "gone", "index"))
#: Keys that hold a cell's layout: a different scope, counted and skipped.
CELL_KEYS = ("cellClasses", "headerClasses", "footerClasses")
SECTION_CELL_KEYS = ("cell", "header", "footer")


def expression_roots(expression: str) -> set:
    """The roots one binding expression reads (Ruby's `extract_variables`),
    or none for a `data.` expression (a cell item's scope)."""
    if expression.strip().startswith("data."):
        return set()
    stripped = _STRING_LITERALS.sub("", expression)
    roots = set()
    for match in _PATH.finditer(stripped):
        root = re.split(r"[.\[]", match.group(0))[0]
        if root in EXTRACTION_KEYWORDS or root[:1].isdigit():
            continue
        roots.add(root)
    return roots


def value_roots(value) -> set:
    """Every binding root in *value* — a string (every occurrence, mixed text
    included), or anything nested inside a dict or list."""
    if isinstance(value, str):
        roots = set()
        for inner in BINDING_OCCURRENCE.findall(value):
            roots |= expression_roots(inner)
        return roots
    if isinstance(value, dict):
        return set().union(*(value_roots(v) for v in value.values())) if value else set()
    if isinstance(value, list):
        return set().union(*(value_roots(v) for v in value)) if value else set()
    return set()


@dataclass
class LayoutFacts:
    #: `metadata.layoutFile` as written; None = not linked.
    layout_file: str | None
    path: Path | None = None
    #: Read and resolved. False when not linked, missing, unreadable, or when
    #: an include could not be resolved (`reason` says which).
    evaluated: bool = False
    reason: str | None = None
    ids: set = field(default_factory=set)
    binding_roots: set = field(default_factory=set)
    unresolved_includes: list = field(default_factory=list)
    #: Cell layouts referenced from this layout (another scope, not bound).
    cells: int = 0
    #: The cell layouts' names where written as a layout path (the string
    #: forms: `cellClasses: ["dir/cell"]`, a section's `"cell": "dir/cell"`).
    cell_layouts: set = field(default_factory=set)
    #: id -> the node's `type`, for the ids that carry one.
    types: dict = field(default_factory=dict)
    #: id -> how many nodes carry it: more than one is a duplicate after the
    #: includes expanded (`duplicate_ids`).
    id_counts: Counter = field(default_factory=Counter)
    #: The spellings an id inside an include that HAS an id takes on some
    #: platform but not in `ids`: the included layout's own id (web does not
    #: flatten includes, so it keeps it) and `<include id>_<id>` (UIKit). The
    #: prefixed camelCase spelling native uses is what `ids` holds.
    include_ids: set = field(default_factory=set)


def _layout_file(spec: dict) -> str | None:
    metadata = spec.get("metadata") if isinstance(spec, dict) else None
    value = metadata.get("layoutFile") if isinstance(metadata, dict) else None
    return value if isinstance(value, str) and value else None


def _load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return None


def _includes(node, found: list) -> None:
    """Every `include` reference in a raw layout tree, depth first."""
    if isinstance(node, dict):
        if isinstance(node.get("include"), str):
            found.append(node["include"])
        for key, value in node.items():
            if key in CELL_KEYS:
                continue
            _includes(value, found)
    elif isinstance(node, list):
        for value in node:
            _includes(value, found)


def _includes_with_an_id(node, found: list) -> None:
    """(layout, include id) of every `include` that carries an `id`, depth
    first — the ones whose ids are spelled differently per platform."""
    if isinstance(node, dict):
        if isinstance(node.get("include"), str) and isinstance(node.get("id"), str) \
                and node["id"]:
            found.append((node["include"], node["id"]))
        for key, value in node.items():
            if key in CELL_KEYS:
                continue
            _includes_with_an_id(value, found)
    elif isinstance(node, list):
        for value in node:
            _includes_with_an_id(value, found)


def _unresolved_includes(tree, layouts_dir: Path) -> list:
    """Include references that do not resolve, following resolved ones the
    way the normalizer does (from the layouts root). Cycle-guarded."""
    missing, seen, queue = [], set(), []
    _includes(tree, queue)
    while queue:
        ref = queue.pop(0)
        if ref in seen:
            continue
        seen.add(ref)
        included = _load(layouts_dir / f"{ref}.json")
        if included is None:
            missing.append(ref)
            continue
        _includes(included, queue)
    return missing


def _walk(node, facts: LayoutFacts) -> None:
    if isinstance(node, dict):
        if isinstance(node.get("id"), str) and node["id"]:
            facts.ids.add(node["id"])
            facts.id_counts[node["id"]] += 1
            if isinstance(node.get("type"), str):
                facts.types[node["id"]] = node["type"]
        for key, value in node.items():
            if key in CELL_KEYS:
                facts.cells += len(value) if isinstance(value, list) else 1
                for cell in value if isinstance(value, list) else [value]:
                    name = cell.get("className") if isinstance(cell, dict) else cell
                    if isinstance(name, str) and name:
                        facts.cell_layouts.add(name)
                continue
            if key == "sections" and isinstance(value, list):
                for section in value:
                    if isinstance(section, dict):
                        facts.cells += sum(1 for k in SECTION_CELL_KEYS if k in section)
                        facts.cell_layouts |= {section[k] for k in SECTION_CELL_KEYS
                                               if isinstance(section.get(k), str) and section[k]}
                continue
            if key in ("child", "children"):
                _walk(value, facts)
                continue
            facts.binding_roots |= value_roots(value)
            if isinstance(value, (dict, list)):
                _walk_nested(value, facts)
    elif isinstance(node, list):
        for value in node:
            _walk(value, facts)


def _walk_nested(value, facts: LayoutFacts) -> None:
    """Ids inside non-child containers (a node's nested component objects)."""
    if isinstance(value, dict):
        if isinstance(value.get("id"), str) and value["id"] and "type" in value:
            _walk(value, facts)
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, dict) and "type" in item:
                _walk(item, facts)


def layout_facts(spec: dict, platform: str | None, *, layouts_dir: Path,
                 styles_dir: Path, _seen: frozenset = frozenset()) -> LayoutFacts:
    """The ids and binding roots of *spec*'s layout, resolved for *platform*."""
    from .normalizer import normalize

    name = _layout_file(spec)
    facts = LayoutFacts(layout_file=name)
    if name is None:
        facts.reason = "layout not linked"
        return facts
    facts.path = Path(layouts_dir) / f"{name}.json"
    tree = _load(facts.path)
    if not isinstance(tree, dict):
        facts.reason = ("layout file missing" if not facts.path.exists()
                        else "layout file unreadable")
        return facts
    facts.unresolved_includes = _unresolved_includes(tree, Path(layouts_dir))
    resolved = normalize(tree, "L2", platform=platform, styles_dir=Path(styles_dir),
                         layouts_dir=Path(layouts_dir), source=str(facts.path)).tree
    _walk(resolved, facts)
    found: list = []
    _includes_with_an_id(tree, found)
    for included, prefix in found:
        if included in _seen or included == name:
            continue
        inner = layout_facts({"metadata": {"layoutFile": included}}, platform,
                             layouts_dir=layouts_dir, styles_dir=styles_dir,
                             _seen=_seen | {name})
        spelled = inner.ids | inner.include_ids
        facts.include_ids |= spelled | {f"{prefix}_{i}" for i in spelled}
    if facts.unresolved_includes:
        facts.reason = "unresolved include: " + ", ".join(facts.unresolved_includes)
        return facts
    facts.evaluated = True
    return facts


@dataclass
class Everywhere:
    """A layout on every platform: the union of the unfiltered resolution and
    each platform's (an id only a platform override gives a node exists on
    that platform, and the unfiltered tree never merges an override)."""
    ids: set
    cell_ids: set
    include_ids: set
    types: dict
    unresolved: list


def layout_ids_every_platform(name: str, *, layouts_dir: Path, styles_dir: Path) -> Everywhere:
    """Layout *name* on every platform, cell ids and include spellings apart."""
    from .platform_resolver import VALID_PLATFORMS

    out = Everywhere(set(), set(), set(), {}, [])
    for platform in (None, *VALID_PLATFORMS):
        facts = layout_facts({"metadata": {"layoutFile": name}}, platform,
                             layouts_dir=layouts_dir, styles_dir=styles_dir)
        out.ids |= facts.ids
        out.include_ids |= facts.include_ids
        out.types.update(facts.types)
        out.unresolved += [u for u in facts.unresolved_includes if u not in out.unresolved]
        out.cell_ids |= cell_ids_for(facts, platform, layouts_dir=layouts_dir,
                                     styles_dir=styles_dir)
    out.include_ids -= out.ids
    return out


def fold(name: str) -> str:
    """`sample_toggle` / `sampleToggle` -> `sampletoggle`. The
    toolchain has three snake->camel functions that disagree on segments with
    capitals; folding both sides is no fourth one (ee, 2026-09-25)."""
    return name.lower().replace("_", "")


def element_candidates(element: str, ids, types=None) -> list:
    """Layout ids a person may have meant by *element* — never counted as a
    match, never applied: the runtime id is the layout's spelling, and which
    node was meant is a person's call. In order:

    - the same name, folded (`sample_toggle` -> `sampleToggle`)
    - the name with the node's TYPE after it (`sample_panel` ->
      `samplePanelView`: the remainder ends with the node's own type)
    - the name after an include's prefix (`sample_row` ->
      `side_sample_row`)
    """
    folded = fold(element)
    if not folded:
        return []
    types = types or {}
    same, typed, prefixed = [], [], []
    for i in sorted(ids):
        fi = fold(i)
        if i == element:
            continue
        if fi == folded:
            same.append(i)
        elif fi.startswith(folded) and isinstance(types.get(i), str) \
                and fi[len(folded):].endswith(fold(types[i])):
            typed.append(i)
        elif fi.endswith(folded) and fi != folded:
            prefixed.append(i)
    return same + typed + prefixed


def classify_element(element: str, *, ids, cell_ids=(), include_ids=(), types=None):
    """(kind, candidates) of an id a spec names — the ONE answer the spec
    validator and the coverage data axis both give (design v4.20):

      on_layout         the layout has it, exactly
      in_cell           a cell layout it names has it — another scope, not checked
      include_spelling  it is how some platform spells an id inside an include
                        with an id — cannot be checked against one resolution
      missing           none of these; *candidates* from `element_candidates`
    """
    if element in ids:
        return "on_layout", []
    if element in cell_ids:
        return "in_cell", []
    if element in include_ids:
        return "include_spelling", []
    return "missing", element_candidates(element, ids, types)


def cell_ids_for(facts: LayoutFacts, platform: str | None, *, layouts_dir: Path,
                 styles_dir: Path) -> set:
    """The ids of the cell layouts *facts* names, followed down, on *platform*."""
    cell_ids, seen, queue = set(), set(), list(facts.cell_layouts)
    while queue:
        cell = queue.pop()
        if cell in seen:
            continue
        seen.add(cell)
        inner = layout_facts({"metadata": {"layoutFile": cell}}, platform,
                             layouts_dir=layouts_dir, styles_dir=styles_dir)
        cell_ids |= inner.ids
        queue += list(inner.cell_layouts)
    return cell_ids


def duplicate_ids(name: str, platforms, *, layouts_dir: Path, styles_dir: Path) -> dict:
    """{platform: {id: count}} — the ids of layout *name* that more than one
    node carries once includes expand with their prefixes, on each of
    *platforms* (design U8). The runtime and every driver find an element by
    its id as written, so two nodes under one id are one element to a test:
    `type_badge` and `typeBadge` under the include `hero` both become
    `heroTypeBadge`; `hero` + `card_type_badge` and `hero_card` + `type_badge`
    both `heroCardTypeBadge`; one partial included twice under the same id.
    Per platform, because a node another platform filters out is not there.
    Cells are their own layouts, checked on their own."""
    out = {}
    for platform in platforms:
        facts = layout_facts({"metadata": {"layoutFile": name}}, platform,
                             layouts_dir=layouts_dir, styles_dir=styles_dir)
        dups = {i: n for i, n in facts.id_counts.items() if n > 1}
        if dups:
            out[platform] = dups
    return out

