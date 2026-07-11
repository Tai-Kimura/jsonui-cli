"""Markdown generator for screen specification JSON files."""

from __future__ import annotations

from pathlib import Path
from typing import Any


_PLATFORM_TOKEN_TO_LABEL = {
    "ios": "iOS", "swift": "iOS", "swiftui": "iOS", "uikit": "iOS",
    "android": "Android", "kotlin": "Android", "java": "Android",
    "compose": "Android", "xml": "Android",
    "web": "Web", "typescript": "Web", "javascript": "Web", "react": "Web",
}


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


def generate_spec_markdown(spec_data: dict, layouts_dir: Path | None = None) -> str:
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
    if metadata.get("author") or metadata.get("createdAt") or metadata.get("updatedAt"):
        lines.append("| | |")
        lines.append("|---|---|")
        if metadata.get("author"):
            lines.append(f"| Author | {metadata['author']} |")
        if metadata.get("createdAt"):
            lines.append(f"| Created | {metadata['createdAt']} |")
        if metadata.get("updatedAt"):
            lines.append(f"| Updated | {metadata['updatedAt']} |")
        lines.append("")

    # Screen Structure
    lines.append("## Screen Structure")
    lines.append("")

    # UI Components table
    lines.append("### UI Components")
    lines.append("")
    components = structure.get("components", [])
    if components:
        lines.append("| Component | ID | Platform | Description | Initial State | Notes |")
        lines.append("|---|---|---|---|---|---|")

        def _render_component_row(comp: dict, depth: int = 0) -> None:
            comp_type = comp.get("type", "-")
            comp_id = comp.get("id", "-")
            platform = _format_platform_md(comp.get("platform"))
            desc = comp.get("description", "-")
            initial = comp.get("initialState", "-")
            comp_notes = comp.get("notes", "-") or "-"
            indent = "&nbsp;&nbsp;" * depth + ("↳ " if depth else "")
            lines.append(
                f"| {indent}{comp_type} | `{comp_id}` | {platform} | {desc} | {initial} | {comp_notes} |"
            )
            for child in comp.get("children", []) or []:
                if isinstance(child, dict):
                    _render_component_row(child, depth + 1)

        for comp in components:
            _render_component_row(comp)
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
                f"| `{elem.get('id', '-')}` | {elem.get('purpose', '-') or '-'} "
                f"| {elem.get('parentId', '-') or '-'} | {comp_ids or '-'} |"
            )
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
                f"| {wv.get('purpose', '-') or '-'} | {style_str} |"
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
        lines.append(f"**Notes:** {structure['notes']}")
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

    # TabView Structure
    tab_view = structure.get("tabView")
    if tab_view:
        lines.append("### TabView Structure")
        lines.append("")
        lines.append(f"**TabView ID:** `{tab_view.get('id', '-')}`")
        lines.append("")
        lines.append("| Tab | Title | Layout File |")
        lines.append("|---|---|---|")
        for i, tab in enumerate(tab_view.get("tabs", []), 1):
            title = tab.get("title", "-")
            layout_file = tab.get("layoutFile", "-")
            lines.append(f"| {i} | {title} | `{layout_file}` |")
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
                    desc = m.get("description", "-") if isinstance(m, dict) else "-"
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
                        f"| {decl} | {flags} | {plats} | {v.get('description', '-')} |"
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
                    lines.append(f"**Notes:** {endpoint['notes']}")
                    lines.append("")

        if data_flow.get("notes"):
            lines.append(f"**Notes:** {data_flow['notes']}")
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
                desc = val.get("description", "-")
                visible = ", ".join(f"`{e}`" for e in val.get("visibleElements", [])) or "-"
                lines.append(f"| `.{v}` | {desc} | {visible} |")
            lines.append("")
            if state.get("notes"):
                lines.append(f"**Notes:** {state['notes']}")
                lines.append("")

        # UI Variables
        variables = state_mgmt.get("uiVariables", [])
        if variables:
            lines.append("### UI Data Variables")
            lines.append("")
            lines.append("| Variable Name | Type | Description | Notes |")
            lines.append("|---|---|---|---|")
            for var in variables:
                var_name = var.get("name", "-")
                var_type = var.get("type", "-")
                desc = var.get("description", "-")
                var_notes = var.get("notes", "-") or "-"
                lines.append(f"| `{var_name}` | {var_type} | {desc} | {var_notes} |")
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
                desc = handler.get("description", "-")
                h_notes = handler.get("notes", "-") or "-"
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
                lines.append("")
            lines.append("```")
            lines.append("")

        if state_mgmt.get("notes"):
            lines.append(f"**Notes:** {state_mgmt['notes']}")
            lines.append("")

    # User Actions
    if user_actions:
        lines.append("## User Actions")
        lines.append("")
        lines.append("| Action | Processing | Destination | Notes |")
        lines.append("|---|---|---|---|")
        for action in user_actions:
            act = action.get("action", "-")
            processing = action.get("processing", "-")
            dest = action.get("destination", "-") or "-"
            act_notes = action.get("notes", "-") or "-"
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
                rule = v.get("rule", "-")
                v_notes = v.get("notes", "-") or "-"
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
                handling = v.get("handling", "-")
                v_notes = v.get("notes", "-") or "-"
                lines.append(f"| {condition} | {handling} | {v_notes} |")
            lines.append("")

        if validation.get("notes"):
            lines.append(f"**Notes:** {validation['notes']}")
            lines.append("")

    # Transitions
    if transitions:
        lines.append("## Transitions")
        lines.append("")
        lines.append("| Condition | Destination | Notes |")
        lines.append("|---|---|---|")
        for trans in transitions:
            condition = trans.get("condition", "-")
            dest = trans.get("destination", "-")
            t_notes = trans.get("notes", "-") or "-"
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
            f_notes = f.get("notes", "-") or "-"
            lines.append(f"| {f_type} | `{path}` | {f_notes} |")
        lines.append("")

    # Notes
    if notes:
        lines.append("## Notes")
        lines.append("")
        for note in notes:
            lines.append(f"- {note}")
        lines.append("")

    return "\n".join(lines)


def _render_layout_tree(layout: dict, depth: int) -> list[str]:
    """Render layout structure as tree lines."""
    lines = []
    root = layout.get("root", "root")
    children = layout.get("children", [])

    indent = "│   " * depth
    lines.append(f"{indent}{root}")

    for i, child in enumerate(children):
        is_last = i == len(children) - 1
        prefix = "└── " if is_last else "├── "
        child_indent = "│   " * depth + prefix

        if isinstance(child, str):
            lines.append(f"{child_indent}{child}")
        elif isinstance(child, dict):
            child_id = child.get("id", "?")
            child_children = child.get("children", [])
            lines.append(f"{child_indent}{child_id}")

            # Render nested children
            if child_children:
                nested_indent = "│   " * (depth + 1) if not is_last else "    " * (depth + 1)
                for j, nested in enumerate(child_children):
                    nested_is_last = j == len(child_children) - 1
                    nested_prefix = "└── " if nested_is_last else "├── "

                    if isinstance(nested, str):
                        lines.append(f"{nested_indent}{nested_prefix}{nested}")
                    elif isinstance(nested, dict):
                        lines.append(f"{nested_indent}{nested_prefix}{nested.get('id', '?')}")

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
            result += f" — {method['description']}"
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
    """Format JSON schema with type comments."""
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
