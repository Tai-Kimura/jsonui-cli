"""Mermaid flowchart diagram generation — drawn from the screen SPECS.

Ruled 2026-09-10: the diagram's one source is ``<spec>.transitions[].destination``
(``spec_graph.py``). Flow tests are checked AGAINST it: a forward transition a
flow test performs that no spec declares is an ERROR (``DiagramResult.errors``),
a destination the classifier cannot resolve is treated as absent
(``DiagramResult.unresolved``), and back steps are exempt — they are the stack's
inverse of a transition the check already saw.

Before this the module read flow tests only and answered "No flow tests
found" on a face with 48 specs, while the canon declared two sources. The
flow-test walk is kept for exactly one purpose: the check.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime
from typing import Any

from ..html.sidebar import escape_html
from ...reproducible import build_datetime
from ...run_log import warn
from .flow_graph import (
    EDGE_BACK,
    EDGE_FORWARD,
    ScreenResolver,
    flow_edges,
    import_jui_cli_module,
    load_flow,
    normalize_screen_ref,
)
from .spec_graph import SpecGraph, SpecTransition, build_spec_graph, iter_spec_files


@dataclass
class TestTreeIndex:
    """Everything one walk of the test tree tells the diagram."""

    #: screen id -> the screen tests covering it (label, group, document)
    by_screen_id: dict[str, list[dict]] = field(default_factory=dict)
    #: screen test FILE name -> the screen id it covers
    file_ref_screen_ids: dict[str, str] = field(default_factory=dict)
    #: screen id -> groups declared in jui.config.json for app-owned screens
    app_owned_groups: dict[str, list[str]] = field(default_factory=dict)


def _collect_flow_graph(
    flows_path: Path,
    screens_path: Path,
    layouts_dir: Path | None = None,
) -> tuple[dict[str, str], dict[str, dict], list[tuple[str, str, str, str, str]], dict[str, list[str]]]:
    """Walk every flow test once and return what the tests DO.

    Returns ``(nodes, node_metadata, edges, flow_subgraphs)`` where an edge
    is ``(from_id, to_id, flow_name, kind, flow_file)``. Since 2026-09-10
    this is no longer a drawing source: ``build_diagram`` compares these
    edges against the spec graph and reports the ones no spec declares.
    """
    tree = _walk_test_tree(screens_path, flows_path)
    resolver = ScreenResolver(layouts_dir, tree.file_ref_screen_ids)

    nodes: dict[str, str] = {}
    node_metadata: dict[str, dict] = {}
    edges: list[tuple[str, str, str, str]] = []
    flow_subgraphs: dict[str, list[str]] = {}

    for flow_file in sorted(flows_path.rglob("*.test.json")):
        flow_data = load_flow(flow_file)
        if flow_data is None:
            continue

        flow_name = flow_data.get("metadata", {}).get("name", flow_file.stem)
        try:
            flow_nodes, flow_transitions = flow_edges(flow_data.get("steps", []), resolver)
        except Exception as e:  # pragma: no cover - defensive, mirrors old behaviour
            warn(f"  WARNING [doc-diagram]: error processing {flow_file}: {e}")
            continue

        if not flow_nodes:
            continue

        for screen_id in flow_nodes:
            if screen_id in nodes:
                continue
            meta = _resolve_screen_metadata(screen_id, tree)
            nodes[screen_id] = meta["label"]
            node_metadata[screen_id] = {
                "entry_screen": meta["entry_screen"],
                "groups": meta["groups"],
                "document": meta["document"],
            }

        flow_subgraphs[flow_name] = flow_nodes
        for from_id, to_id, kind in flow_transitions:
            edges.append((from_id, to_id, flow_name, kind, str(flow_file)))

    return nodes, node_metadata, edges, flow_subgraphs


NO_SPECS_DIAGRAM = "flowchart LR\n    NO_SPECS[No screen specs found]"
#: First tab: every node and every resolved edge, whatever the groups.
ALL_TAB = "All"


@dataclass(frozen=True)
class TransitionError:
    """A forward transition a flow test performs that no spec declares."""

    from_id: str
    to_id: str
    flow_name: str
    flow_file: str
    #: Which of "no spec" / "spec declares no such transition" / "an
    #: app-owned screen declares no such transition" it is, plus the source's
    #: unresolved destinations when it has any — that is usually the fix.
    reason: str

    def __str__(self) -> str:
        return (f"flow test \"{self.flow_name}\" ({self.flow_file}) transitions "
                f"{self.from_id} -> {self.to_id}: {self.reason}")


@dataclass
class DiagramResult:
    """What one owner's diagram run produced. ``combined`` is "" when
    nothing was drawable — callers suppress the page and the link then."""

    #: group name -> mermaid code
    diagrams: dict[str, str] = field(default_factory=dict)
    combined: str = ""
    errors: list[TransitionError] = field(default_factory=list)
    unresolved: list[SpecTransition] = field(default_factory=list)
    #: `none` transitions, all inferred from wording today (see SpecGraph.nones)
    nones: list[SpecTransition] = field(default_factory=list)
    #: ids that normalize alike, drawn as one: (winner, [(raw, source), ...])
    id_collisions: list[tuple[str, list[tuple[str, str]]]] = field(default_factory=list)
    stats: dict[str, int] = field(default_factory=dict)


def build_diagram(
    spec_dir: Path | str | None,
    *,
    flows_dir: Path | str | None = None,
    screens_dir: Path | str | None = None,
    layouts_dir: Path | str | None = None,
    aliases=(),
    app_owned=(),
    app_owned_transitions: dict[str, list[str]] | None = None,
    document_href,
) -> DiagramResult:
    """Draw from the specs under ``spec_dir``; check the flow tests under
    ``flows_dir`` against what was drawn.

    ``screens_dir`` (screen tests) supplies labels, groups and document links
    for the nodes, exactly as before; it is not a source of edges. With no
    ``spec_dir`` or no spec in it, nothing is drawn (``combined == ""``) and
    the flow tests go unchecked — the caller says so, because "no spec
    directory" is a configuration state, not a spec omission.
    """
    flows_path = Path(flows_dir) if flows_dir else None
    screens_path = Path(screens_dir) if screens_dir else (
        flows_path.parent / "screens" if flows_path else None)
    result = DiagramResult()

    graph = build_spec_graph(
        spec_dir, layouts_dir=layouts_dir, aliases=aliases,
        app_owned=app_owned, app_owned_transitions=app_owned_transitions,
    )
    result.unresolved = list(graph.unresolved)
    result.nones = list(graph.nones)
    result.id_collisions = list(graph.id_collisions)
    result.stats = {
        "specs": graph.specs_scanned,
        "transitions": len(graph.transitions),
        "spec_edges": len(graph.forward_pairs()),
        "unresolved": len(graph.unresolved),
        "none_inferred": len(graph.nones),
    }

    tree = _walk_test_tree(screens_path, flows_path)
    nodes: dict[str, str] = {}
    node_metadata: dict[str, dict] = {}
    drawn_ids = {n for e in graph.edges for n in e[:2]} | {f for f, _raw in graph.externals}
    for screen_id in sorted(drawn_ids):
        meta = _resolve_screen_metadata(screen_id, tree, spec_groups=graph.groups)
        spec_label = graph.nodes.get(screen_id, "")
        if meta["label"] == screen_id.replace("_", " ").title() and spec_label:
            meta["label"] = spec_label
        nodes[screen_id] = meta["label"]
        node_metadata[screen_id] = {
            "entry_screen": meta["entry_screen"],
            "groups": meta["groups"],
            "document": meta["document"],
            "spec_page": graph.spec_pages.get(screen_id),
        }

    # The denominator of the click-target count is THIS set: the ids the
    # graph drew. Not a regex over the emitted text — `^\s{4}(\w+)\[` reads
    # only square brackets and drops every round-bracketed entry node, which
    # cost one node per face in the first measurement of this ticket.
    declared = [m["document"] for m in node_metadata.values() if m.get("document")]
    result.stats["documents_declared"] = len(declared)
    result.stats["documents_rebased"] = sum(1 for d in declared if document_href(d) != d)
    result.stats["nodes"] = len(nodes)
    result.stats["click_targets"] = sum(
        1 for node_id in nodes
        if _click_href(node_metadata.get(node_id, {}), document_href))

    # ---- the check: what the flow tests do vs what the specs declare ----
    flow_files = sorted(flows_path.rglob("*.test.json")) if flows_path and flows_path.is_dir() else []
    result.stats["flow_tests"] = len(flow_files)
    if flow_files:
        _n, _m, flow_edges_found, _s = _collect_flow_graph(flows_path, screens_path, layouts_dir)
        # Declared = every edge the specs produce: a forward edge, or the
        # return edge derived from a `back` declaration (X returns to each
        # screen that pushes it). A flow that leaves a sheet by tapping
        # "save" and lands on its opener performs that return as a forward
        # step; the spec declared it as `back`. Same edge, drawn dotted.
        forward = {(f, t) for f, t, _k in graph.edges}
        seen_pairs: set[tuple[str, str]] = set()
        checked: set[tuple[str, str]] = set()
        for from_id, to_id, flow_name, kind, flow_file in flow_edges_found:
            if kind == EDGE_BACK:
                continue
            checked.add((from_id, to_id))
            if (from_id, to_id) in forward or (from_id, to_id) in seen_pairs:
                continue
            seen_pairs.add((from_id, to_id))
            result.errors.append(TransitionError(
                from_id, to_id, flow_name, flow_file,
                _absence_reason(graph, from_id, to_id, app_owned)))
        result.stats["flow_edges"] = len(checked)
        result.stats["absent"] = len(result.errors)

    if not nodes:
        return result
    result.combined = _build_mermaid_diagram(nodes, graph.edges, node_metadata, graph.externals,
                                             document_href=document_href)
    collisions = mermaid_id_problems(result.combined)
    if collisions:  # pragma: no cover - impossible by construction; kept as the tripwire
        raise RuntimeError(
            f"subgraph and node share an id, Mermaid would refuse the diagram: {collisions}")
    # The group tabs show edges WITHIN a group (plus entry edges into it); an
    # edge between two groups appeared in none of them and on no list — a
    # face counted 29 resolved edges on the closing line and 19 drawn on the
    # page (2026-09-10). The combined diagram is the first tab, so every
    # resolved edge is drawn somewhere the reader can find it.
    result.diagrams = {ALL_TAB: result.combined}
    result.diagrams.update(
        _group_diagrams(nodes, node_metadata, document_href, graph.edges, graph.externals))
    return result


def _absence_reason(graph: SpecGraph, from_id: str, to_id: str, app_owned) -> str:
    owned = {normalize_screen_ref(s) for s in app_owned}
    if from_id in owned:
        head = (f"the app-owned screen {from_id} declares no transition to {to_id} "
                f"(jui.config.json test.appOwnedScreens[].transitions)")
    elif from_id not in graph.sources_with_spec:
        head = f"{from_id} has no spec"
    else:
        head = f"{from_id}'s spec declares no transition to {to_id}"
    unresolved = [t.raw for t in graph.unresolved if t.source == from_id]
    if unresolved:
        listed = ", ".join(repr(r) for r in unresolved[:4])
        more = "" if len(unresolved) <= 4 else f" (+{len(unresolved) - 4} more)"
        head += (f"; {len(unresolved)} of its destination(s) could not be resolved "
                 f"and count as absent: {listed}{more}")
    return head


def generate_mermaid_diagram(
    spec_dir: Path | str | None,
    screens_dir: Path | str | None = None,
    layouts_dir: Path | str | None = None,
    **kwargs,
) -> str:
    """One combined Mermaid diagram from the specs under ``spec_dir``.

    ``NO_SPECS`` placeholder when the directory holds no spec — the shape the
    old "No flow tests found" placeholder had, so a page never renders blank.
    """
    if not iter_spec_files(spec_dir):
        return NO_SPECS_DIAGRAM
    result = build_diagram(spec_dir, screens_dir=screens_dir, layouts_dir=layouts_dir, **kwargs)
    return result.combined


def generate_grouped_mermaid_diagrams(
    spec_dir: Path | str | None,
    screens_dir: Path | str | None = None,
    layouts_dir: Path | str | None = None,
    **kwargs,
) -> dict[str, str]:
    """Separate Mermaid diagrams per group, from the specs.

    ``{"All": NO_SPECS}`` when no spec exists; ``{}`` when specs exist but
    none declares a resolvable transition — callers use the empty mapping to
    suppress the diagram link instead of publishing an empty page.
    """
    if not iter_spec_files(spec_dir):
        return {"All": NO_SPECS_DIAGRAM}
    result = build_diagram(spec_dir, screens_dir=screens_dir, layouts_dir=layouts_dir, **kwargs)
    return result.diagrams


def _external_node_id(from_id: str, raw: str) -> str:
    import hashlib
    digest = hashlib.md5(f"{from_id}\x00{raw}".encode("utf-8")).hexdigest()[:8]
    return f"ext_{digest}"


def _external_lines(externals: list[tuple[str, str]], only_from: set[str] | None = None) -> list[str]:
    """Terminal nodes for ``external`` destinations (canon: "a terminal
    node, never a screen") and the edge into each."""
    lines: list[str] = []
    for from_id, raw in sorted(set(externals)):
        if only_from is not None and from_id not in only_from:
            continue
        node = _external_node_id(from_id, raw)
        lines.append(f'    {node}>"{_escape_label(raw)}"]:::externalNode')
        lines.append(f"    {_emit_node_id(from_id)} --> {node}")
    if lines:
        lines.append("    classDef externalNode fill:#fff3e0,stroke:#ff9800,stroke-dasharray: 4 2")
    return lines


def _click_href(meta: dict, document_href) -> str | None:
    """Where a node's click goes, or ``None`` when it must not have one.

    A screen test's ``source.document`` is the author's choice and wins. With
    no declaration the node falls back to the spec page the site generator
    wrote for that screen — but ONLY if it wrote one. An app-owned screen
    (``licenses``: a drawn node with no spec) gets no click, because emitting
    a href the site never wrote is the same defect as emitting none, pointed
    the other way (2026-09-10, doc-diagram-click-targets-vanish-…).

    The href is relative to the diagram's own directory. Measured, not
    assumed: in both output layouts the site produces —
    ``docs/html/<app>/{diagram.html,specs/}`` and
    ``<app>/docs/html/{diagram.html,specs/}`` — ``specs/`` is the diagram's
    sibling, which is also how the declared ``document`` values resolve.
    """
    document = meta.get("document")
    if document:
        # The declared value says where the page is WRITTEN, not how to reach
        # it from here. `document_href` asks the writer's own mapping and says
        # the answer from the diagram's directory; it is required, never
        # defaulted, because the identity spelling is exactly the bug.
        return document_href(document)
    page = meta.get("spec_page")
    return f"specs/{page}" if page else None


def _group_diagrams(
    nodes: dict[str, str],
    node_metadata: dict[str, dict],
    document_href,
    all_edges: list[tuple[str, str, str]],
    externals: list[tuple[str, str]],
) -> dict[str, str]:
    """Group nodes by their metadata groups (a node may sit in several)."""
    groups: dict[str, set[str]] = {}
    entry_nodes: set[str] = set()

    for node_id, meta in node_metadata.items():
        if meta.get("entry_screen"):
            entry_nodes.add(node_id)
        node_groups = meta.get("groups") or []
        if not node_groups:
            node_groups = ["その他"]
        for group in node_groups:
            groups.setdefault(group, set()).add(node_id)

    diagrams: dict[str, str] = {}
    for group_name in sorted(groups.keys()):
        group_nodes = groups[group_name]

        relevant_entry_nodes = set()
        for entry_node in entry_nodes:
            for from_id, to_id, _kind in all_edges:
                if from_id == entry_node and to_id in group_nodes:
                    relevant_entry_nodes.add(entry_node)
                    break

        group_edges = []
        for from_id, to_id, kind in all_edges:
            from_in_group = from_id in group_nodes or from_id in relevant_entry_nodes
            to_in_group = to_id in group_nodes
            if from_in_group and to_in_group:
                group_edges.append((from_id, to_id, kind))

        lines = ["flowchart LR"]
        if relevant_entry_nodes:
            lines.append("")
            lines.append("    %% Entry screens")
            for node_id in sorted(relevant_entry_nodes):
                lines.append(
                    f'    {_emit_node_id(node_id)}(["{_escape_label(nodes[node_id])}"]):::entryNode'
                )
            lines.append("")
            lines.append("    classDef entryNode fill:#e8f5e9,stroke:#4caf50,stroke-width:3px")

        lines.append("")
        lines.append(f"    %% {group_name}")
        for node_id in sorted(group_nodes):
            if node_id not in relevant_entry_nodes:
                lines.append(
                    f'    {_emit_node_id(node_id)}["{_escape_label(nodes[node_id])}"]'
                )

        if group_edges:
            lines.append("")
            lines.append("    %% Transitions")
            for from_id, to_id, kind in _dedupe_edges(group_edges):
                lines.append(_edge_line(from_id, to_id, kind))

        ext_lines = _external_lines(externals, only_from=group_nodes | relevant_entry_nodes)
        if ext_lines:
            lines.append("")
            lines.append("    %% External destinations")
            lines.extend(ext_lines)

        click_lines = []
        for node_id in sorted(group_nodes | relevant_entry_nodes):
            meta = node_metadata.get(node_id, {})
            href = _click_href(meta, document_href)
            if href:
                safe_tooltip = nodes[node_id].replace('"', "'")
                click_lines.append(
                    f'    click {_emit_node_id(node_id)} "{href}" "{safe_tooltip}"'
                )
        if click_lines:
            lines.append("")
            lines.append("    %% Click events for document links")
            lines.extend(click_lines)

        # A group literally named "All" must not overwrite the All tab.
        key = group_name if group_name != ALL_TAB else f"{group_name} (group)"
        diagrams[key] = "\n".join(lines)

    return diagrams


def _normalize_file_ref(file_ref: str) -> str:
    """Normalize file reference to just the screen name."""
    # Remove path prefixes like "../screens/home/" and get just the file name
    # e.g., "../screens/home/home" -> "home"
    # e.g., "login" -> "login"
    name = file_ref.split("/")[-1]
    # Remove .test.json or .json extension if present
    if name.endswith(".test.json"):
        name = name[:-10]
    elif name.endswith(".json"):
        name = name[:-5]
    return name


def _extract_screen_references(steps: list[dict]) -> list[dict]:
    """Extract file reference steps from flow steps (skip inline actions)."""
    refs = []
    for step in steps:
        if "file" in step:
            # Normalize file reference to screen name only
            normalized = _normalize_file_ref(step["file"])
            refs.append({
                "file": normalized,
                "case": step.get("case"),
                "cases": step.get("cases")
            })
    return refs


def _sanitize_id(name: str) -> str:
    """
    Sanitize a name for use as Mermaid node/subgraph ID.
    Mermaid IDs must be alphanumeric + underscore only.
    Non-ASCII characters are converted to a hash-based ID.
    """
    import re
    import hashlib

    # Replace common separators
    sanitized = name.replace("/", "_").replace("-", "_").replace(".", "_").replace(" ", "_")

    # Check if result contains only valid characters
    if re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', sanitized):
        return sanitized

    # Contains non-ASCII or invalid characters, create a hash-based ID
    # Use prefix + hash for readability
    hash_suffix = hashlib.md5(name.encode('utf-8')).hexdigest()[:8]
    return f"group_{hash_suffix}"


#: Mermaid keywords that cannot stand alone as a node identifier.
_MERMAID_RESERVED = frozenset(
    {"end", "graph", "subgraph", "class", "classDef", "click", "style", "linkStyle", "o", "x"}
)


#: Namespace for subgraph ids. Mermaid's flowchart keeps subgraphs and nodes
#: in ONE id space: a subgraph whose id equals a node inside it makes "the
#: node its own parent" and the WHOLE diagram refuses to render
#: ("would create a cycle"). A group named after its screen — `"group":
#: "mypage"` around the `mypage` node — is the most natural naming there is,
#: and two faces hit it the day the All tab appeared (2026-09-10: 2 of 3 and
#: 2 of 5 subgraphs). Always prefixed, not only on collision: an id space
#: kept apart by construction needs no detector to stay apart.
_SUBGRAPH_PREFIX = "sg_"


def _subgraph_id(group_name: str) -> str:
    return f"{_SUBGRAPH_PREFIX}{_sanitize_id(group_name)}"


def _emit_node_id(screen_id: str) -> str:
    """Diagram-safe identifier for a screen id.

    Screen ids reach us straight from test files, so a space, a non-ASCII
    name or a Mermaid keyword would otherwise emit a broken diagram. A screen
    id that happens to start with the subgraph namespace is pushed out of it.
    """
    safe = _sanitize_id(screen_id)
    if safe in _MERMAID_RESERVED or safe.startswith(_SUBGRAPH_PREFIX):
        return f"{safe}_node"
    return safe


def mermaid_id_problems(code: str) -> list[str]:
    """Ids a flowchart declares both as a subgraph and as a node.

    The browser is the only place this failure used to show, and it showed
    as an empty tab with a red line under it; the CLI's counts (edges,
    ERROR 0, exit 0) said nothing. Checked on every combined diagram at
    generation time so the failure moves from the reader's browser to the
    run that produced it.
    """
    import re
    subgraphs: set[str] = set()
    nodes: set[str] = set()
    for raw in code.splitlines():
        line = raw.strip()
        if not line or line.startswith("%%") or line.startswith("classDef") or line.startswith("click"):
            continue
        m = re.match(r"subgraph\s+([A-Za-z_][A-Za-z0-9_]*)", line)
        if m:
            subgraphs.add(m.group(1))
            continue
        if line == "end" or line.startswith("flowchart"):
            continue
        for token in re.findall(r"(?<![A-Za-z0-9_])([A-Za-z_][A-Za-z0-9_]*)(?=\s*(?:\[|\(|>|-->|-\.->|:::|$))", line):
            nodes.add(token)
    return sorted(subgraphs & nodes)


def _escape_label(label: str) -> str:
    """Escape a display label for use inside a Mermaid node bracket."""
    out = str(label).replace('"', "'").replace("\n", " ")
    for char in ("[", "]", "(", ")", "{", "}", "|"):
        out = out.replace(char, " ")
    return out.strip()


def _dedupe_edges(edges) -> list[tuple[str, str, str]]:
    """Collapse duplicate (from, to) pairs, keeping the first kind seen.

    A pair that occurs both as a forward transition and as a back
    transition stays forward: the forward arrow is the one that carries
    navigational meaning.
    """
    kinds: dict[tuple[str, str], str] = {}
    for from_id, to_id, kind in edges:
        key = (from_id, to_id)
        if key not in kinds or kinds[key] == EDGE_BACK:
            kinds[key] = kind
    return [(from_id, to_id, kind) for (from_id, to_id), kind in sorted(kinds.items())]


def _edge_line(from_id: str, to_id: str, kind: str) -> str:
    """Render one edge. Back navigation uses a dotted arrow so a screen
    pair linked by "go forward, then go back" reads as one round trip
    rather than two equivalent transitions."""
    arrow = "-.->" if kind == EDGE_BACK else "-->"
    return f"    {_emit_node_id(from_id)} {arrow} {_emit_node_id(to_id)}"


def _make_node_id(file_ref: str, case_name: str | None) -> str:
    """Create a unique node ID from file reference and case name."""
    # Sanitize for Mermaid node IDs (alphanumeric and underscore only)
    base = file_ref.replace("/", "_").replace("-", "_").replace(".", "_")
    if case_name:
        case_part = case_name.replace("-", "_").replace(".", "_")
        return f"{base}_{case_part}"
    return base


#: Sentinel for a file name several screen tests claim with DIFFERENT
#: screens. Resolving it would pick one at random, so it resolves to none.
_AMBIGUOUS = object()


def _walk_test_tree(screens_path: Path, flows_path: Path) -> TestTreeIndex:
    """One walk over the test tree, producing everything the diagram needs.

    Reading each test file once and returning all three indexes keeps the
    node ids, their metadata and the file-reference resolution derived from
    the SAME view of the tree — three separate walks are how a node used to
    exist with metadata that belonged to a different file.
    """
    by_screen: dict[str, list[dict]] = {}
    by_file: dict[str, object] = {}
    app_owned: dict[str, list[str]] = {}
    config_cache: dict[Path, dict | None] = {}

    for base in (screens_path, flows_path):
        if not base or not Path(base).is_dir():
            continue
        for path in sorted(Path(base).rglob("*.test.json")):
            _merge_app_owned_groups(path.parent, config_cache, app_owned)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(data, dict) or data.get("type") != "screen":
                continue
            layout = (data.get("source") or {}).get("layout")
            if not isinstance(layout, str) or not layout:
                continue
            screen_id = normalize_screen_ref(layout)
            by_screen.setdefault(screen_id, []).append(data)

            stem = path.name[: -len(".test.json")]
            known = by_file.get(stem)
            if known is not None and known != screen_id:
                by_file[stem] = _AMBIGUOUS
            elif known is None:
                by_file[stem] = screen_id

    return TestTreeIndex(
        by_screen_id=by_screen,
        file_ref_screen_ids={k: v for k, v in by_file.items() if isinstance(v, str)},
        app_owned_groups=app_owned,
    )


def _merge_app_owned_groups(
    directory: Path, cache: dict[Path, dict[str, list[str]]], out: dict[str, list[str]]
) -> None:
    """Collect ``test.appOwnedScreens`` groups from the config owning a test.

    Resolved per test DIRECTORY rather than once for the tree: a multi-app
    project has one config per app, and a diagram spanning both apps needs
    both declarations. An app-owned screen has no layout, so it has no test
    file to carry ``metadata.group`` — the declaration is the only place it
    can say which group it belongs to.

    Both the config location and the declaration shape come from jui_cli;
    when jui is not installed there are simply no declared groups, which is
    the same graceful degradation the classifier already has.
    """
    if directory not in cache:
        project_config = import_jui_cli_module("jui_cli.core.project_config")
        screen_identity = import_jui_cli_module("jui_cli.core.screen_identity")
        if project_config is None or screen_identity is None:
            cache[directory] = {}
        else:
            config, _path = project_config.find_project_config(directory)
            declared = project_config.declared_app_owned_screens(config)
            cache[directory] = screen_identity.app_owned_groups(declared)
    for screen_id, groups in cache[directory].items():
        out.setdefault(screen_id, groups)


def _resolve_screen_metadata(
    screen_id: str, tree: TestTreeIndex, spec_groups: dict[str, list[str]] | None = None
) -> dict:
    """Label / entry_screen / group / document for one screen id.

    With several tests covering one screen, the display name is left as the
    derived title: picking "the first" silently labels a node with another
    screen's test name. Flags and links are merged instead, since those are
    screen-level facts every test on that screen agrees about.

    Groups, in canon precedence: the screen test's ``metadata.group`` wins;
    the spec's ``metadata.group`` fills in for a screen no test names (the
    diagram is drawn from specs, so a screen with a spec and no test needed
    a place to declare one — 22 of 31 nodes on one face had none); the
    jui.config.json app-owned declaration comes last.
    """
    spec_groups = spec_groups or {}
    result = {
        "label": screen_id.replace("_", " ").title(),
        "entry_screen": False,
        "groups": [],
        "document": None,
    }

    tests = tree.by_screen_id.get(screen_id) or []
    if not tests:
        result["groups"] = list(spec_groups.get(screen_id) or tree.app_owned_groups.get(screen_id) or [])
        return result

    names = {
        (t.get("metadata") or {}).get("name")
        for t in tests
        if (t.get("metadata") or {}).get("name")
    }
    if len(names) == 1:
        result["label"] = names.pop()

    groups: list[str] = []
    for test in tests:
        metadata = test.get("metadata") or {}
        if metadata.get("entry_screen"):
            result["entry_screen"] = True
        group_val = metadata.get("group")
        if isinstance(group_val, list):
            groups.extend(str(g) for g in group_val)
        elif isinstance(group_val, str) and group_val:
            groups.append(group_val)
        if result["document"] is None:
            document = (test.get("source") or {}).get("document")
            if isinstance(document, str) and document:
                result["document"] = document

    seen: set[str] = set()
    # A test's own group wins: one screen, one place to look. The
    # declaration only fills in for a screen whose tests declare none.
    result["groups"] = [g for g in groups if not (g in seen or seen.add(g))] or list(
        spec_groups.get(screen_id) or tree.app_owned_groups.get(screen_id) or []
    )
    return result


def _get_screen_metadata(
    file_ref: str,
    screens_path: Path,
    flows_path: Path
) -> dict:
    """
    Get metadata for a screen node from screen test file.

    Args:
        file_ref: File reference (e.g., "login", "home")
        screens_path: Path to screens directory
        flows_path: Path to flows directory

    Returns:
        Dict with 'label', 'entry_screen', 'groups', and 'document' keys
    """
    result = {
        "label": file_ref.replace("_", " ").title(),
        "entry_screen": False,
        "groups": [],
        "document": None
    }

    # Try to find the screen test file
    candidates = [
        screens_path / file_ref / f"{file_ref}.test.json",
        screens_path / f"{file_ref}.test.json",
        screens_path / file_ref / f"{file_ref.split('/')[-1]}.test.json",
        flows_path / f"{file_ref}.test.json",
    ]

    ref_file = None
    for candidate in candidates:
        if candidate.exists():
            ref_file = candidate
            break

    if not ref_file:
        return result

    try:
        with open(ref_file, 'r', encoding='utf-8') as f:
            screen_data = json.load(f)

        metadata = screen_data.get("metadata", {})
        screen_name = metadata.get("name", "")

        if screen_name:
            result["label"] = screen_name

        # Get entry_screen and group from metadata
        result["entry_screen"] = metadata.get("entry_screen", False)
        # Normalize group to list (can be string or array in schema)
        group_val = metadata.get("group")
        if group_val is None:
            result["groups"] = []
        elif isinstance(group_val, list):
            result["groups"] = group_val
        else:
            result["groups"] = [group_val]

        # Get document path from source
        source = screen_data.get("source", {})
        result["document"] = source.get("document")

        return result

    except Exception:
        return result


def _get_screen_label(
    file_ref: str,
    case_name: str | None,
    screens_path: Path,
    flows_path: Path
) -> str:
    """
    Get display label for a screen node from screen test metadata.name.

    Args:
        file_ref: File reference (e.g., "login", "home")
        case_name: Optional case name
        screens_path: Path to screens directory
        flows_path: Path to flows directory

    Returns:
        Display label string
    """
    metadata = _get_screen_metadata(file_ref, screens_path, flows_path)
    label = metadata["label"]

    if case_name:
        # Try to find case-specific label
        candidates = [
            screens_path / file_ref / f"{file_ref}.test.json",
            screens_path / f"{file_ref}.test.json",
            screens_path / file_ref / f"{file_ref.split('/')[-1]}.test.json",
            flows_path / f"{file_ref}.test.json",
        ]

        for candidate in candidates:
            if candidate.exists():
                try:
                    with open(candidate, 'r', encoding='utf-8') as f:
                        screen_data = json.load(f)
                    cases = screen_data.get("cases", [])
                    for case in cases:
                        if case.get("name") == case_name:
                            case_desc = case.get("description", "")
                            if case_desc:
                                return case_desc
                            return f"{label}: {case_name}"
                except Exception:
                    pass
                break

    return label


def _build_mermaid_diagram(
    nodes: dict[str, str],
    edges: list[tuple[str, str, str]],
    node_metadata: dict[str, dict] | None = None,
    externals: list[tuple[str, str]] | None = None,
    *,
    document_href,
) -> str:
    """
    Build the combined Mermaid flowchart diagram string.

    Args:
        nodes: Dict of node_id -> display label
        edges: List of (from_id, to_id, kind) tuples
        node_metadata: Dict of node_id -> {entry_screen, groups, document}
        externals: (from_id, raw) external destinations, drawn as terminal nodes

    Returns:
        Mermaid diagram string
    """
    if node_metadata is None:
        node_metadata = {}
    externals = externals or []

    lines = ["flowchart LR"]

    # Separate entry screens and regular nodes
    entry_nodes = set()
    grouped_nodes: dict[str, list[str]] = {}  # group_name -> list of node_ids
    ungrouped_nodes = []

    for node_id in nodes:
        meta = node_metadata.get(node_id, {})
        if meta.get("entry_screen"):
            entry_nodes.add(node_id)
        else:
            node_groups = meta.get("groups") or []
            if node_groups:
                # Add to first group only for the combined diagram
                group = node_groups[0]
                if group not in grouped_nodes:
                    grouped_nodes[group] = []
                grouped_nodes[group].append(node_id)
            else:
                ungrouped_nodes.append(node_id)

    # Define entry screen nodes first (standalone, not in subgraph)
    if entry_nodes:
        lines.append("")
        lines.append("    %% Entry screens")
        for node_id in sorted(entry_nodes):
            lines.append(
                f'    {_emit_node_id(node_id)}(["{_escape_label(nodes[node_id])}"]):::entryNode'
            )
        lines.append("")
        lines.append("    classDef entryNode fill:#e8f5e9,stroke:#4caf50,stroke-width:3px")

    # Define grouped nodes in subgraphs
    for group_name in sorted(grouped_nodes.keys()):
        group_node_ids = grouped_nodes[group_name]
        # Subgraph id lives in its own namespace — see _SUBGRAPH_PREFIX.
        group_id = _subgraph_id(group_name)
        lines.append("")
        lines.append(f'    subgraph {group_id}["{_escape_label(group_name)}"]')
        for node_id in sorted(group_node_ids):
            lines.append(
                f'        {_emit_node_id(node_id)}["{_escape_label(nodes[node_id])}"]'
            )
        lines.append("    end")

    # Define ungrouped nodes
    if ungrouped_nodes:
        lines.append("")
        lines.append("    %% Other screens")
        for node_id in sorted(ungrouped_nodes):
            lines.append(f'    {_emit_node_id(node_id)}["{_escape_label(nodes[node_id])}"]')

    # Build unique edges (deduplicate same source->target pairs)
    unique_edges = _dedupe_edges(edges)

    # Separate entry screen edges (output first for LR layout positioning)
    entry_edges = [e for e in unique_edges if e[0] in entry_nodes]
    other_edges = [e for e in unique_edges if e[0] not in entry_nodes]

    # Add edges - entry screen edges first for left positioning in LR layout
    lines.append("")
    lines.append("    %% Transitions")
    for from_id, to_id, kind in entry_edges:
        lines.append(_edge_line(from_id, to_id, kind))
    for from_id, to_id, kind in other_edges:
        lines.append(_edge_line(from_id, to_id, kind))

    ext_lines = _external_lines(externals)
    if ext_lines:
        lines.append("")
        lines.append("    %% External destinations")
        lines.extend(ext_lines)

    # Add click events for nodes with document links
    click_lines = []
    for node_id in sorted(nodes):
        meta = node_metadata.get(node_id, {})
        href = _click_href(meta, document_href)
        if href:
            safe_tooltip = nodes[node_id].replace('"', "'")
            click_lines.append(
                f'    click {_emit_node_id(node_id)} "{href}" "{safe_tooltip}"'
            )

    if click_lines:
        lines.append("")
        lines.append("    %% Click events for document links")
        lines.extend(click_lines)

    return "\n".join(lines)


def generate_mermaid_html(
    spec_dir: Path | str | None,
    output_path: Path,
    title: str = "Flow Diagram",
    screens_dir: Path | str | None = None,
    layouts_dir: Path | str | None = None,
    *,
    flows_dir: Path | str | None = None,
    aliases=(),
    app_owned=(),
    app_owned_transitions: dict[str, list[str]] | None = None,
    site_root: Path | str | None = None,
    document_href,
) -> DiagramResult:
    """Write the tabbed diagram page for one owner and return what happened.

    ``site_root`` is the directory holding the site's ``index.html``; the
    page's "Back to Index" link is written RELATIVE to it. Without it the
    link is ``index.html`` beside the page — right for a page at the root,
    a 404 for an app's page under ``<app>/`` (reported by the user
    2026-09-10: every per-app diagram since v1.8.64 linked to
    ``<app>/index.html``, which does not exist).

    The page is written only when something was drawable
    (``result.combined`` non-empty); callers suppress the link otherwise —
    publishing a page with zero tabs used to render blank. The page carries
    the check's findings too: every flow-test transition absent from the
    specs, and every destination treated as absent, so the reader who opens
    the diagram sees why an edge they expected is missing.
    """
    result = build_diagram(
        spec_dir, flows_dir=flows_dir, screens_dir=screens_dir, layouts_dir=layouts_dir,
        aliases=aliases, app_owned=app_owned, app_owned_transitions=app_owned_transitions,
        document_href=document_href,
    )
    if not result.diagrams:
        return result

    output_path = Path(output_path)
    html_content = _generate_tabbed_mermaid_html_page(
        result.diagrams, title, errors=result.errors, unresolved=result.unresolved,
        nones=result.nones, index_href=index_href_for(output_path, site_root))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    return result


def index_href_for(page_path: Path | str, site_root: Path | str | None) -> str:
    """The relative href from a page to the site's ``index.html``.

    ``diagram.html`` at the root → ``index.html``; ``user/diagram.html`` →
    ``../index.html``. With no site root the page is assumed to sit beside
    the index (the standalone ``generate mermaid -o`` case).
    """
    if site_root is None:
        return "index.html"
    import os
    target = Path(site_root).resolve() / "index.html"
    return os.path.relpath(target, Path(page_path).resolve().parent).replace(os.sep, "/")


def _issues_html(errors, unresolved, nones=()) -> str:
    """The check's findings, on the page the reader is already looking at."""
    parts: list[str] = []
    if errors:
        items = "".join(
            f"<li><code>{escape_html(e.from_id)} &rarr; {escape_html(e.to_id)}</code> "
            f"&mdash; {escape_html(e.reason)} "
            f"<span class='issue-src'>(flow test &ldquo;{escape_html(e.flow_name)}&rdquo;, "
            f"{escape_html(e.flow_file)})</span></li>"
            for e in errors)
        parts.append(
            f'<div class="issues errors"><h2>ERROR: {len(errors)} transition(s) found in flow '
            f'tests but absent from the specs</h2>'
            f'<p>A flow test navigates where its spec declares no transition. Declare it in the '
            f'spec (<code>transitions[].destination</code>), or in <code>jui.config.json</code> '
            f'<code>test.appOwnedScreens[].transitions</code> for a screen that has no layout.</p>'
            f'<ul>{items}</ul></div>')
    if unresolved:
        items = "".join(
            f"<li><code>{escape_html(u.source)}</code>: &ldquo;{escape_html(u.raw)}&rdquo; "
            f"<span class='issue-src'>({escape_html(u.kind)}: {escape_html(u.why)})</span></li>"
            for u in unresolved)
        parts.append(
            f'<div class="issues unresolved"><h2>WARNING: {len(unresolved)} destination(s) could '
            f'not be resolved and were treated as absent</h2>'
            f'<p>Not drawn, and not an error by themselves. Name the screen id, declare an alias '
            f'(<code>spec.transitionAliases</code>), or declare the destination as '
            f'<code>none</code> / external.</p><ul>{items}</ul></div>')
    if nones:
        items = "".join(
            f"<li><code>{escape_html(u.source)}</code>: &ldquo;{escape_html(u.raw)}&rdquo;</li>"
            for u in nones)
        parts.append(
            f'<div class="issues nones"><h2>INFO: {len(nones)} destination(s) read as '
            f'&ldquo;no screen transition&rdquo; from their wording</h2>'
            f'<p>Not drawn, by declaration. Listed because the kind is inferred from words such as '
            f'画面内 / SPA / tab — a screen name that happens to contain one lands here too, and a reader '
            f'could not otherwise tell the two apart.</p><ul>{items}</ul></div>')
    return "\n".join(parts)


def _generate_tabbed_mermaid_html_page(
    diagrams: dict[str, str], title: str, errors=(), unresolved=(), nones=(),
    index_href: str = "index.html",
) -> str:
    """Generate HTML page with tabs for each group diagram."""
    issues_html = _issues_html(list(errors), list(unresolved), list(nones))

    # Build tab buttons and content
    tab_buttons = []
    tab_contents = []
    ordered = sorted(diagrams.items(), key=lambda kv: (kv[0] != ALL_TAB, kv[0]))
    for i, (group_name, mermaid_code) in enumerate(ordered):
        active_class = " active" if i == 0 else ""
        tab_id = f"tab-{i}"

        tab_buttons.append(
            f'<button class="tab-btn{active_class}" onclick="showTab(\'{tab_id}\')" data-tab="{tab_id}">{escape_html(group_name)}</button>'
        )

        display = "block" if i == 0 else "none"
        tab_contents.append(f'''
            <div class="tab-content" id="{tab_id}" style="display: {display}">
                <div class="diagram-wrapper" id="wrapper-{tab_id}">
                    <div class="diagram-container" id="container-{tab_id}">
                        <pre class="mermaid">
{mermaid_code}
                        </pre>
                    </div>
                </div>
            </div>''')

    tabs_html = "\n".join(tab_buttons)
    contents_html = "\n".join(tab_contents)

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{escape_html(title)}</title>
    <script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
    <style>
        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: #f5f5f5;
            min-height: 100vh;
            padding: 20px;
        }}

        .container {{
            max-width: 100%;
            margin: 0 auto;
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            overflow: hidden;
        }}

        .header {{
            padding: 20px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }}

        .header h1 {{
            font-size: 24px;
            font-weight: 600;
        }}

        .header .subtitle {{
            font-size: 14px;
            opacity: 0.9;
            margin-top: 5px;
        }}

        .toolbar {{
            padding: 15px 20px;
            background: #fafafa;
            border-bottom: 1px solid #eee;
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
            align-items: center;
        }}

        .toolbar a {{
            padding: 8px 16px;
            background: #667eea;
            color: white;
            text-decoration: none;
            border-radius: 4px;
            font-size: 14px;
            transition: background 0.2s;
        }}

        .toolbar a:hover {{
            background: #5a6fd6;
        }}

        .toolbar .info {{
            margin-left: auto;
            font-size: 12px;
            color: #666;
        }}

        /* Zoom controls */
        .zoom-controls {{
            display: flex;
            align-items: center;
            gap: 8px;
            margin-left: 20px;
            padding: 4px 12px;
            background: #fff;
            border: 1px solid #ddd;
            border-radius: 6px;
        }}

        .zoom-controls button {{
            width: 32px;
            height: 32px;
            border: none;
            background: #f0f0f0;
            border-radius: 4px;
            cursor: pointer;
            font-size: 18px;
            font-weight: bold;
            color: #333;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: background 0.2s;
        }}

        .zoom-controls button:hover {{
            background: #e0e0e0;
        }}

        .zoom-controls button:active {{
            background: #d0d0d0;
        }}

        .zoom-level {{
            min-width: 50px;
            text-align: center;
            font-size: 14px;
            font-weight: 500;
            color: #333;
        }}

        /* Tab styles */
        .tabs {{
            display: flex;
            flex-wrap: wrap;
            gap: 4px;
            padding: 15px 20px;
            background: #f8f8f8;
            border-bottom: 1px solid #ddd;
        }}

        .tab-btn {{
            padding: 10px 20px;
            border: 1px solid #ddd;
            background: white;
            border-radius: 6px 6px 0 0;
            cursor: pointer;
            font-size: 14px;
            font-weight: 500;
            color: #666;
            transition: all 0.2s;
            margin-bottom: -1px;
        }}

        .tab-btn:hover {{
            background: #f0f0f0;
            color: #333;
        }}

        .tab-btn.active {{
            background: white;
            color: #667eea;
            border-bottom-color: white;
            font-weight: 600;
        }}

        .tab-content {{
            min-height: 400px;
        }}

        .issues {{
            margin: 16px 20px 24px;
            padding: 14px 18px;
            border-radius: 6px;
            border-left: 5px solid #999;
            background: #fafafa;
            font-size: 14px;
        }}

        .issues h2 {{
            font-size: 15px;
            margin-bottom: 6px;
        }}

        .issues p {{
            margin-bottom: 8px;
            color: #444;
        }}

        .issues ul {{
            margin-left: 20px;
        }}

        .issues li {{
            margin: 3px 0;
        }}

        .issues .issue-src {{
            color: #777;
            font-size: 12px;
        }}

        .issues.errors {{
            border-left-color: #d32f2f;
            background: #fdecea;
        }}

        .issues.unresolved {{
            border-left-color: #ff9800;
            background: #fff3e0;
        }}

        .issues.nones {{
            border-left-color: #90a4ae;
            background: #eceff1;
        }}

        .diagram-wrapper {{
            overflow: auto;
            min-height: 400px;
            max-height: calc(100vh - 300px);
            position: relative;
            cursor: grab;
        }}

        .diagram-wrapper:active {{
            cursor: grabbing;
        }}

        .diagram-container {{
            padding: 30px;
            transform-origin: top left;
            transition: transform 0.1s ease-out;
            display: inline-block;
            min-width: 100%;
        }}

        .mermaid {{
            display: flex;
            justify-content: center;
        }}

        .mermaid svg {{
            max-width: none !important;
            height: auto;
        }}

        .footer {{
            padding: 15px 20px;
            background: #fafafa;
            border-top: 1px solid #eee;
            font-size: 12px;
            color: #666;
            text-align: center;
        }}

        .mermaid .node rect {{
            fill: #e3f2fd;
            stroke: #1976d2;
            stroke-width: 2px;
            rx: 5px;
            ry: 5px;
        }}

        .mermaid .edgePath .path {{
            stroke: #666;
            stroke-width: 2px;
        }}

        @media (max-width: 768px) {{
            body {{
                padding: 10px;
            }}

            .header {{
                padding: 15px;
            }}

            .header h1 {{
                font-size: 20px;
            }}

            .diagram-container {{
                padding: 15px;
            }}

            .tabs {{
                padding: 10px;
            }}

            .tab-btn {{
                padding: 8px 12px;
                font-size: 12px;
            }}

            .zoom-controls {{
                margin-left: 0;
                margin-top: 10px;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{escape_html(title)}</h1>
            <div class="subtitle">Screen transitions by group &mdash; drawn from the screen specs; flow tests are checked against them</div>
        </div>

        <div class="toolbar">
            <a href="{index_href}">Back to Index</a>
            <div class="zoom-controls">
                <button onclick="zoomOut()" title="Zoom Out">-</button>
                <span class="zoom-level" id="zoomLevel">100%</span>
                <button onclick="zoomIn()" title="Zoom In">+</button>
                <button onclick="resetZoom()" title="Reset Zoom" style="font-size: 12px; width: auto; padding: 0 8px;">Reset</button>
                <button onclick="fitToScreen()" title="Fit to Screen" style="font-size: 12px; width: auto; padding: 0 8px;">Fit</button>
            </div>
            <span class="info">Generated: {build_datetime().strftime('%Y-%m-%d %H:%M:%S')}</span>
        </div>

        <div class="tabs">
            {tabs_html}
        </div>

        {contents_html}
        {issues_html}

        <div class="footer">
            Generated by JsonUI Test CLI
        </div>
    </div>

    <script>
        // Track which tabs have been rendered
        const renderedTabs = new Set();

        // Zoom state per tab
        const tabZoomState = {{}};
        let currentTabId = 'tab-0';

        // Zoom constants
        const minZoom = 0.25;
        const maxZoom = 3;
        const zoomStep = 0.25;

        function getZoomState(tabId) {{
            if (!tabZoomState[tabId]) {{
                tabZoomState[tabId] = {{ zoom: 1 }};
            }}
            return tabZoomState[tabId];
        }}

        function updateZoomDisplay() {{
            const state = getZoomState(currentTabId);
            document.getElementById('zoomLevel').textContent = Math.round(state.zoom * 100) + '%';

            const container = document.querySelector(`#${{currentTabId}} .diagram-container`);
            if (container) {{
                container.style.transform = `scale(${{state.zoom}})`;
            }}
        }}

        function zoomIn() {{
            const state = getZoomState(currentTabId);
            if (state.zoom < maxZoom) {{
                state.zoom = Math.min(state.zoom + zoomStep, maxZoom);
                updateZoomDisplay();
            }}
        }}

        function zoomOut() {{
            const state = getZoomState(currentTabId);
            if (state.zoom > minZoom) {{
                state.zoom = Math.max(state.zoom - zoomStep, minZoom);
                updateZoomDisplay();
            }}
        }}

        function resetZoom() {{
            const state = getZoomState(currentTabId);
            state.zoom = 1;
            updateZoomDisplay();

            const wrapper = document.querySelector(`#${{currentTabId}} .diagram-wrapper`);
            if (wrapper) {{
                wrapper.scrollLeft = 0;
                wrapper.scrollTop = 0;
            }}
        }}

        function fitToScreen() {{
            const container = document.querySelector(`#${{currentTabId}} .diagram-container`);
            const wrapper = document.querySelector(`#${{currentTabId}} .diagram-wrapper`);
            const state = getZoomState(currentTabId);

            if (container && wrapper) {{
                const svg = container.querySelector('svg');
                if (svg) {{
                    const svgWidth = svg.getBoundingClientRect().width / state.zoom;
                    const svgHeight = svg.getBoundingClientRect().height / state.zoom;
                    const wrapperWidth = wrapper.clientWidth - 60;
                    const wrapperHeight = wrapper.clientHeight - 60;

                    const scaleX = wrapperWidth / svgWidth;
                    const scaleY = wrapperHeight / svgHeight;
                    state.zoom = Math.min(scaleX, scaleY, maxZoom);
                    state.zoom = Math.max(state.zoom, minZoom);
                    updateZoomDisplay();
                }}
            }}
        }}

        async function showTab(tabId) {{
            currentTabId = tabId;

            // Hide all tab contents
            document.querySelectorAll('.tab-content').forEach(content => {{
                content.style.display = 'none';
            }});

            // Remove active class from all buttons
            document.querySelectorAll('.tab-btn').forEach(btn => {{
                btn.classList.remove('active');
            }});

            // Show selected tab content
            document.getElementById(tabId).style.display = 'block';

            // Add active class to clicked button
            document.querySelector(`[data-tab="${{tabId}}"]`).classList.add('active');

            // Render mermaid for this tab if not already done
            if (!renderedTabs.has(tabId)) {{
                const container = document.getElementById(tabId);
                const mermaidPre = container.querySelector('pre.mermaid');
                if (mermaidPre) {{
                    try {{
                        const code = mermaidPre.textContent;
                        const {{ svg }} = await mermaid.render('mermaid-' + tabId, code);
                        mermaidPre.innerHTML = svg;
                        mermaidPre.classList.remove('mermaid');
                        renderedTabs.add(tabId);
                    }} catch (e) {{
                        console.error('Mermaid render error:', e);
                        mermaidPre.innerHTML = '<div style="color:red;">Diagram render error: ' + e.message + '</div>';
                    }}
                }}
            }}

            // Update zoom display for this tab
            updateZoomDisplay();
        }}

        // Initialize Mermaid (don't auto-render on load)
        mermaid.initialize({{
            startOnLoad: false,
            theme: 'default',
            flowchart: {{
                useMaxWidth: false,
                htmlLabels: true,
                curve: 'basis'
            }},
            securityLevel: 'loose'
        }});

        // Render the first tab on page load
        document.addEventListener('DOMContentLoaded', function() {{
            showTab('tab-0');

            // Mouse wheel zoom (for all diagram wrappers)
            document.querySelectorAll('.diagram-wrapper').forEach(wrapper => {{
                wrapper.addEventListener('wheel', function(e) {{
                    if (e.ctrlKey || e.metaKey) {{
                        e.preventDefault();
                        if (e.deltaY < 0) {{
                            zoomIn();
                        }} else {{
                            zoomOut();
                        }}
                    }}
                }}, {{ passive: false }});

                // Drag to pan
                let isDragging = false;
                let startX, startY, scrollLeft, scrollTop;

                wrapper.addEventListener('mousedown', (e) => {{
                    isDragging = true;
                    startX = e.pageX - wrapper.offsetLeft;
                    startY = e.pageY - wrapper.offsetTop;
                    scrollLeft = wrapper.scrollLeft;
                    scrollTop = wrapper.scrollTop;
                }});

                wrapper.addEventListener('mouseleave', () => {{
                    isDragging = false;
                }});

                wrapper.addEventListener('mouseup', () => {{
                    isDragging = false;
                }});

                wrapper.addEventListener('mousemove', (e) => {{
                    if (!isDragging) return;
                    e.preventDefault();
                    const x = e.pageX - wrapper.offsetLeft;
                    const y = e.pageY - wrapper.offsetTop;
                    const walkX = (x - startX) * 1.5;
                    const walkY = (y - startY) * 1.5;
                    wrapper.scrollLeft = scrollLeft - walkX;
                    wrapper.scrollTop = scrollTop - walkY;
                }});
            }});
        }});
    </script>
</body>
</html>'''

    return html
