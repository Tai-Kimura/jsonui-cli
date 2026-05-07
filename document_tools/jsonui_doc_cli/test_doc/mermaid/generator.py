"""Mermaid flowchart diagram generation from flow tests."""

from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime
from typing import Any

from ..html.sidebar import escape_html


def generate_mermaid_diagram(
    flows_dir: Path,
    screens_dir: Path | None = None
) -> str:
    """
    Generate a Mermaid flowchart diagram from all flow tests in a directory.

    Args:
        flows_dir: Directory containing flow test files
        screens_dir: Optional directory containing screen test files (defaults to sibling screens/)

    Returns:
        Mermaid diagram string
    """
    flows_path = Path(flows_dir)

    # Default screens dir to sibling directory
    if screens_dir is None:
        screens_path = flows_path.parent / "screens"
    else:
        screens_path = Path(screens_dir)

    # Collect all flow test files
    flow_files = sorted(flows_path.rglob("*.test.json"))

    if not flow_files:
        return "flowchart LR\n    NO_FLOWS[No flow tests found]"

    # Parse all flows and build node/edge data
    all_nodes: dict[str, str] = {}  # node_id -> display label
    node_metadata: dict[str, dict] = {}  # node_id -> {entry_screen, group}
    all_edges: list[tuple[str, str, str]] = []  # (from_id, to_id, flow_name)
    flow_subgraphs: dict[str, list[str]] = {}  # flow_name -> list of node_ids in order

    for flow_file in flow_files:
        try:
            with open(flow_file, 'r', encoding='utf-8') as f:
                flow_data = json.load(f)

            if flow_data.get("type") != "flow":
                continue

            metadata = flow_data.get("metadata", {})
            flow_name = metadata.get("name", flow_file.stem)
            steps = flow_data.get("steps", [])

            # Extract screen references from steps (skip inline actions)
            screen_refs = _extract_screen_references(steps)

            if not screen_refs:
                continue

            # Build nodes for this flow (screen level only, ignore case names)
            flow_nodes = []
            prev_screen = None
            for screen_ref in screen_refs:
                file_ref = screen_ref["file"]

                # Skip if same screen as previous (consecutive same-screen steps)
                if file_ref == prev_screen:
                    continue
                prev_screen = file_ref

                # Create node ID from screen name only (no case)
                node_id = _make_node_id(file_ref, None)

                # Get display label and metadata from screen test
                if node_id not in all_nodes:
                    screen_meta = _get_screen_metadata(file_ref, screens_path, flows_path)
                    all_nodes[node_id] = screen_meta["label"]
                    node_metadata[node_id] = {
                        "entry_screen": screen_meta["entry_screen"],
                        "groups": screen_meta["groups"],  # Now a list
                        "document": screen_meta["document"]
                    }

                flow_nodes.append(node_id)

            # Store flow nodes
            flow_subgraphs[flow_name] = flow_nodes

            # Build edges (consecutive screen transitions)
            for i in range(len(flow_nodes) - 1):
                from_node = flow_nodes[i]
                to_node = flow_nodes[i + 1]
                all_edges.append((from_node, to_node, flow_name))

        except Exception as e:
            print(f"  Warning: Error processing {flow_file}: {e}")
            continue

    # Generate Mermaid diagram
    return _build_mermaid_diagram(all_nodes, all_edges, flow_subgraphs, node_metadata)


def generate_grouped_mermaid_diagrams(
    flows_dir: Path,
    screens_dir: Path | None = None
) -> dict[str, str]:
    """
    Generate separate Mermaid diagrams for each group.

    Args:
        flows_dir: Directory containing flow test files
        screens_dir: Optional directory containing screen test files

    Returns:
        Dict of group_name -> mermaid_code
    """
    flows_path = Path(flows_dir)

    if screens_dir is None:
        screens_path = flows_path.parent / "screens"
    else:
        screens_path = Path(screens_dir)

    flow_files = sorted(flows_path.rglob("*.test.json"))

    if not flow_files:
        return {"All": "flowchart LR\n    NO_FLOWS[No flow tests found]"}

    # Collect all data
    all_nodes: dict[str, str] = {}
    node_metadata: dict[str, dict] = {}
    all_edges: list[tuple[str, str, str]] = []

    for flow_file in flow_files:
        try:
            with open(flow_file, 'r', encoding='utf-8') as f:
                flow_data = json.load(f)

            if flow_data.get("type") != "flow":
                continue

            metadata = flow_data.get("metadata", {})
            flow_name = metadata.get("name", flow_file.stem)
            steps = flow_data.get("steps", [])

            screen_refs = _extract_screen_references(steps)
            if not screen_refs:
                continue

            flow_nodes = []
            prev_screen = None
            for screen_ref in screen_refs:
                file_ref = screen_ref["file"]
                if file_ref == prev_screen:
                    continue
                prev_screen = file_ref

                node_id = _make_node_id(file_ref, None)
                if node_id not in all_nodes:
                    screen_meta = _get_screen_metadata(file_ref, screens_path, flows_path)
                    all_nodes[node_id] = screen_meta["label"]
                    node_metadata[node_id] = {
                        "entry_screen": screen_meta["entry_screen"],
                        "groups": screen_meta["groups"],  # Now a list
                        "document": screen_meta["document"]
                    }

                flow_nodes.append(node_id)

            for i in range(len(flow_nodes) - 1):
                from_node = flow_nodes[i]
                to_node = flow_nodes[i + 1]
                all_edges.append((from_node, to_node, flow_name))

        except Exception as e:
            print(f"  Warning: Error processing {flow_file}: {e}")
            continue

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
            for from_id, to_id, _ in all_edges:
                if from_id == entry_node and to_id in group_nodes:
                    relevant_entry_nodes.add(entry_node)
                    break

        # Get edges within this group or from entry nodes to this group
        group_edges = []
        for from_id, to_id, flow_name in all_edges:
            from_in_group = from_id in group_nodes or from_id in relevant_entry_nodes
            to_in_group = to_id in group_nodes
            if from_in_group and to_in_group:
                group_edges.append((from_id, to_id))

        # Build mermaid for this group
        lines = ["flowchart LR"]

        # Add entry nodes first
        if relevant_entry_nodes:
            lines.append("")
            lines.append("    %% Entry screens")
            for node_id in sorted(relevant_entry_nodes):
                label = all_nodes[node_id]
                safe_label = label.replace('"', "'").replace("\n", " ")
                lines.append(f'    {node_id}(["{safe_label}"]):::entryNode')
            lines.append("")
            lines.append("    classDef entryNode fill:#e8f5e9,stroke:#4caf50,stroke-width:3px")

        # Add group nodes
        lines.append("")
        lines.append(f"    %% {group_name}")
        for node_id in sorted(group_nodes):
            if node_id not in relevant_entry_nodes:
                label = all_nodes[node_id]
                safe_label = label.replace('"', "'").replace("\n", " ")
                lines.append(f'    {node_id}["{safe_label}"]')

        # Add edges
        if group_edges:
            lines.append("")
            lines.append("    %% Transitions")
            seen_edges = set()
            for from_id, to_id in group_edges:
                edge_key = (from_id, to_id)
                if edge_key not in seen_edges:
                    seen_edges.add(edge_key)
                    lines.append(f"    {from_id} --> {to_id}")

        # Add click events for nodes with document links
        click_lines = []
        all_group_node_ids = group_nodes | relevant_entry_nodes
        for node_id in sorted(all_group_node_ids):
            meta = node_metadata.get(node_id, {})
            document = meta.get("document")
            if document:
                label = all_nodes[node_id]
                safe_tooltip = label.replace('"', "'")
                click_lines.append(f'    click {node_id} "{document}" "{safe_tooltip}"')

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


def _make_node_id(file_ref: str, case_name: str | None) -> str:
    """Create a unique node ID from file reference and case name."""
    # Sanitize for Mermaid node IDs (alphanumeric and underscore only)
    base = file_ref.replace("/", "_").replace("-", "_").replace(".", "_")
    if case_name:
        case_part = case_name.replace("-", "_").replace(".", "_")
        return f"{base}_{case_part}"
    return base


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
            label = nodes[node_id]
            safe_label = label.replace('"', "'").replace("\n", " ")
            lines.append(f'    {node_id}(["{safe_label}"]):::entryNode')
        lines.append("")
        lines.append("    classDef entryNode fill:#e8f5e9,stroke:#4caf50,stroke-width:3px")

    # Define grouped nodes in subgraphs
    for group_name in sorted(grouped_nodes.keys()):
        group_node_ids = grouped_nodes[group_name]
        # Sanitize group name for subgraph ID (must be alphanumeric + underscore only)
        group_id = _sanitize_id(group_name)
        lines.append("")
        lines.append(f'    subgraph {group_id}["{group_name}"]')
        for node_id in sorted(group_node_ids):
            label = nodes[node_id]
            safe_label = label.replace('"', "'").replace("\n", " ")
            lines.append(f'        {node_id}["{safe_label}"]')
        lines.append("    end")

    # Define ungrouped nodes
    if ungrouped_nodes:
        lines.append("")
        lines.append("    %% Other screens")
        for node_id in sorted(ungrouped_nodes):
            label = nodes[node_id]
            safe_label = label.replace('"', "'").replace("\n", " ")
            lines.append(f'    {node_id}["{safe_label}"]')

    # Build unique edges (deduplicate same source->target pairs)
    unique_edges: dict[tuple[str, str], list[str]] = {}
    for from_id, to_id, flow_name in edges:
        key = (from_id, to_id)
        if key not in unique_edges:
            unique_edges[key] = []
        if flow_name not in unique_edges[key]:
            unique_edges[key].append(flow_name)

    # Separate entry screen edges (output first for LR layout positioning)
    entry_edges = []
    other_edges = []
    for (from_id, to_id), flow_names in sorted(unique_edges.items()):
        if from_id in entry_nodes:
            entry_edges.append((from_id, to_id))
        else:
            other_edges.append((from_id, to_id))

    # Add edges - entry screen edges first for left positioning in LR layout
    lines.append("")
    lines.append("    %% Transitions")
    for from_id, to_id in entry_edges:
        lines.append(f"    {from_id} --> {to_id}")
    for from_id, to_id in other_edges:
        lines.append(f"    {from_id} --> {to_id}")

    # Add click events for nodes with document links
    click_lines = []
    for node_id in nodes:
        meta = node_metadata.get(node_id, {})
        document = meta.get("document")
        if document:
            label = nodes[node_id]
            safe_tooltip = label.replace('"', "'")
            click_lines.append(f'    click {node_id} "{document}" "{safe_tooltip}"')

    if click_lines:
        lines.append("")
        lines.append("    %% Click events for document links")
        lines.extend(click_lines)

    return "\n".join(lines)


def generate_mermaid_html(
    flows_dir: Path,
    output_path: Path,
    title: str = "Flow Diagram",
    screens_dir: Path | None = None
) -> str:
    """
    Generate an HTML page with embedded Mermaid diagrams (one per group).

    Args:
        flows_dir: Directory containing flow test files
        output_path: Path to write HTML file
        title: Page title
        screens_dir: Optional directory containing screen test files

    Returns:
        The generated Mermaid diagram string (combined)
    """
    # Generate grouped diagrams
    grouped_diagrams = generate_grouped_mermaid_diagrams(flows_dir, screens_dir)

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
