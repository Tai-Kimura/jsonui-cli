"""Markdown generator for screen specification JSON files."""

from __future__ import annotations

import json

from pathlib import Path
from typing import Any


_PLATFORM_TOKEN_TO_LABEL = {
    "ios": "iOS", "swift": "iOS", "swiftui": "iOS", "uikit": "iOS",
    "android": "Android", "kotlin": "Android", "java": "Android",
    "compose": "Android", "xml": "Android",
    "web": "Web", "typescript": "Web", "javascript": "Web", "react": "Web",
}


def _cell(value) -> str:
    """A prose value inside a table row: its line breaks as `<br>`.

    A raw newline ends a Markdown table row, so a multi-line description —
    a texts-file Markdown one especially — split its row in two and pushed
    the rest of the text out of the table. Block-level prose is inserted
    as-is, where a Markdown text renders as written.
    """
    if value is None:
        return ""
    return str(value).replace("\r\n", "\n").replace("\n", "<br>")


def _labelled(label: str, value) -> list[str]:
    """`**Notes:** text`, or — for Markdown from a texts file — the label on
    its own line and the value as blocks below it.

    Inline, a Markdown value that opens with a heading or a list is glued to
    the label's paragraph, and `## Rule` renders as the literal text "## Rule".
    """
    if _is_markdown(value):
        return [f"**{label}:**", "", str(value).rstrip("\n")]
    return [f"**{label}:** {value}"]


def _list_continuation(text) -> str:
    """Text placed inside a `- ` list item: continuation lines indented so
    they stay in the item instead of starting a new block after the list."""
    return str(text).replace("\r\n", "\n").replace("\n", "\n  ")


def _is_markdown(value) -> bool:
    from ..prose import is_markdown
    return is_markdown(value)


def _components_table_md(components: list) -> list[str]:
    """The UI Components table: a row per component, children indented."""
    lines = ["| Component | ID | Platform | Description | Initial State | Notes |",
             "|---|---|---|---|---|---|"]

    def row(comp: dict, depth: int) -> None:
        indent = "&nbsp;&nbsp;" * depth + ("↳ " if depth else "")
        lines.append(
            f"| {indent}{comp.get('type', '-')} | `{comp.get('id', '-')}` | {_format_platform_md(comp.get('platform'))} "
            f"| {_cell(comp.get('description', '-'))} | {comp.get('initialState', '-')} | {_cell(comp.get('notes', '-') or '-')} |"
        )
        for child in comp.get("children", []) or []:
            if isinstance(child, dict):
                row(child, depth + 1)

    for comp in components:
        if isinstance(comp, dict):
            row(comp, 0)
    return lines


def _section_ref_md(ref) -> str:
    """A Collection section's cell / header / footer reference, as text."""
    if isinstance(ref, str):
        return f"`{ref}`" if ref else "-"
    if isinstance(ref, dict):
        name = ref.get("layoutFile") or ref.get("layout") or ref.get("id") or ""
        return f"`{name}`" if name else "-"
    return "-"


def _format_platform_md(value) -> str:
    """Format a platform filter (string or override dict) for markdown output."""
    if not value:
        return "-"
    if isinstance(value, str):
        tokens = [t.strip().lower() for t in value.split(",") if t.strip()]
        labels: list[str] = []
        seen = set()
        for t in tokens:
            label = _PLATFORM_TOKEN_TO_LABEL.get(t, t)
            if label not in seen:
                labels.append(label)
                seen.add(label)
        return ", ".join(labels) if labels else "-"
    if isinstance(value, dict):
        keys = [k for k in value.keys() if k in ("ios", "android", "web")]
        if not keys:
            return "-"
        return ", ".join(f"{k.capitalize()}*" for k in keys)
    return "-"


from .html_generator import _sub_spec_sections, _ui_variable_default, layout_node_marks


def generate_spec_markdown(spec_data: dict, layouts_dir: Path | None = None,
                           spec_dir: Path | None = None) -> str:
    """
    Generate Markdown documentation from screen specification JSON.

    Args:
        spec_data: Parsed specification JSON data
        layouts_dir: Path to shared layouts directory (for layoutFile import)

    Returns:
        Generated Markdown string
    """
    # Import Layout JSON if layoutFile is specified
    if layouts_dir and (spec_data.get("metadata") or {}).get("layoutFile"):
        from .layout_importer import import_layout_into_spec
        spec_data = import_layout_into_spec(spec_data, layouts_dir)

    lines: list[str] = []

    metadata = spec_data.get("metadata", {})
    structure = spec_data.get("structure", {})
    data_flow = spec_data.get("dataFlow", {})
    state_mgmt = spec_data.get("stateManagement", {})
    user_actions = spec_data.get("userActions", [])
    validation = spec_data.get("validation", {})
    transitions = spec_data.get("transitions", [])
    related_files = spec_data.get("relatedFiles", [])
    notes = spec_data.get("notes", [])

    # Title
    name = metadata.get("name", "Screen")
    display_name = metadata.get("displayName", name)
    lines.append(f"# {name} - {display_name}")
    lines.append("")

    # Overview
    lines.append("## Overview")
    lines.append("")
    lines.append(metadata.get("description", ""))
    lines.append("")

    # Metadata info
    if metadata.get("author") or metadata.get("createdAt") or metadata.get("updatedAt") or metadata.get("layoutFile"):
        lines.append("| | |")
        lines.append("|---|---|")
        if metadata.get("layoutFile"):
            lines.append(f"| Layout File | `{metadata['layoutFile']}` |")
        if metadata.get("author"):
            lines.append(f"| Author | {metadata['author']} |")
        if metadata.get("createdAt"):
            lines.append(f"| Created | {metadata['createdAt']} |")
        if metadata.get("updatedAt"):
            lines.append(f"| Updated | {metadata['updatedAt']} |")
        lines.append("")

    # Sub-Specs (for screen_parent_spec). The HTML side has carried this
    # index since parents existed; markdown had none at all, so a split
    # screen's markdown page named neither its parts nor where its behaviour
    # is declared.
    sub_specs = spec_data.get("subSpecs") or []
    if sub_specs:
        lines.append("## Sub Specifications")
        lines.append("")
        lines.append(
            "This screen is split across the sub-specs below. Its behaviour — "
            "data flow, state, user actions, validation — is declared in them "
            "and documented on their pages, not here. A parent spec may not "
            "declare those sections itself."
        )
        lines.append("")
        show_declares = spec_dir is not None
        if show_declares:
            lines.append("| Name | File | Declares | Description |")
            lines.append("|---|---|---|---|")
        else:
            lines.append("| Name | File | Description |")
            lines.append("|---|---|---|")
        for sub in sub_specs:
            cells = [sub.get("name", "-"), f"`{sub.get('file', '')}`"]
            if show_declares:
                cells.append(_sub_spec_sections(spec_dir, sub.get("file", "")) or "-")
            cells.append(_cell(sub.get("description", "-")))
            lines.append("| " + " | ".join(cells) + " |")
        lines.append("")

    # Screen Structure
    lines.append("## Screen Structure")
    lines.append("")

    # UI Components table
    lines.append("### UI Components")
    lines.append("")
    components = structure.get("components", [])
    if components:
        lines.extend(_components_table_md(components))
        lines.append("")

    # Decorative elements
    decorative = structure.get("decorativeElements") or []
    if decorative:
        lines.append("### Decorative Elements")
        lines.append("")
        lines.append("| ID | Purpose | Parent | Components |")
        lines.append("|---|---|---|---|")
        for elem in decorative:
            comp_ids = ", ".join(
                f"`{c.get('id', '')}`" for c in elem.get("components", []) or []
            )
            lines.append(
                f"| `{elem.get('id', '-')}` | {_cell(elem.get('purpose', '-') or '-')} "
                f"| {elem.get('parentId', '-') or '-'} | {comp_ids or '-'} |"
            )
        lines.append("")
        # Each element's components, as the UI Components table (the HTML
        # page draws them the same way; until jsonui-cli 1.9.6 neither did).
        for elem in decorative:
            elem_components = [c for c in (elem.get("components") or []) if isinstance(c, dict)]
            if elem_components:
                lines.append(f"#### Components — {elem.get('id', '-')}")
                lines.append("")
                lines.extend(_components_table_md(elem_components))
                lines.append("")

    # Wrapper views
    wrappers = structure.get("wrapperViews") or []
    if wrappers:
        lines.append("### Wrapper Views")
        lines.append("")
        lines.append("| ID | Wraps | Purpose | Style |")
        lines.append("|---|---|---|---|")
        for wv in wrappers:
            style = wv.get("style") or {}
            style_str = ", ".join(f"{k}={v}" for k, v in style.items()) or "-"
            lines.append(
                f"| `{wv.get('id', '-')}` | `{wv.get('wraps', '-')}` "
                f"| {_cell(wv.get('purpose', '-') or '-')} | {style_str} |"
            )
        lines.append("")

    # Layout Structure
    lines.append("### Layout Structure")
    lines.append("")
    layout = structure.get("layout", {})
    if layout:
        lines.append("```")
        lines.extend(_render_layout_tree(layout, 0))
        lines.append("```")
        lines.append("")

    # Structure notes
    if structure.get("notes"):
        lines.extend(_labelled("Notes", structure['notes']))
        lines.append("")

    # Collection Structure(s) — structure.collection + structure.collections[]
    _all_collections = [
        c for c in [structure.get("collection"), *(structure.get("collections") or [])]
        if isinstance(c, dict)
    ]
    for collection in _all_collections:
        lines.append("### Collection Structure")
        lines.append("")
        lines.append(f"**Collection ID:** `{collection.get('id', '-')}`")
        lines.append("")
        # What the HTML page draws for a Collection, in the same order.
        if collection.get("description"):
            lines.append(str(collection["description"]))
            lines.append("")
        if collection.get("cellIdProperty"):
            lines.append(f"**Cell ID Property:** `{collection['cellIdProperty']}`")
            lines.append("")
        if collection.get("insets") not in (None, ""):
            lines.append(f"**Insets:** `{collection['insets']}`")
            lines.append("")
        cell_classes = [c for c in (collection.get("cellClasses") or []) if isinstance(c, str)]
        if cell_classes:
            lines.append("**Cell Classes:** " + ", ".join(f"`{c}`" for c in cell_classes))
            lines.append("")

        if collection.get("header"):
            lines.append("#### Header Layout")
            lines.append("")
            lines.append("```")
            lines.extend(_render_layout_tree(collection["header"], 0))
            lines.append("```")
            lines.append("")

        if collection.get("cell"):
            lines.append("#### Cell Layout")
            lines.append("")
            lines.append("```")
            lines.extend(_render_layout_tree(collection["cell"], 0))
            lines.append("```")
            lines.append("")

        if collection.get("footer"):
            lines.append("#### Footer Layout")
            lines.append("")
            lines.append("```")
            lines.extend(_render_layout_tree(collection["footer"], 0))
            lines.append("```")
            lines.append("")

        section_rows = [sec for sec in (collection.get("sections") or []) if isinstance(sec, dict)]
        if section_rows:
            lines.append("#### Sections")
            lines.append("")
            lines.append("| # | Index | Cell | Header | Footer | Columns | Description | Notes |")
            lines.append("|---|---|---|---|---|---|---|---|")
            for i, sec in enumerate(section_rows, start=1):
                refs = [_section_ref_md(sec.get(k)) for k in ("cell", "header", "footer")]
                index = sec["index"] if sec.get("index") is not None else "-"
                columns = sec["columns"] if sec.get("columns") is not None else "-"
                lines.append(f"| {i} | {index} | {refs[0]} | {refs[1]} | {refs[2]} | {columns} "
                             f"| {_cell(sec.get('description') or '-')} | {_cell(sec.get('notes') or '-')} |")
            lines.append("")

        if collection.get("notes"):
            lines.extend(_labelled("Notes", collection["notes"]))
            lines.append("")

    # TabView Structure
    tab_view = structure.get("tabView")
    if tab_view:
        lines.append("### TabView Structure")
        lines.append("")
        lines.append(f"**TabView ID:** `{tab_view.get('id', '-')}`")
        lines.append("")
        lines.append("| Tab | Title | Layout File | View | Icon | Selected Icon |")
        lines.append("|---|---|---|---|---|---|")
        for i, tab in enumerate(tab_view.get("tabs", []), 1):
            title = tab.get("title", "-")
            layout_file = tab.get("layoutFile", "-")
            lines.append(f"| {i} | {title} | `{layout_file}` | `{tab.get('view') or '-'}` "
                         f"| `{tab.get('icon') or '-'}` | `{tab.get('selectedIcon') or '-'}` |")
        lines.append("")

    # Embeds (the HTML page's table; until jsonui-cli 1.9.6 neither page read them)
    embeds = [e for e in (structure.get("embeds") or []) if isinstance(e, dict)]
    if embeds:
        lines.append("### Embeds")
        lines.append("")
        lines.append("| Region | Screen | Navigation | Params | Events |")
        lines.append("|---|---|---|---|---|")
        for emb in embeds:
            params = ", ".join(f"{k}={v}" for k, v in (emb.get("params") or {}).items()) or "-"
            events = ", ".join(f"{k}={v}" for k, v in (emb.get("events") or {}).items()) or "-"
            lines.append(f"| `{emb.get('regionId', '-')}` | `{emb.get('screen', '-')}` "
                         f"| {emb.get('navigationMode') or '-'} | {params} | {events} |")
        lines.append("")

    # Custom components (the HTML page lists them; the Markdown did not)
    custom_components = [c for c in (structure.get("customComponents") or []) if isinstance(c, dict)]
    if custom_components:
        lines.append("### Custom Components")
        lines.append("")
        lines.append("| Component | Specification | Description |")
        lines.append("|---|---|---|")
        for cc in custom_components:
            spec_file = cc.get("specFile") or "-"
            lines.append(f"| {cc.get('name', '-')} | `{spec_file}` | {_cell(cc.get('description', '-') or '-')} |")
        lines.append("")

    # Data Flow
    if data_flow:
        lines.append("## Data Flow")
        lines.append("")

        # Mermaid diagram
        diagram = data_flow.get("diagram")
        if diagram:
            lines.append("```mermaid")
            lines.append(diagram)
            lines.append("```")
            lines.append("")

        # ViewModel
        view_model = data_flow.get("viewModel") or {}
        if view_model:
            lines.append("### ViewModel")
            lines.append("")
            if view_model.get("description"):
                lines.append(view_model["description"])
                lines.append("")

            vm_methods = view_model.get("methods", [])
            if vm_methods:
                lines.append("#### Methods")
                lines.append("")
                lines.append("| Signature | Platforms | Description |")
                lines.append("|---|---|---|")
                for m in vm_methods:
                    sig = _format_vm_method_md(m)
                    plats = _format_member_platforms_md(m)
                    desc = _cell(m.get("description", "-")) if isinstance(m, dict) else "-"
                    lines.append(f"| {sig} | {plats} | {desc} |")
                lines.append("")

            vm_vars = view_model.get("vars", [])
            if vm_vars:
                lines.append("#### Vars")
                lines.append("")
                lines.append("| Declaration | Flags | Platforms | Description |")
                lines.append("|---|---|---|---|")
                for v in vm_vars:
                    decl = _format_vm_var_md(v)
                    flags = _format_vm_var_flags_md(v)
                    plats = _format_member_platforms_md(v)
                    lines.append(
                        f"| {decl} | {flags} | {plats} | {_cell(v.get('description', '-'))} |"
                    )
                lines.append("")

        # Repositories
        repos = data_flow.get("repositories", [])
        if repos:
            lines.append("### Repositories")
            lines.append("")
            for repo in repos:
                repo_name = repo.get("name", "-")
                lines.append(f"#### {repo_name}")
                lines.append("")
                if repo.get("description"):
                    lines.append(str(repo["description"]))
                    lines.append("")
                methods = repo.get("methods", [])
                if methods:
                    for method in methods:
                        lines.append(f"- {_format_method_md(method)}")
                    lines.append("")

        # UseCases
        use_cases = data_flow.get("useCases", [])
        if use_cases:
            lines.append("### UseCases")
            lines.append("")
            for uc in use_cases:
                uc_name = uc.get("name", "-")
                lines.append(f"#### {uc_name}")
                lines.append("")
                if uc.get("description"):
                    lines.append(uc["description"])
                    lines.append("")
                dep_repos = uc.get("repositories", [])
                if dep_repos:
                    lines.append(f"**Dependencies:** {', '.join(dep_repos)}")
                    lines.append("")
                methods = uc.get("methods", [])
                if methods:
                    for method in methods:
                        lines.append(f"- {_format_method_md(method)}")
                    lines.append("")

        # API Endpoints
        endpoints = data_flow.get("apiEndpoints", [])
        if endpoints:
            lines.append("### API Endpoints")
            lines.append("")
            for endpoint in endpoints:
                method = endpoint.get("method", "GET")
                path = endpoint.get("path", "-")
                lines.append(f"#### `{method}` {path}")
                lines.append("")

                request = endpoint.get("request")
                if request:
                    lines.append("**Request:**")
                    lines.append("```json")
                    lines.append(_format_json_schema(request))
                    lines.append("```")
                    lines.append("")

                response = endpoint.get("response")
                if response:
                    lines.append("**Response:**")
                    lines.append("```json")
                    lines.append(_format_json_schema(response))
                    lines.append("```")
                    lines.append("")

                if endpoint.get("notes"):
                    lines.extend(_labelled("Notes", endpoint['notes']))
                    lines.append("")

        if data_flow.get("notes"):
            lines.extend(_labelled("Notes", data_flow['notes']))
            lines.append("")

    # State Management
    if state_mgmt:
        lines.append("## State Management")
        lines.append("")

        # States
        states = state_mgmt.get("states", [])
        for state in states:
            state_name = state.get("name", "State")
            lines.append(f"### {state_name}")
            lines.append("")
            lines.append("| Value | Description | Visible Elements |")
            lines.append("|---|---|---|")
            for val in state.get("values", []):
                v = val.get("value", "-")
                desc = _cell(val.get("description", "-"))
                visible = ", ".join(f"`{e}`" for e in val.get("visibleElements", [])) or "-"
                lines.append(f"| `.{v}` | {desc} | {visible} |")
            lines.append("")
            if state.get("notes"):
                lines.extend(_labelled("Notes", state['notes']))
                lines.append("")

        # UI Variables
        variables = state_mgmt.get("uiVariables", [])
        if variables:
            lines.append("### UI Data Variables")
            lines.append("")
            lines.append("| Variable Name | Type | Default | Description | Notes |")
            lines.append("|---|---|---|---|---|")
            for var in variables:
                var_name = var.get("name", "-")
                var_type = var.get("type", "-")
                desc = _cell(var.get("description", "-"))
                var_notes = _cell(var.get("notes", "-") or "-")
                lines.append(f"| `{var_name}` | {var_type} | `{_ui_variable_default(var)}` | {desc} | {var_notes} |")
            lines.append("")

        # View-local Event Handlers (ViewModel public API is under dataFlow.viewModel)
        handlers = state_mgmt.get("eventHandlers", [])
        if handlers:
            lines.append("### View-local Event Handlers")
            lines.append("")
            lines.append("_Handlers kept inside the View layer. ViewModel public API lives under `dataFlow.viewModel`._")
            lines.append("")
            lines.append("| Handler | Description | Notes |")
            lines.append("|---|---|---|")
            for handler in handlers:
                h_name = handler.get("name", "-")
                desc = _cell(handler.get("description", "-"))
                h_notes = _cell(handler.get("notes", "-") or "-")
                lines.append(f"| `{h_name}` | {desc} | {h_notes} |")
            lines.append("")

        # Display Logic
        logic_rules = state_mgmt.get("displayLogic", [])
        if logic_rules:
            lines.append("### Display Logic")
            lines.append("")
            lines.append("```")
            for rule in logic_rules:
                condition = rule.get("condition", "-")
                lines.append(f"{condition}:")
                for effect in rule.get("effects", []):
                    element = effect.get("element", "-")
                    state = effect.get("state", "-")
                    var_name = effect.get("variableName")
                    suffix = f" [variable: {var_name}]" if var_name else ""
                    lines.append(f"  - {element}: {state}{suffix}")
                if rule.get("notes"):
                    lines.append(f"  Notes: {rule['notes']}")
                lines.append("")
            lines.append("```")
            lines.append("")

        if state_mgmt.get("notes"):
            lines.extend(_labelled("Notes", state_mgmt['notes']))
            lines.append("")

    # User Actions
    if user_actions:
        lines.append("## User Actions")
        lines.append("")
        lines.append("| Action | Processing | Destination | Notes |")
        lines.append("|---|---|---|---|")
        for action in user_actions:
            act = action.get("action", "-")
            processing = _cell(action.get("processing", "-"))
            dest = action.get("destination", "-") or "-"
            act_notes = _cell(action.get("notes", "-") or "-")
            lines.append(f"| {act} | {processing} | {dest} | {act_notes} |")
        lines.append("")

    # Validation
    if validation:
        lines.append("## Validation")
        lines.append("")

        client_side = validation.get("clientSide", [])
        if client_side:
            lines.append("### Client-side")
            lines.append("")
            lines.append("| Field | Rule | Notes |")
            lines.append("|---|---|---|")
            for v in client_side:
                field = v.get("field", "-")
                rule = _cell(v.get("rule", "-"))
                v_notes = _cell(v.get("notes", "-") or "-")
                lines.append(f"| {field} | {rule} | {v_notes} |")
            lines.append("")

        server_side = validation.get("serverSide", [])
        if server_side:
            lines.append("### Server-side")
            lines.append("")
            lines.append("| Error Condition | Handling | Notes |")
            lines.append("|---|---|---|")
            for v in server_side:
                condition = v.get("condition", "-")
                handling = _cell(v.get("handling", "-"))
                v_notes = _cell(v.get("notes", "-") or "-")
                lines.append(f"| {condition} | {handling} | {v_notes} |")
            lines.append("")

        if validation.get("notes"):
            lines.extend(_labelled("Notes", validation['notes']))
            lines.append("")

    # Branch Contracts (opt-in decision tables)
    branch_contracts = spec_data.get("branchContracts") or {}
    if branch_contracts:
        import json as _json

        def _pairs(mapping: dict) -> str:
            return "<br>".join(
                f"`{k}` = `{_json.dumps(v, ensure_ascii=False)}`"
                for k, v in mapping.items()
            )

        bc_methods = branch_contracts.get("methods") or {}
        declared = sum(
            1
            for c in bc_methods.values() if isinstance(c, dict)
            for b in (c.get("branches") or [])
            if isinstance(b, dict) and "note" not in b
        )
        notes_only = sum(
            1
            for c in bc_methods.values() if isinstance(c, dict)
            for b in (c.get("branches") or [])
            if isinstance(b, dict) and "note" in b
        )
        platform_scoped = sum(
            1
            for c in bc_methods.values() if isinstance(c, dict)
            for b in (c.get("branches") or [])
            if isinstance(b, dict) and "note" not in b and "platforms" in b
        )
        lines.append("## Branch Contracts")
        lines.append("")
        summary = (
            f"{len(bc_methods)} method(s) — {declared} declared branch(es), "
            f"{notes_only} note-only branch(es) outside the machine-checkable contract."
        )
        if platform_scoped:
            summary += (
                f" {platform_scoped} branch(es) are scoped to specific platforms."
            )
        lines.append(summary)
        lines.append("")

        bc_conditions = branch_contracts.get("conditions") or {}
        if isinstance(bc_conditions, dict) and bc_conditions:
            lines.append("### Named Conditions")
            lines.append("")
            lines.append("| Name | Meaning | Witness (true) | Witness (false) |")
            lines.append("|---|---|---|---|")
            for cname, cond in bc_conditions.items():
                cond = cond if isinstance(cond, dict) else {}
                wt = cond.get("witness_true")
                wf = cond.get("witness_false")
                lines.append(
                    f"| `{cname}` | {_cell(cond.get('meaning', '-') or '-')} | "
                    f"{_pairs(wt) if isinstance(wt, dict) else '-'} | "
                    f"{_pairs(wf) if isinstance(wf, dict) else '-'} |"
                )
            lines.append("")

        for method_name, contract in bc_methods.items():
            if not isinstance(contract, dict):
                continue
            lines.append(f"### `{method_name}`")
            lines.append("")
            baseline = contract.get("baseline")
            if isinstance(baseline, dict) and baseline:
                lines.append(f"**Baseline:** {_pairs(baseline)}")
                lines.append("")
            branches = contract.get("branches") or []
            scoped = any(
                isinstance(b, dict) and "note" not in b and "platforms" in b
                for b in branches
            )
            if scoped:
                lines.append("| # | When | Then | Platforms | Notes |")
                lines.append("|---|---|---|---|---|")
            else:
                lines.append("| # | When | Then | Notes |")
                lines.append("|---|---|---|---|")
            for i, branch in enumerate(branches, start=1):
                if not isinstance(branch, dict):
                    continue
                if "note" in branch:
                    empty = " | |" if scoped else " |"
                    lines.append(
                        f"| {i} | *note (not machine-checked): "
                        f"{_cell(branch.get('note', '') or '')}* |{empty} |"
                    )
                    continue
                when = branch.get("when")
                then = branch.get("then")
                platform_cell = ""
                if scoped:
                    raw = branch.get("platforms")
                    platform_cell = (
                        ", ".join(str(p) for p in raw)
                        if isinstance(raw, list) and raw
                        else "all"
                    ) + " | "
                lines.append(
                    f"| {i} | {_pairs(when) if isinstance(when, dict) else '-'} | "
                    f"{_pairs(then) if isinstance(then, dict) else '-'} | "
                    f"{platform_cell}"
                    f"{_cell(branch.get('notes', '-') or '-')} |"
                )
            lines.append("")

        if branch_contracts.get("notes"):
            lines.extend(_labelled("Notes", branch_contracts['notes']))
            lines.append("")

    # Transitions
    if transitions:
        lines.append("## Transitions")
        lines.append("")
        lines.append("| Condition | Destination | Notes |")
        lines.append("|---|---|---|")
        for trans in transitions:
            condition = _cell(trans.get("condition", "-"))
            dest = trans.get("destination", "-")
            t_notes = _cell(trans.get("notes", "-") or "-")
            lines.append(f"| {condition} | {dest} | {t_notes} |")
        lines.append("")

    # Related Files
    if related_files:
        lines.append("## Related Files")
        lines.append("")
        lines.append("| Type | File Path | Notes |")
        lines.append("|---|---|---|")
        for f in related_files:
            f_type = f.get("type", "-")
            path = f.get("path", "-")
            f_notes = _cell(f.get("notes", "-") or "-")
            lines.append(f"| {f_type} | `{path}` | {f_notes} |")
        lines.append("")

    # Notes
    if notes:
        lines.append("## Notes")
        lines.append("")
        for note in notes:
            # Continuation lines indented, so a multi-paragraph note stays
            # inside its list item instead of ending the list.
            lines.append("- " + str(note).replace("\n", "\n  "))
        lines.append("")

    return "\n".join(lines)


def _render_layout_tree(layout: dict, depth: int) -> list[str]:
    """Render layout structure as tree lines, every level (as the HTML page's
    tree; until jsonui-cli 1.9.6 the Markdown stopped at the second level)."""
    lines = [("│   " * depth) + str(layout.get("root", "root")) + layout_node_marks(layout)]

    def render(children: list, prefix: str) -> None:
        for i, child in enumerate(children):
            is_last = i == len(children) - 1
            branch = "└── " if is_last else "├── "
            if isinstance(child, str):
                lines.append(f"{prefix}{branch}{child}")
            elif isinstance(child, dict):
                lines.append(f"{prefix}{branch}{child.get('id', '?')}{layout_node_marks(child)}")
                nested = child.get("children") or []
                if nested:
                    render(nested, prefix + ("    " if is_last else "│   "))

    render(layout.get("children", []) or [], "│   " * depth)
    return lines


def _format_method_md(method) -> str:
    """Format a method (string or dict) as Markdown."""
    if isinstance(method, dict):
        method_name = method.get("name", "")
        params = method.get("params")
        if isinstance(params, list):
            params_str = ", ".join(
                f"{p.get('name', '?')}: {p.get('type', '?')}"
                for p in params if isinstance(p, dict)
            )
        else:
            params_str = str(params) if params else ""
        return_type = method.get("returnType", "")
        is_async = method.get("isAsync", True)
        async_prefix = "async " if is_async else ""
        result = f"`{async_prefix}{method_name}({params_str})`"
        if return_type:
            result += f" → `{return_type}`"
        if method.get("description"):
            desc = method["description"]
            if _is_markdown(desc):
                # Its own paragraph inside the item: a Markdown value may
                # open with a list or a heading, which glued after " — "
                # would be literal text.
                result += " —\n\n  " + _list_continuation(str(desc).rstrip("\n"))
            else:
                result += f" — {_list_continuation(desc)}"
        return result
    else:
        return f"`{method}`"


def _format_vm_method_md(method) -> str:
    """Markdown signature for a ``dataFlow.viewModel.methods`` entry.

    ViewModel methods default to ``isAsync: false`` (sync). Repository /
    UseCase methods still default to async via ``_format_method_md``.
    """
    if isinstance(method, str):
        return f"`{method}()`"
    if not isinstance(method, dict):
        return "`-`"
    name = method.get("name", "-")
    params = method.get("params")
    if isinstance(params, list):
        params_str = ", ".join(
            f"{p.get('name', '?')}: {p.get('type', '?')}"
            for p in params if isinstance(p, dict)
        )
    else:
        params_str = str(params) if params else ""
    return_type = method.get("returnType", "")
    is_async = bool(method.get("isAsync", False))
    async_prefix = "async " if is_async else ""
    sig = f"`{async_prefix}{name}({params_str})`"
    if return_type:
        sig += f" → `{return_type}`"
    return sig


def _format_vm_var_md(var: dict) -> str:
    name = var.get("name", "-")
    raw_type = var.get("type", "-")
    if var.get("optional"):
        if "->" in raw_type and not raw_type.endswith("?"):
            raw_type = f"({raw_type})?"
        elif not raw_type.endswith("?"):
            raw_type = f"{raw_type}?"
    keyword = "let" if var.get("readOnly") and not var.get("observable", True) else "var"
    return f"`{keyword} {name}: {raw_type}`"


def _format_vm_var_flags_md(var: dict) -> str:
    flags = []
    if var.get("observable", True):
        flags.append("observable")
    if var.get("optional"):
        flags.append("optional")
    if var.get("readOnly"):
        flags.append("readOnly")
    return ", ".join(flags) if flags else "—"


def _format_member_platforms_md(member) -> str:
    if not isinstance(member, dict):
        return "—"
    if "platforms" not in member:
        return "all"
    raw = member.get("platforms")
    if not isinstance(raw, list):
        return "invalid"
    if not raw:
        return "— (none)"
    return ", ".join(f"`{p}`" for p in raw)


def _format_json_schema(schema: dict, indent: int = 2) -> str:
    """Format JSON schema with type comments.

    A non-object reaches here only from a spec the validator should have
    rejected, but generation is reachable without validating. It used to
    raise `AttributeError: 'str' object has no attribute 'items'`, which
    names neither the field nor the file — the reporting lane rebuilt the
    traceback by hand to find which of the spec's many strings it was.
    Rendered instead, matching what the HTML generator already does with
    the same input, so the two generators agree and the diagnosis stays
    where it belongs (the validator, which now names the path).
    """
    if not isinstance(schema, dict):
        return json.dumps(schema, ensure_ascii=False)

    lines = []
    lines.append("{")

    items = list(schema.items())
    for i, (key, value) in enumerate(items):
        comma = "," if i < len(items) - 1 else ""

        if isinstance(value, dict):
            lines.append(f'  "{key}": {{')
            nested_items = list(value.items())
            for j, (nk, nv) in enumerate(nested_items):
                ncomma = "," if j < len(nested_items) - 1 else ""
                lines.append(f'    "{nk}": "{nv}"{ncomma}')
            lines.append(f"  }}{comma}")
        else:
            lines.append(f'  "{key}": "{value}"{comma}')

    lines.append("}")
    return "\n".join(lines)
