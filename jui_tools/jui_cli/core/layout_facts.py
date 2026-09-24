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
        for key, value in node.items():
            if key in CELL_KEYS:
                facts.cells += len(value) if isinstance(value, list) else 1
                continue
            if key == "sections" and isinstance(value, list):
                for section in value:
                    if isinstance(section, dict):
                        facts.cells += sum(1 for k in SECTION_CELL_KEYS if k in section)
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
                 styles_dir: Path) -> LayoutFacts:
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
    if facts.unresolved_includes:
        facts.reason = "unresolved include: " + ", ".join(facts.unresolved_includes)
        return facts
    facts.evaluated = True
    return facts
