"""Mermaid flowchart diagram generation from flow tests."""

from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime
from typing import Any

from ..html.sidebar import escape_html
from .flow_graph import (
    EDGE_BACK,
    ScreenResolver,
    flow_edges,
    load_flow,
    normalize_screen_ref,
)


def _collect_flow_graph(
    flows_path: Path,
    screens_path: Path,
    layouts_dir: Path | None = None,
) -> tuple[dict[str, str], dict[str, dict], list[tuple[str, str, str, str]], dict[str, list[str]]]:
    """Walk every flow test once and return the whole graph.

    Returns ``(nodes, node_metadata, edges, flow_subgraphs)`` where an edge
    is ``(from_id, to_id, flow_name, kind)``. This is the single collection
    pass — the combined and grouped builders both consume it, so their
    node sets can no longer drift apart.
    """
    resolver = ScreenResolver(layouts_dir)
    screen_lookup = _build_screen_test_lookup(screens_path, flows_path)

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
            print(f"  Warning: Error processing {flow_file}: {e}")
            continue

        if not flow_nodes:
            continue

        for screen_id in flow_nodes:
            if screen_id in nodes:
                continue
            meta = _resolve_screen_metadata(screen_id, screen_lookup)
            nodes[screen_id] = meta["label"]
            node_metadata[screen_id] = {
                "entry_screen": meta["entry_screen"],
                "groups": meta["groups"],
                "document": meta["document"],
            }

        flow_subgraphs[flow_name] = flow_nodes
        for from_id, to_id, kind in flow_transitions:
            edges.append((from_id, to_id, flow_name, kind))

    return nodes, node_metadata, edges, flow_subgraphs


def generate_mermaid_diagram(
    flows_dir: Path,
    screens_dir: Path | None = None,
    layouts_dir: Path | None = None,
) -> str:
    """
    Generate a Mermaid flowchart diagram from all flow tests in a directory.

    Args:
        flows_dir: Directory containing flow test files
        screens_dir: Optional directory containing screen test files (defaults to sibling screens/)
        layouts_dir: Optional layout tree; enables screen/cell classification
            so Collection cells stop appearing as screens.

    Returns:
        Mermaid diagram string
    """
    flows_path = Path(flows_dir)

    # Default screens dir to sibling directory
    if screens_dir is None:
        screens_path = flows_path.parent / "screens"
    else:
        screens_path = Path(screens_dir)

    if not sorted(flows_path.rglob("*.test.json")):
        return "flowchart LR\n    NO_FLOWS[No flow tests found]"

    all_nodes, node_metadata, all_edges, flow_subgraphs = _collect_flow_graph(
        flows_path, screens_path, layouts_dir
    )

    # Generate Mermaid diagram
    return _build_mermaid_diagram(all_nodes, all_edges, flow_subgraphs, node_metadata)


def generate_grouped_mermaid_diagrams(
    flows_dir: Path,
    screens_dir: Path | None = None,
    layouts_dir: Path | None = None,
) -> dict[str, str]:
    """
    Generate separate Mermaid diagrams for each group.

    Args:
        flows_dir: Directory containing flow test files
        screens_dir: Optional directory containing screen test files
        layouts_dir: Optional layout tree; enables screen/cell classification

    Returns:
        Dict of group_name -> mermaid_code. Empty when no flow yields a
        screen — callers use that to suppress the diagram link instead of
        publishing an empty page.
    """
    flows_path = Path(flows_dir)

    if screens_dir is None:
        screens_path = flows_path.parent / "screens"
    else:
        screens_path = Path(screens_dir)

    flow_files = sorted(flows_path.rglob("*.test.json"))

    if not flow_files:
        return {"All": "flowchart LR\n    NO_FLOWS[No flow tests found]"}

    all_nodes, node_metadata, all_edges, _flow_subgraphs = _collect_flow_graph(
        flows_path, screens_path, layouts_dir
    )

    if not all_nodes:
        return {}

    # Group nodes by their groups metadata (nodes can belong to multiple groups)
    groups: dict[str, set[str]] = {}
    entry_nodes: set[str] = set()

    for node_id, meta in node_metadata.items():
        if meta.get("entry_screen"):
            entry_nodes.add(node_id)
        node_groups = meta.get("groups") or []
        if not node_groups:
            node_groups = ["その他"]
        for group in node_groups:
            if group not in groups:
                groups[group] = set()
            groups[group].add(node_id)

    # Build diagram for each group
    diagrams: dict[str, str] = {}

    for group_name in sorted(groups.keys()):
        group_nodes = groups[group_name]

        # Include entry nodes in the diagram if they connect to this group
        relevant_entry_nodes = set()
        for entry_node in entry_nodes:
            for from_id, to_id, _flow_name, _kind in all_edges:
                if from_id == entry_node and to_id in group_nodes:
                    relevant_entry_nodes.add(entry_node)
                    break

        # Get edges within this group or from entry nodes to this group
        group_edges = []
        for from_id, to_id, _flow_name, kind in all_edges:
            from_in_group = from_id in group_nodes or from_id in relevant_entry_nodes
            to_in_group = to_id in group_nodes
            if from_in_group and to_in_group:
                group_edges.append((from_id, to_id, kind))

        # Build mermaid for this group
        lines = ["flowchart LR"]

        # Add entry nodes first
        if relevant_entry_nodes:
            lines.append("")
            lines.append("    %% Entry screens")
            for node_id in sorted(relevant_entry_nodes):
                lines.append(
                    f'    {_emit_node_id(node_id)}(["{_escape_label(all_nodes[node_id])}"]):::entryNode'
                )
            lines.append("")
            lines.append("    classDef entryNode fill:#e8f5e9,stroke:#4caf50,stroke-width:3px")

        # Add group nodes
        lines.append("")
        lines.append(f"    %% {group_name}")
        for node_id in sorted(group_nodes):
            if node_id not in relevant_entry_nodes:
                lines.append(
                    f'    {_emit_node_id(node_id)}["{_escape_label(all_nodes[node_id])}"]'
                )

        # Add edges
        if group_edges:
            lines.append("")
            lines.append("    %% Transitions")
            for from_id, to_id, kind in _dedupe_edges(group_edges):
                lines.append(_edge_line(from_id, to_id, kind))

        # Add click events for nodes with document links
        click_lines = []
        all_group_node_ids = group_nodes | relevant_entry_nodes
        for node_id in sorted(all_group_node_ids):
            meta = node_metadata.get(node_id, {})
            document = meta.get("document")
            if document:
                safe_tooltip = all_nodes[node_id].replace('"', "'")
                click_lines.append(
                    f'    click {_emit_node_id(node_id)} "{document}" "{safe_tooltip}"'
                )

        if click_lines:
            lines.append("")
            lines.append("    %% Click events for document links")
            lines.extend(click_lines)

        diagrams[group_name] = "\n".join(lines)

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


def _emit_node_id(screen_id: str) -> str:
    """Diagram-safe identifier for a screen id.

    Screen ids reach us straight from test files, so a space, a non-ASCII
    name or a Mermaid keyword would otherwise emit a broken diagram.
    """
    safe = _sanitize_id(screen_id)
    if safe in _MERMAID_RESERVED:
        return f"{safe}_node"
    return safe


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


def _build_screen_test_lookup(screens_path: Path, flows_path: Path) -> dict[str, list[dict]]:
    """Index every screen test by the canonical screen id it covers.

    The id comes from ``source.layout``'s basename — the file's own name is
    unreliable because one screen commonly has several test files
    (``login_smoke``, ``login_tier2a_scroll_conditions``, ...) and because
    a test whose steps start on another screen legitimately points its
    ``source.layout`` elsewhere.
    """
    lookup: dict[str, list[dict]] = {}
    for base in (screens_path, flows_path):
        if not base or not Path(base).is_dir():
            continue
        for path in sorted(Path(base).rglob("*.test.json")):
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
            lookup.setdefault(normalize_screen_ref(layout), []).append(data)
    return lookup


def _resolve_screen_metadata(screen_id: str, lookup: dict[str, list[dict]]) -> dict:
    """Label / entry_screen / group / document for one screen id.

    With several tests covering one screen, the display name is left as the
    derived title: picking "the first" silently labels a node with another
    screen's test name. Flags and links are merged instead, since those are
    screen-level facts every test on that screen agrees about.
    """
    result = {
        "label": screen_id.replace("_", " ").title(),
        "entry_screen": False,
        "groups": [],
        "document": None,
    }

    tests = lookup.get(screen_id) or []
    if not tests:
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
    result["groups"] = [g for g in groups if not (g in seen or seen.add(g))]
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
    subgraphs: dict[str, list[str]],
    node_metadata: dict[str, dict] | None = None
) -> str:
    """
    Build the Mermaid flowchart diagram string.

    Args:
        nodes: Dict of node_id -> display label
        edges: List of (from_id, to_id, flow_name) tuples
        subgraphs: Dict of flow_name -> list of node_ids
        node_metadata: Dict of node_id -> {entry_screen, groups}

    Returns:
        Mermaid diagram string
    """
    if node_metadata is None:
        node_metadata = {}

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
        # Sanitize group name for subgraph ID (must be alphanumeric + underscore only)
        group_id = _sanitize_id(group_name)
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
    unique_edges = _dedupe_edges((from_id, to_id, kind) for from_id, to_id, _flow, kind in edges)

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

    # Add click events for nodes with document links
    click_lines = []
    for node_id in sorted(nodes):
        meta = node_metadata.get(node_id, {})
        document = meta.get("document")
        if document:
            safe_tooltip = nodes[node_id].replace('"', "'")
            click_lines.append(
                f'    click {_emit_node_id(node_id)} "{document}" "{safe_tooltip}"'
            )

    if click_lines:
        lines.append("")
        lines.append("    %% Click events for document links")
        lines.extend(click_lines)

    return "\n".join(lines)


def generate_mermaid_html(
    flows_dir: Path,
    output_path: Path,
    title: str = "Flow Diagram",
    screens_dir: Path | None = None,
    layouts_dir: Path | None = None,
) -> str:
    """
    Generate an HTML page with embedded Mermaid diagrams (one per group).

    Args:
        flows_dir: Directory containing flow test files
        output_path: Path to write HTML file
        title: Page title
        screens_dir: Optional directory containing screen test files
        layouts_dir: Optional layout tree; enables screen/cell classification

    Returns:
        The generated Mermaid diagram string (combined), or an empty string
        when no flow yields a screen. Callers MUST treat the empty string as
        "no diagram" and suppress the link: publishing a page with zero tabs
        used to render a blank page (its tab script has no tab to select).

    Raises:
        Nothing — an empty result is a normal outcome, not an error.
    """
    # Generate grouped diagrams
    grouped_diagrams = generate_grouped_mermaid_diagrams(flows_dir, screens_dir, layouts_dir)

    if not grouped_diagrams:
        return ""

    html_content = _generate_tabbed_mermaid_html_page(grouped_diagrams, title)

    # Write HTML file
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)

    # Return combined for backward compatibility
    return "\n\n".join(grouped_diagrams.values())


def _generate_mermaid_html_page(mermaid_code: str, title: str) -> str:
    """Generate the HTML page content with Mermaid diagram."""

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

        .diagram-wrapper {{
            overflow: auto;
            min-height: 400px;
            max-height: calc(100vh - 250px);
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

        /* Mermaid node styling */
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

        .mermaid .edgeLabel {{
            background: white;
            padding: 2px 5px;
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
            <div class="subtitle">Screen transition diagram generated from flow tests</div>
        </div>

        <div class="toolbar">
            <a href="index.html">Back to Index</a>
            <div class="zoom-controls">
                <button onclick="zoomOut()" title="Zoom Out">-</button>
                <span class="zoom-level" id="zoomLevel">100%</span>
                <button onclick="zoomIn()" title="Zoom In">+</button>
                <button onclick="resetZoom()" title="Reset Zoom" style="font-size: 12px; width: auto; padding: 0 8px;">Reset</button>
                <button onclick="fitToScreen()" title="Fit to Screen" style="font-size: 12px; width: auto; padding: 0 8px;">Fit</button>
            </div>
            <span class="info">Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</span>
        </div>

        <div class="diagram-wrapper" id="diagramWrapper">
            <div class="diagram-container" id="diagramContainer">
                <pre class="mermaid">
{mermaid_code}
                </pre>
            </div>
        </div>

        <div class="footer">
            Generated by JsonUI Test CLI
        </div>
    </div>

    <script>
        let currentZoom = 1;
        const minZoom = 0.25;
        const maxZoom = 3;
        const zoomStep = 0.25;

        const container = document.getElementById('diagramContainer');
        const wrapper = document.getElementById('diagramWrapper');
        const zoomLevelEl = document.getElementById('zoomLevel');

        function updateZoom() {{
            container.style.transform = `scale(${{currentZoom}})`;
            zoomLevelEl.textContent = Math.round(currentZoom * 100) + '%';
        }}

        function zoomIn() {{
            if (currentZoom < maxZoom) {{
                currentZoom = Math.min(currentZoom + zoomStep, maxZoom);
                updateZoom();
            }}
        }}

        function zoomOut() {{
            if (currentZoom > minZoom) {{
                currentZoom = Math.max(currentZoom - zoomStep, minZoom);
                updateZoom();
            }}
        }}

        function resetZoom() {{
            currentZoom = 1;
            updateZoom();
            wrapper.scrollLeft = 0;
            wrapper.scrollTop = 0;
        }}

        function fitToScreen() {{
            const svg = container.querySelector('svg');
            if (svg) {{
                const svgWidth = svg.getBoundingClientRect().width / currentZoom;
                const svgHeight = svg.getBoundingClientRect().height / currentZoom;
                const wrapperWidth = wrapper.clientWidth - 60;
                const wrapperHeight = wrapper.clientHeight - 60;

                const scaleX = wrapperWidth / svgWidth;
                const scaleY = wrapperHeight / svgHeight;
                currentZoom = Math.min(scaleX, scaleY, maxZoom);
                currentZoom = Math.max(currentZoom, minZoom);
                updateZoom();
            }}
        }}

        // Mouse wheel zoom
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

        // Initialize Mermaid
        mermaid.initialize({{
            startOnLoad: true,
            theme: 'default',
            flowchart: {{
                useMaxWidth: false,
                htmlLabels: true,
                curve: 'basis'
            }},
            securityLevel: 'loose'
        }});
    </script>
</body>
</html>'''

    return html


def _generate_tabbed_mermaid_html_page(diagrams: dict[str, str], title: str) -> str:
    """Generate HTML page with tabs for each group diagram."""

    # Build tab buttons and content
    tab_buttons = []
    tab_contents = []
    for i, (group_name, mermaid_code) in enumerate(sorted(diagrams.items())):
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
            <div class="subtitle">Screen transition diagrams by group</div>
        </div>

        <div class="toolbar">
            <a href="index.html">Back to Index</a>
            <div class="zoom-controls">
                <button onclick="zoomOut()" title="Zoom Out">-</button>
                <span class="zoom-level" id="zoomLevel">100%</span>
                <button onclick="zoomIn()" title="Zoom In">+</button>
                <button onclick="resetZoom()" title="Reset Zoom" style="font-size: 12px; width: auto; padding: 0 8px;">Reset</button>
                <button onclick="fitToScreen()" title="Fit to Screen" style="font-size: 12px; width: auto; padding: 0 8px;">Fit</button>
            </div>
            <span class="info">Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</span>
        </div>

        <div class="tabs">
            {tabs_html}
        </div>

        {contents_html}

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
