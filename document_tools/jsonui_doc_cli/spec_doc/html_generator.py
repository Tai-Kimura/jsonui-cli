"""HTML generator for screen specification JSON files."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any


#: Top-level keys that say nothing about what a sub-spec CONTRIBUTES — they are
#: bookkeeping every spec carries.
_SUB_SPEC_BOOKKEEPING = frozenset({
    "$schema", "type", "version", "metadata", "subSpecs", "notes", "relatedFiles",
})


def _sub_spec_sections(spec_dir: "Path | None", sub_file: str) -> str:
    """The sections a sub-spec declares, for the parent index's `Declares` cell.

    The index has to answer "which page is validation on?". Without this the
    parent lists names and files and leaves the reader to open all of them —
    an index with no table of contents.

    Read from the sub-spec itself rather than from the parent's `subSpecs`
    entry, because the entry carries only name/file/description; the parent is
    forbidden from declaring the sections, so it cannot list them either.

    Degrades to "" when the directory is not known or the file cannot be read:
    a wrong list is worse than none here, since the whole point is telling a
    reader where to look.
    """
    if spec_dir is None or not sub_file:
        return ""
    try:
        path = Path(spec_dir) / sub_file
        if not path.is_file():
            path = Path(spec_dir) / Path(sub_file).name
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    if not isinstance(data, dict):
        return ""
    return ", ".join(sorted(k for k in data if k not in _SUB_SPEC_BOOKKEEPING))


def generate_spec_html(
    spec_data: dict,
    title: str | None = None,
    all_tests_nav: dict | None = None,
    current_path: str | None = None,
    layouts_dir: Path | None = None,
    spec_dir: Path | None = None,
    unit_href: str | None = None,
) -> str:
    """
    Generate HTML documentation from screen specification JSON.

    Args:
        spec_data: Parsed specification JSON data
        title: Optional custom title
        all_tests_nav: Navigation data for sidebar (if provided, adds sidebar)
        current_path: Current page's relative path (for highlighting in sidebar)
        layouts_dir: Path to shared layouts directory (for layoutFile import)

    Returns:
        Generated HTML string
    """
    # Import Layout JSON(s) — both metadata.layoutFile (screen-level) and
    # structure.collection.* layout refs (cellClasses, cell.layoutFile, etc.)
    # are inlined so the report shows the full component tree for every cell.
    if layouts_dir:
        from .layout_importer import import_layout_into_spec
        spec_data = import_layout_into_spec(spec_data, layouts_dir)

    # Load color token map from {layouts_dir}/Resources/colors.json if present,
    # so the Components table can render real swatches next to tokens.
    colors_map = _load_colors_map(layouts_dir)

    metadata = spec_data.get("metadata", {})
    structure = spec_data.get("structure", {})
    data_flow = spec_data.get("dataFlow", {})
    state_mgmt = spec_data.get("stateManagement", {})
    user_actions = spec_data.get("userActions", [])
    validation = spec_data.get("validation", {})
    transitions = spec_data.get("transitions", [])
    related_files = spec_data.get("relatedFiles", [])
    notes = spec_data.get("notes", [])

    name = metadata.get("name", "Screen")
    display_name = metadata.get("displayName", name)
    page_title = title or f"{name} - {display_name}"

    has_sidebar = all_tests_nav is not None

    parts = []

    # HTML header with styles
    parts.append(_get_html_header(page_title, has_sidebar))

    # Sidebar (if navigation data provided)
    if has_sidebar:
        # Import here to avoid circular imports
        from ..test_doc.html.sidebar import generate_spec_sidebar
        parts.append('<div class="layout-with-sidebar">')
        sidebar_parts = generate_spec_sidebar(display_name, all_tests_nav, current_path)
        parts.extend(sidebar_parts)
        parts.append('<main class="main-content">')

    # Main content
    parts.append('<div class="container">')

    # Title
    parts.append(f'<h1>{_e(name)} - {_e(display_name)}</h1>')

    # Hand-written unit tests are declared HERE and documented on their own
    # page. This is a link, not a copy: the declaration renders once, on the
    # Unit Tests side, and the spec page stays a screen specification. Absent
    # `unit_href` the page is byte-identical to what it was, so a project
    # with no unitContracts — and any caller that does not pass it — is
    # unaffected.
    if unit_href and spec_data.get("unitContracts") is not None:
        parts.append('<p class="unit-contract-link">')
        parts.append(
            f'Hand-written unit tests for this screen: '
            f'<a href="{_e(unit_href)}">Unit Tests</a>'
        )
        parts.append('</p>')

    # Overview
    parts.append('<section id="overview">')
    parts.append('<h2>Overview</h2>')
    parts.append(f'<p>{_e(metadata.get("description", ""))}</p>')

    # Metadata table
    if metadata.get("author") or metadata.get("createdAt") or metadata.get("updatedAt"):
        parts.append('<table class="meta-table">')
        if metadata.get("author"):
            parts.append(f'<tr><th>Author</th><td>{_e(metadata["author"])}</td></tr>')
        if metadata.get("createdAt"):
            parts.append(f'<tr><th>Created</th><td>{_e(metadata["createdAt"])}</td></tr>')
        if metadata.get("updatedAt"):
            parts.append(f'<tr><th>Updated</th><td>{_e(metadata["updatedAt"])}</td></tr>')
        parts.append('</table>')
    parts.append('</section>')

    # Sub-Specs (for screen_parent_spec)
    sub_specs = spec_data.get("subSpecs", [])
    if sub_specs:
        parts.append('<section id="sub-specs">')
        parts.append('<h2>Sub Specifications</h2>')
        # A parent page is an INDEX, and the absence of Data Flow / Validation
        # here is the design rather than a gap. Saying so is not decoration: a
        # lane read the four missing sections as a defect and filed it, and
        # nothing on the page could have told them otherwise. Absence is only
        # legible where the absence is.
        #
        # The index deliberately does not reproduce the sections. A merged view
        # would teach readers a shape the tools refuse — the parent may not
        # declare these sections at all — and a second copy of each one would
        # drift from the first.
        parts.append(
            '<p class="note">This screen is split across the sub-specs below. '
            'Its behaviour — data flow, state, user actions, validation — is '
            'declared in them and documented on their pages, not here. A '
            'parent spec may not declare those sections itself.</p>'
        )
        # The column is DROPPED, not blanked, when the sub-specs cannot be
        # read: an empty cell under a `Declares` heading asserts "this
        # sub-spec declares nothing", which is a wrong answer to the only
        # question the index exists to answer. No column asks the reader to
        # open the pages — slower, but true.
        show_declares = spec_dir is not None
        parts.append('<table>')
        parts.append('<thead><tr><th>Name</th><th>File</th>'
                     + ('<th>Declares</th>' if show_declares else '')
                     + '<th>Description</th></tr></thead>')
        parts.append('<tbody>')
        for sub in sub_specs:
            sub_name = _e(sub.get("name", "-"))
            sub_file = sub.get("file", "")
            sub_desc = _e(sub.get("description", "-"))
            declares = (f"<td>{_e(_sub_spec_sections(spec_dir, sub_file))}</td>"
                        if show_declares else "")
            # Create link to sub-spec HTML if current_path is available
            sub_html = sub_file.replace(".spec.json", ".html").split("/")[-1] if sub_file else ""
            sub_dir = "/".join(sub_file.split("/")[:-1]) if "/" in sub_file else ""
            if current_path and sub_html:
                # Compute relative link from current page to sub-spec
                from pathlib import Path
                current_dir = str(Path(current_path).parent)
                if sub_dir:
                    link = f"{sub_dir}/{sub_html}"
                else:
                    link = sub_html
                parts.append(f'<tr><td><a href="{link}">{sub_name}</a></td><td><code>{_e(sub_file)}</code></td>{declares}<td>{sub_desc}</td></tr>')
            else:
                parts.append(f'<tr><td>{sub_name}</td><td><code>{_e(sub_file)}</code></td>{declares}<td>{sub_desc}</td></tr>')
        parts.append('</tbody></table>')
        parts.append('</section>')

    # Screen Structure
    parts.append('<section id="structure">')
    parts.append('<h2>Screen Structure</h2>')

    # Components table (tree-style, collapsible per row)
    components = structure.get("components", [])
    if components:
        _append_components_table(parts, components, colors_map, title="UI Components", initial_depth=2)

    # Decorative Elements (A-2)
    decorative = structure.get("decorativeElements") or []
    if decorative:
        parts.append('<h3>Decorative Elements</h3>')
        parts.append('<table>')
        parts.append(
            '<thead><tr><th>ID</th><th>Purpose</th><th>Parent</th>'
            '<th>Components</th></tr></thead>'
        )
        parts.append('<tbody>')
        for elem in decorative:
            comp_ids = ', '.join(
                f'<code>{_e(c.get("id", ""))}</code>'
                for c in elem.get("components", []) or []
            )
            parts.append(
                '<tr>'
                f'<td><code>{_e(elem.get("id", "-"))}</code></td>'
                f'<td>{_e(elem.get("purpose", "-") or "-")}</td>'
                f'<td>{_e(elem.get("parentId", "-") or "-")}</td>'
                f'<td>{comp_ids or "-"}</td>'
                '</tr>'
            )
        parts.append('</tbody></table>')

    # Wrapper Views (A-6)
    wrappers = structure.get("wrapperViews") or []
    if wrappers:
        parts.append('<h3>Wrapper Views</h3>')
        parts.append('<table>')
        parts.append(
            '<thead><tr><th>ID</th><th>Wraps</th><th>Purpose</th>'
            '<th>Style</th></tr></thead>'
        )
        parts.append('<tbody>')
        for wv in wrappers:
            style = wv.get("style") or {}
            style_str = ', '.join(f'{k}={v}' for k, v in style.items()) or '-'
            parts.append(
                '<tr>'
                f'<td><code>{_e(wv.get("id", "-"))}</code></td>'
                f'<td><code>{_e(wv.get("wraps", "-"))}</code></td>'
                f'<td>{_e(wv.get("purpose", "-") or "-")}</td>'
                f'<td>{_e(style_str)}</td>'
                '</tr>'
            )
        parts.append('</tbody></table>')

    # Layout structure
    layout = structure.get("layout", {})
    if layout:
        parts.append('<h3>Layout Structure</h3>')
        parts.append('<pre class="layout-tree">')
        parts.append(_render_layout_tree_html(layout))
        parts.append('</pre>')

    if structure.get("notes"):
        parts.append(f'<p class="notes"><strong>Notes:</strong> {_e(structure["notes"])}</p>')

    # Collection(s) — structure.collection plus the multi-Collection
    # structure.collections[] form; each renders its own block.
    _all_collections = [
        c for c in [structure.get("collection"), *(structure.get("collections") or [])]
        if isinstance(c, dict)
    ]
    for collection in _all_collections:
        parts.append('<h3>Collection Structure</h3>')
        lazy_badge = ''
        # `lazy: false` opts out of virtualization. Call it out here because it
        # changes rendered output (no ScrollView / LazyColumn wrapper) and is
        # easy to miss when scanning the spec.
        if collection.get("lazy") is False:
            lazy_badge = (
                ' <span class="badge badge-non-lazy" '
                'title="Collection renders eagerly without a scroll container; '
                'the parent is expected to provide scrolling.">'
                'lazy: false</span>'
            )
        parts.append(
            f'<p><strong>Collection ID:</strong> '
            f'<code>{_e(collection.get("id", "-"))}</code>{lazy_badge}</p>'
        )

        cell_classes = collection.get("cellClasses") or []
        if isinstance(cell_classes, list) and cell_classes:
            refs_html = ", ".join(
                f'<code>{_e(ref)}</code>' for ref in cell_classes if isinstance(ref, str)
            )
            parts.append(f'<p><strong>Cell Classes:</strong> {refs_html}</p>')

        _render_collection_slot(parts, collection.get("header"), "Header Layout", "collection-header", colors_map)
        _render_collection_slot(parts, collection.get("cell"),   "Cell Layout",   "collection-cell",   colors_map)
        _render_collection_slot(parts, collection.get("footer"), "Footer Layout", "collection-footer", colors_map)

        resolved_cells = collection.get("_resolvedCells") or {}
        if isinstance(resolved_cells, dict) and resolved_cells:
            parts.append('<h4>Cell Layouts (resolved from cellClasses / sections)</h4>')
            for i, (ref, entry) in enumerate(resolved_cells.items(), start=1):
                wrapper_id = f"collection-cell-{i}"
                heading = f'<summary><strong>{_e(ref)}</strong></summary>'
                parts.append(f'<details class="resolved-cell" open>')
                parts.append(heading)
                if entry.get("components"):
                    _append_components_table(
                        parts,
                        entry["components"],
                        colors_map,
                        title=f'Components — {ref}',
                        initial_depth=2,
                        wrapper_id=wrapper_id,
                    )
                elif entry.get("layout"):
                    parts.append('<pre class="layout-tree">')
                    parts.append(_render_layout_tree_html(entry["layout"]))
                    parts.append('</pre>')
                else:
                    parts.append(f'<p><em>Layout file not found: <code>{_e(ref)}</code></em></p>')
                parts.append('</details>')

        sections = collection.get("sections") or []
        if isinstance(sections, list) and sections:
            section_rows = [s for s in sections if isinstance(s, dict)]
            if section_rows:
                parts.append('<h4>Sections</h4>')
                parts.append('<table>')
                parts.append('<thead><tr><th>#</th><th>Cell</th><th>Header</th><th>Footer</th></tr></thead>')
                parts.append('<tbody>')
                for i, sec in enumerate(section_rows, start=1):
                    parts.append(
                        '<tr>'
                        f'<td>{i}</td>'
                        f'<td>{_format_section_ref(sec.get("cell"))}</td>'
                        f'<td>{_format_section_ref(sec.get("header"))}</td>'
                        f'<td>{_format_section_ref(sec.get("footer"))}</td>'
                        '</tr>'
                    )
                parts.append('</tbody></table>')

    # TabView
    tab_view = structure.get("tabView")
    if tab_view:
        parts.append('<h3>TabView Structure</h3>')
        parts.append(f'<p><strong>TabView ID:</strong> <code>{_e(tab_view.get("id", "-"))}</code></p>')
        parts.append('<table>')
        parts.append('<thead><tr><th>Tab</th><th>Title</th><th>Layout File</th></tr></thead>')
        parts.append('<tbody>')
        for i, tab in enumerate(tab_view.get("tabs", []), 1):
            parts.append(f'<tr><td>{i}</td><td>{_e(tab.get("title", "-"))}</td><td><code>{_e(tab.get("layoutFile", "-"))}</code></td></tr>')
        parts.append('</tbody></table>')

    # Custom Components
    custom_components = structure.get("customComponents", [])
    if custom_components:
        parts.append('<h3>Custom Components</h3>')
        parts.append('<p>This screen uses the following custom components (third-party SDK, native features, etc.):</p>')
        parts.append('<table>')
        parts.append('<thead><tr><th>Component</th><th>Specification</th><th>Description</th></tr></thead>')
        parts.append('<tbody>')
        for cc in custom_components:
            cc_name = cc.get("name", "-")
            spec_file = cc.get("specFile", "")
            description = cc.get("description", "-")
            # Generate link to component HTML (convert .component.json to .html)
            if spec_file:
                html_file = spec_file.replace(".component.json", ".html")
                # Link path: ../components/html/{name}.html (relative from screens/html/)
                link_path = f"../../components/html/{html_file}"
                spec_link = f'<a href="{_e(link_path)}" class="component-link">{_e(spec_file)}</a>'
            else:
                spec_link = "-"
            parts.append(f'<tr><td><span class="custom-component-name">{_e(cc_name)}</span></td><td>{spec_link}</td><td>{_e(description)}</td></tr>')
        parts.append('</tbody></table>')

    parts.append('</section>')

    # Data Flow
    if data_flow:
        parts.append('<section id="dataflow">')
        parts.append('<h2>Data Flow</h2>')

        diagram = data_flow.get("diagram") or _build_dataflow_mermaid(
            metadata, data_flow
        )
        if diagram:
            # Mermaid reads the element's text content including HTML-like
            # markup (e.g. ``<br/>`` inside quoted labels). Applying html.escape
            # here would leak ``&quot;`` / ``&lt;br/&gt;`` into the graph, so we
            # pass the diagram source through unmodified.
            parts.append('<pre class="mermaid">')
            parts.append(diagram)
            parts.append('</pre>')

        view_model = data_flow.get("viewModel") or {}
        if view_model:
            parts.append('<h3>ViewModel</h3>')
            if view_model.get("description"):
                parts.append(f'<p>{_e(view_model["description"])}</p>')

            vm_methods = view_model.get("methods", [])
            if vm_methods:
                parts.append(
                    f'<details class="vm-section" open>'
                    f'<summary class="vm-section-header">Methods '
                    f'<span class="count-badge">{len(vm_methods)}</span></summary>'
                )
                parts.append('<table>')
                parts.append(
                    '<thead><tr><th>Signature</th><th>Platforms</th>'
                    '<th>Description</th></tr></thead>'
                )
                parts.append('<tbody>')
                for m in vm_methods:
                    sig = _format_vm_method_html(m)
                    plats = _format_member_platforms(m)
                    desc = m.get("description", "-") if isinstance(m, dict) else "-"
                    parts.append(f'<tr><td>{sig}</td><td>{plats}</td><td>{_e(desc)}</td></tr>')
                parts.append('</tbody></table>')
                parts.append('</details>')

            vm_vars = view_model.get("vars", [])
            if vm_vars:
                parts.append(
                    f'<details class="vm-section" open>'
                    f'<summary class="vm-section-header">Vars '
                    f'<span class="count-badge">{len(vm_vars)}</span></summary>'
                )
                parts.append('<table>')
                parts.append(
                    '<thead><tr><th>Declaration</th><th>Flags</th>'
                    '<th>Platforms</th><th>Description</th></tr></thead>'
                )
                parts.append('<tbody>')
                for v in vm_vars:
                    decl = _format_vm_var_html(v)
                    flags = _format_vm_var_flags(v)
                    plats = _format_member_platforms(v)
                    parts.append(
                        f'<tr><td>{decl}</td><td>{flags}</td>'
                        f'<td>{plats}</td><td>{_e(v.get("description", "-"))}</td></tr>'
                    )
                parts.append('</tbody></table>')
                parts.append('</details>')

        repos = data_flow.get("repositories", [])
        if repos:
            parts.append('<h3>Repositories</h3>')
            for repo in repos:
                parts.append(f'<h4>{_e(repo.get("name", "-"))}</h4>')
                parts.append('<ul>')
                for method in repo.get("methods", []):
                    parts.append(f'<li>{_format_method_html(method)}</li>')
                parts.append('</ul>')

        use_cases = data_flow.get("useCases", [])
        if use_cases:
            parts.append('<h3>UseCases</h3>')
            for uc in use_cases:
                parts.append(f'<h4>{_e(uc.get("name", "-"))}</h4>')
                if uc.get("description"):
                    parts.append(f'<p>{_e(uc["description"])}</p>')
                dep_repos = uc.get("repositories", [])
                if dep_repos:
                    parts.append(f'<p><strong>Dependencies:</strong> {", ".join(_e(r) for r in dep_repos)}</p>')
                parts.append('<ul>')
                for method in uc.get("methods", []):
                    parts.append(f'<li>{_format_method_html(method)}</li>')
                parts.append('</ul>')

        endpoints = data_flow.get("apiEndpoints", [])
        if endpoints:
            parts.append('<h3>API Endpoints</h3>')
            for endpoint in endpoints:
                method = endpoint.get("method", "GET")
                path = endpoint.get("path", "-")
                parts.append(f'<h4><span class="http-method method-{method.lower()}">{_e(method)}</span> {_e(path)}</h4>')

                request = endpoint.get("request")
                if request:
                    parts.append('<p><strong>Request:</strong></p>')
                    parts.append('<pre class="json">')
                    parts.append(_format_json_html(request))
                    parts.append('</pre>')

                response = endpoint.get("response")
                if response:
                    parts.append('<p><strong>Response:</strong></p>')
                    parts.append('<pre class="json">')
                    parts.append(_format_json_html(response))
                    parts.append('</pre>')

                if endpoint.get("notes"):
                    parts.append(f'<p class="notes"><strong>Notes:</strong> {_e(endpoint["notes"])}</p>')

        if data_flow.get("notes"):
            parts.append(f'<p class="notes"><strong>Notes:</strong> {_e(data_flow["notes"])}</p>')

        parts.append('</section>')

    # State Management
    if state_mgmt:
        parts.append('<section id="state">')
        parts.append('<h2>State Management</h2>')

        for state in state_mgmt.get("states", []):
            parts.append(f'<h3>{_e(state.get("name", "State"))}</h3>')
            parts.append('<table>')
            parts.append('<thead><tr><th>Value</th><th>Description</th><th>Visible Elements</th></tr></thead>')
            parts.append('<tbody>')
            for val in state.get("values", []):
                visible = ", ".join(f'<code>{_e(e)}</code>' for e in val.get("visibleElements", [])) or "-"
                parts.append(f'<tr><td><code>{_e(val.get("value", "-"))}</code></td><td>{_e(val.get("description", "-"))}</td><td>{visible}</td></tr>')
            parts.append('</tbody></table>')
            if state.get("notes"):
                parts.append(f'<p class="notes"><strong>Notes:</strong> {_e(state["notes"])}</p>')

        variables = state_mgmt.get("uiVariables", [])
        if variables:
            parts.append(
                f'<details class="vm-section" open>'
                f'<summary class="vm-section-header">UI Data Variables '
                f'<span class="count-badge">{len(variables)}</span></summary>'
            )
            parts.append('<table>')
            parts.append('<thead><tr><th>Variable</th><th>Type</th><th>Description</th><th>Notes</th></tr></thead>')
            parts.append('<tbody>')
            for var in variables:
                parts.append(f'<tr><td><code>{_e(var.get("name", "-"))}</code></td><td>{_e(var.get("type", "-"))}</td><td>{_e(var.get("description", "-"))}</td><td>{_e(var.get("notes", "") or "-")}</td></tr>')
            parts.append('</tbody></table>')
            parts.append('</details>')

        handlers = state_mgmt.get("eventHandlers", [])
        if handlers:
            parts.append(
                f'<details class="vm-section" open>'
                f'<summary class="vm-section-header">View-local Event Handlers '
                f'<span class="count-badge">{len(handlers)}</span></summary>'
            )
            parts.append(
                '<p class="section-intro">Handlers kept inside the View layer. '
                'ViewModel public API lives under <code>dataFlow.viewModel</code>.</p>'
            )
            parts.append('<table>')
            parts.append('<thead><tr><th>Handler</th><th>Description</th><th>Notes</th></tr></thead>')
            parts.append('<tbody>')
            for h in handlers:
                parts.append(
                    f'<tr><td><code>{_e(h.get("name", "-"))}</code></td>'
                    f'<td>{_e(h.get("description", "-"))}</td>'
                    f'<td>{_e(h.get("notes", "") or "-")}</td></tr>'
                )
            parts.append('</tbody></table>')
            parts.append('</details>')

        logic_rules = state_mgmt.get("displayLogic", [])
        if logic_rules:
            parts.append('<h3>Display Logic</h3>')
            parts.append('<pre class="display-logic">')
            for rule in logic_rules:
                parts.append(f'{_e(rule.get("condition", "-"))}:')
                for effect in rule.get("effects", []):
                    suffix = ""
                    var_name = effect.get("variableName")
                    if var_name:
                        suffix = f' [variable: {_e(var_name)}]'
                    parts.append(
                        f'  - {_e(effect.get("element", "-"))}: '
                        f'{_e(effect.get("state", "-"))}{suffix}'
                    )
                parts.append('')
            parts.append('</pre>')

        if state_mgmt.get("notes"):
            parts.append(f'<p class="notes"><strong>Notes:</strong> {_e(state_mgmt["notes"])}</p>')

        parts.append('</section>')

    # User Actions
    if user_actions:
        parts.append('<section id="actions">')
        parts.append('<h2>User Actions</h2>')
        parts.append('<table>')
        parts.append('<thead><tr><th>Action</th><th>Processing</th><th>Destination</th><th>Notes</th></tr></thead>')
        parts.append('<tbody>')
        for action in user_actions:
            parts.append(f'<tr><td>{_e(action.get("action", "-"))}</td><td>{_e(action.get("processing", "-"))}</td><td>{_e(action.get("destination", "") or "-")}</td><td>{_e(action.get("notes", "") or "-")}</td></tr>')
        parts.append('</tbody></table>')
        parts.append('</section>')

    # Validation
    if validation:
        parts.append('<section id="validation">')
        parts.append('<h2>Validation</h2>')

        client_side = validation.get("clientSide", [])
        if client_side:
            parts.append('<h3>Client-side</h3>')
            parts.append('<table>')
            parts.append('<thead><tr><th>Field</th><th>Rule</th><th>Notes</th></tr></thead>')
            parts.append('<tbody>')
            for v in client_side:
                parts.append(f'<tr><td>{_e(v.get("field", "-"))}</td><td>{_e(v.get("rule", "-"))}</td><td>{_e(v.get("notes", "") or "-")}</td></tr>')
            parts.append('</tbody></table>')

        server_side = validation.get("serverSide", [])
        if server_side:
            parts.append('<h3>Server-side</h3>')
            parts.append('<table>')
            parts.append('<thead><tr><th>Error Condition</th><th>Handling</th><th>Notes</th></tr></thead>')
            parts.append('<tbody>')
            for v in server_side:
                parts.append(f'<tr><td>{_e(v.get("condition", "-"))}</td><td>{_e(v.get("handling", "-"))}</td><td>{_e(v.get("notes", "") or "-")}</td></tr>')
            parts.append('</tbody></table>')

        if validation.get("notes"):
            parts.append(f'<p class="notes"><strong>Notes:</strong> {_e(validation["notes"])}</p>')

        parts.append('</section>')

    # Branch Contracts (opt-in decision tables)
    branch_contracts = spec_data.get("branchContracts") or {}
    if branch_contracts:
        parts.extend(_generate_branch_contracts_section(branch_contracts))

    # Transitions
    if transitions:
        parts.append('<section id="transitions">')
        parts.append('<h2>Transitions</h2>')
        parts.append('<table>')
        parts.append('<thead><tr><th>Condition</th><th>Destination</th><th>Notes</th></tr></thead>')
        parts.append('<tbody>')
        for trans in transitions:
            parts.append(f'<tr><td>{_e(trans.get("condition", "-"))}</td><td>{_e(trans.get("destination", "-"))}</td><td>{_e(trans.get("notes", "") or "-")}</td></tr>')
        parts.append('</tbody></table>')
        parts.append('</section>')

    # Related Files (grouped by type, collapsible per group)
    if related_files:
        groups: dict[str, list[dict]] = {}
        for f in related_files:
            t = f.get("type") or "-"
            groups.setdefault(t, []).append(f)

        parts.append('<section id="files">')
        parts.append('<div class="tree-wrapper" data-initial-depth="0">')
        parts.append('<div class="tree-table-header">')
        parts.append('<h2>Related Files</h2>')
        parts.append(
            '<div class="tree-controls">'
            '<button type="button" class="tree-expand-all">Expand all</button>'
            '<button type="button" class="tree-collapse-all">Collapse all</button>'
            '</div>'
        )
        parts.append('</div>')
        parts.append('<table class="tree-table">')
        parts.append('<thead><tr><th>Type</th><th>File Path</th><th>Notes</th></tr></thead>')
        parts.append('<tbody>')
        for gi, (gtype, gfiles) in enumerate(groups.items(), start=1):
            group_id = str(gi)
            parts.append(
                f'<tr class="tree-group" data-row-id="{_e(group_id)}" data-has-children="true">'
                '<td colspan="3">'
                '<span class="tree-toggle" role="button" aria-label="toggle">▶</span>'
                f'<span class="tree-group-name">{_e(gtype)}</span>'
                f'<span class="tree-group-count">{len(gfiles)}</span>'
                '</td></tr>'
            )
            for fi, f in enumerate(gfiles, start=1):
                row_id = f"{group_id}-{fi}"
                # Use a distinct name — `notes` at module scope is the
                # top-level spec Notes list rendered later in the page.
                file_note = f.get("notes") or f.get("description") or ""
                parts.append(
                    f'<tr data-row-id="{_e(row_id)}" data-parent-id="{_e(group_id)}">'
                    '<td class="tree-col">'
                    '<span class="tree-indent" style="width:16px"></span>'
                    '<span class="tree-spacer"></span>'
                    f'<code>{_e(f.get("type", "-"))}</code>'
                    '</td>'
                    f'<td><code>{_e(f.get("path", "-"))}</code></td>'
                    f'<td>{_e(file_note or "-")}</td>'
                    '</tr>'
                )
        parts.append('</tbody></table>')
        parts.append('</div>')  # tree-wrapper
        parts.append('</section>')

    # Notes
    if notes:
        parts.append('<section id="notes">')
        parts.append('<h2>Notes</h2>')
        parts.append('<ul>')
        for note in notes:
            parts.append(f'<li>{_e(note)}</li>')
        parts.append('</ul>')
        parts.append('</section>')

    parts.append('</div>')  # container

    # Close sidebar layout if present
    if has_sidebar:
        parts.append('</main>')  # main-content
        parts.append('</div>')  # layout-with-sidebar

    # Footer with Mermaid script
    parts.append(_get_html_footer(has_sidebar))

    return "\n".join(parts)


def _format_branch_value(value: Any) -> str:
    """Compact JSON-ish rendering of a when/then value."""
    import json as _json
    return _json.dumps(value, ensure_ascii=False)


def _format_branch_pairs(mapping: dict) -> str:
    """Render a when/then object as `key = value` lines."""
    lines = []
    for k, v in mapping.items():
        lines.append(f'<code>{_e(str(k))}</code> = <code>{_e(_format_branch_value(v))}</code>')
    return '<br>'.join(lines)


def _generate_branch_contracts_section(branch_contracts: dict) -> list[str]:
    """Decision-table rendering of branchContracts.

    Note branches (escape hatch) are rendered as distinct rows and counted
    in the section summary — undeclared branches stay visible, never
    silently dropped.
    """
    parts: list[str] = []
    conditions = branch_contracts.get("conditions") or {}
    methods = branch_contracts.get("methods") or {}

    declared = 0
    notes_only = 0
    platform_scoped = 0
    for contract in methods.values():
        if not isinstance(contract, dict):
            continue
        for branch in contract.get("branches", []) or []:
            if isinstance(branch, dict) and "note" in branch:
                notes_only += 1
            else:
                declared += 1
                if isinstance(branch, dict) and "platforms" in branch:
                    platform_scoped += 1

    parts.append('<section id="branch-contracts">')
    parts.append('<h2>Branch Contracts</h2>')
    summary = (
        f'{len(methods)} method(s) — {declared} declared branch(es), '
        f'{notes_only} note-only branch(es) outside the machine-checkable '
        'contract.'
    )
    if platform_scoped:
        # A branch that only exists on some platforms is a real difference
        # between implementations; the table has to say so, or a reader of
        # the generated doc sees a contract that their platform never runs.
        summary += (
            f' {platform_scoped} branch(es) are scoped to specific platforms.'
        )
    parts.append(f'<p class="notes">{summary}</p>')

    if conditions and isinstance(conditions, dict):
        parts.append('<h3>Named Conditions</h3>')
        parts.append('<table>')
        parts.append(
            '<thead><tr><th>Name</th><th>Meaning</th>'
            '<th>Witness (true)</th><th>Witness (false)</th></tr></thead>'
        )
        parts.append('<tbody>')
        for cname, cond in conditions.items():
            cond = cond if isinstance(cond, dict) else {}
            wt = cond.get("witness_true")
            wf = cond.get("witness_false")
            parts.append(
                f'<tr><td><code>{_e(str(cname))}</code></td>'
                f'<td>{_e(cond.get("meaning", "-") or "-")}</td>'
                f'<td>{_format_branch_pairs(wt) if isinstance(wt, dict) else "-"}</td>'
                f'<td>{_format_branch_pairs(wf) if isinstance(wf, dict) else "-"}</td></tr>'
            )
        parts.append('</tbody></table>')

    for method_name, contract in methods.items():
        if not isinstance(contract, dict):
            continue
        parts.append(f'<h3><code>{_e(str(method_name))}</code></h3>')
        baseline = contract.get("baseline")
        if isinstance(baseline, dict) and baseline:
            parts.append(
                f'<p class="notes"><strong>Baseline:</strong> '
                f'{_format_branch_pairs(baseline)}</p>'
            )
        branches = contract.get("branches", []) or []
        # The column appears only for methods that actually scope branches,
        # so single-platform projects keep the table they had.
        scoped = any(
            isinstance(b, dict) and "note" not in b and "platforms" in b
            for b in branches
        )
        parts.append('<table>')
        platform_header = '<th>Platforms</th>' if scoped else ''
        parts.append(
            f'<thead><tr><th>#</th><th>When</th><th>Then</th>'
            f'{platform_header}<th>Notes</th></tr></thead>'
        )
        parts.append('<tbody>')
        for i, branch in enumerate(branches, start=1):
            if not isinstance(branch, dict):
                continue
            if "note" in branch:
                parts.append(
                    f'<tr><td>{i}</td><td colspan="{4 if scoped else 3}">'
                    f'<em>note (not machine-checked): '
                    f'{_e(branch.get("note", "") or "")}</em></td></tr>'
                )
                continue
            when = branch.get("when")
            then = branch.get("then")
            platform_cell = (
                f'<td>{_format_member_platforms(branch)}</td>' if scoped else ''
            )
            parts.append(
                f'<tr><td>{i}</td>'
                f'<td>{_format_branch_pairs(when) if isinstance(when, dict) else "-"}</td>'
                f'<td>{_format_branch_pairs(then) if isinstance(then, dict) else "-"}</td>'
                f'{platform_cell}'
                f'<td>{_e(branch.get("notes", "") or "-")}</td></tr>'
            )
        parts.append('</tbody></table>')

    if branch_contracts.get("notes"):
        parts.append(
            f'<p class="notes"><strong>Notes:</strong> '
            f'{_e(branch_contracts["notes"])}</p>'
        )
    parts.append('</section>')
    return parts


def _format_method_params(params) -> str:
    """Format method params (string or structured array) to display string."""
    if isinstance(params, list):
        return ", ".join(f"{p.get('name', '?')}: {p.get('type', '?')}" for p in params if isinstance(p, dict))
    return str(params) if params else ""


def _format_method_html(method) -> str:
    """Format a method (string or dict) as HTML."""
    if isinstance(method, dict):
        method_name = _e(method.get("name", ""))
        params = _format_method_params(method.get("params"))
        return_type = _e(method.get("returnType", ""))
        is_async = method.get("isAsync", True)
        async_prefix = "async " if is_async else ""
        method_str = f'<code>{async_prefix}{method_name}({_e(params)})</code>'
        if return_type:
            method_str += f' → <code class="return-type">{return_type}</code>'
        if method.get("description"):
            method_str += f' — {_e(method["description"])}'
        return method_str
    else:
        return f'<code>{_e(method)}</code>'


def _format_vm_method_html(method) -> str:
    """Render a ``dataFlow.viewModel.methods`` entry as an HTML signature.

    ViewModel methods default to ``isAsync: false`` (sync button taps are
    the common case). Repository/UseCase methods still default to async
    via ``_format_method_html``.
    """
    if isinstance(method, str):
        return f'<code>{_e(method)}()</code>'
    if not isinstance(method, dict):
        return '<code>-</code>'
    name = _e(method.get("name", "-"))
    params = _format_method_params(method.get("params"))
    return_type = _e(method.get("returnType", ""))
    is_async = bool(method.get("isAsync", False))
    async_prefix = "async " if is_async else ""
    sig = f'<code>{async_prefix}{name}({_e(params)})</code>'
    if return_type:
        sig += f' → <code class="return-type">{return_type}</code>'
    return sig


def _format_vm_var_html(var: dict) -> str:
    name = _e(var.get("name", "-"))
    raw_type = var.get("type", "-")
    if bool(var.get("optional", False)) and "->" in raw_type and not raw_type.endswith("?"):
        raw_type = f"({raw_type})?"
    elif bool(var.get("optional", False)) and not raw_type.endswith("?"):
        raw_type = f"{raw_type}?"
    keyword = "let" if var.get("readOnly") and not var.get("observable", True) else "var"
    return f'<code>{keyword} {name}: {_e(raw_type)}</code>'


def _format_vm_var_flags(var: dict) -> str:
    chips = []
    if var.get("observable", True):
        chips.append('<span class="flag-chip flag-observable">observable</span>')
    if var.get("optional"):
        chips.append('<span class="flag-chip flag-optional">optional</span>')
    if var.get("readOnly"):
        chips.append('<span class="flag-chip flag-readonly">readOnly</span>')
    return "".join(chips) if chips else "—"


def _format_member_platforms(member: dict) -> str:
    """Render a member's ``platforms`` field.

    - omitted → "all"
    - `[]` (vars) → "— (none)" with warning title
    - populated list → platform badges
    """
    if not isinstance(member, dict):
        return "—"
    if "platforms" not in member:
        return '<em title="Imported into all platforms">all</em>'
    raw = member.get("platforms")
    if not isinstance(raw, list):
        return '<em>invalid</em>'
    if not raw:
        return '<em title="Explicit [] — not imported anywhere">— (none)</em>'
    return "".join(
        f'<span class="platform-badge platform-{_e(str(p))}">{_e(str(p))}</span>'
        for p in raw
    )


def _e(text: str) -> str:
    """Escape HTML special characters."""
    if text is None:
        return ""
    return html.escape(str(text))


def _sanitize_mermaid_id(raw: str) -> str:
    import re as _re
    cleaned = _re.sub(r"[^A-Za-z0-9_]", "_", raw or "")
    if not cleaned or not cleaned[0].isalpha():
        cleaned = "n_" + cleaned
    return cleaned


def _mermaid_label(raw: str) -> str:
    s = (raw or "").replace('"', "'")
    return s.replace("\n", "<br/>")


def _parse_endpoint_ref(ref: str) -> tuple[str, str] | None:
    """Parse ``"METHOD /path"`` into ``(METHOD, /path)``. Tolerates extra
    whitespace. Returns ``None`` on bad input."""
    if not isinstance(ref, str):
        return None
    parts = ref.strip().split(None, 1)
    if len(parts) != 2:
        return None
    method, path = parts[0].upper(), parts[1].strip()
    if not path.startswith("/"):
        return None
    return method, path


def _collect_method_endpoints(method: dict) -> list[str]:
    """Collect declared endpoint refs for a repo method.

    Accepts either ``endpoint`` (single str) or ``endpoints`` (list of str),
    or both.
    """
    refs: list[str] = []
    single = method.get("endpoint")
    if isinstance(single, str):
        refs.append(single)
    multi = method.get("endpoints") or []
    if isinstance(multi, list):
        refs.extend(r for r in multi if isinstance(r, str))
    return refs


def _build_dataflow_mermaid(metadata: dict, data_flow: dict) -> str | None:
    """Auto-generate a Mermaid flowchart describing
    View → ViewModel → UseCase → Repository → API layering.

    Explicit linkage from the spec is preferred over structural fan-out:

    * ``useCase.repositories`` declares which repos a UseCase depends on.
      UseCase methods may additionally declare ``calls: ["Repo.method", ...]``
      — repos referenced there are merged into the dependency set.
    * Repository methods may declare ``endpoint`` (single ``"METHOD /path"``)
      or ``endpoints`` (list). Only those references produce Repo→Endpoint
      edges — no more cartesian fan-out between repos and endpoints.

    Returns ``None`` when there isn't enough structure for a useful diagram.
    """
    vm = data_flow.get("viewModel") or {}
    use_cases = data_flow.get("useCases") or []
    repos = data_flow.get("repositories") or []
    endpoints = data_flow.get("apiEndpoints") or []

    if not (vm or use_cases or repos or endpoints):
        return None

    name = metadata.get("name", "Screen")
    display_name = metadata.get("displayName", name)

    lines: list[str] = ["flowchart LR"]

    view_id = _sanitize_mermaid_id(f"V_{name}")
    lines.append(f'    {view_id}["{_mermaid_label(display_name)}<br/>(View)"]')

    vm_id: str | None = None
    if vm:
        vm_id = _sanitize_mermaid_id(f"VM_{name}")
        vm_count = len(vm.get("methods", []) or [])
        vm_label = f"{name}ViewModel"
        if vm_count:
            vm_label += f"<br/>{vm_count} methods"
        lines.append(f'    {vm_id}["{_mermaid_label(vm_label)}"]')
        lines.append(f"    {view_id} --> {vm_id}")

    uc_entries: list[tuple[str, str, list[str]]] = []
    for uc in use_cases:
        uc_name = uc.get("name", "UseCase")
        uid = _sanitize_mermaid_id(f"UC_{uc_name}")
        # Explicit dependency list (preferred), accept either spelling.
        deps = list(uc.get("repositories") or uc.get("dependencies") or [])
        # Merge in repos referenced from method-level ``calls`` lists.
        for m in uc.get("methods") or []:
            for ref in m.get("calls") or []:
                if not isinstance(ref, str) or "." not in ref:
                    continue
                repo_name = ref.split(".", 1)[0]
                if repo_name and repo_name not in deps:
                    deps.append(repo_name)
        uc_entries.append((uid, uc_name, deps))
        count = len(uc.get("methods", []) or [])
        label = uc_name + (f"<br/>{count} methods" if count else "")
        lines.append(f'    {uid}["{_mermaid_label(label)}"]')
        if vm_id:
            lines.append(f"    {vm_id} --> {uid}")

    repo_ids: dict[str, str] = {}
    repo_method_endpoints: dict[str, list[tuple[str, str]]] = {}
    for repo in repos:
        rname = repo.get("name", "Repository")
        rid = _sanitize_mermaid_id(f"R_{rname}")
        repo_ids[rname] = rid
        count = len(repo.get("methods", []) or [])
        label = rname + (f"<br/>{count} methods" if count else "")
        lines.append(f'    {rid}["{_mermaid_label(label)}"]')
        declared: list[tuple[str, str]] = []
        for m in repo.get("methods") or []:
            for ref in _collect_method_endpoints(m):
                parsed = _parse_endpoint_ref(ref)
                if parsed:
                    declared.append(parsed)
        repo_method_endpoints[rname] = declared

    if uc_entries and repo_ids:
        for uid, _uc_name, dep_names in uc_entries:
            targets = [repo_ids[n] for n in dep_names if n in repo_ids]
            if not targets:
                # No explicit or inferred linkage — fall back to fan-out so
                # the UC isn't left floating.
                targets = list(repo_ids.values())
            for rid in targets:
                lines.append(f"    {uid} --> {rid}")
    elif vm_id and repo_ids and not uc_entries:
        for rid in repo_ids.values():
            lines.append(f"    {vm_id} --> {rid}")

    if endpoints:
        # Map (METHOD, /path) → endpoint node id so repo methods can point at
        # the right one.
        ep_id_by_ref: dict[tuple[str, str], str] = {}
        ep_ids_ordered: list[str] = []
        for idx, ep in enumerate(endpoints):
            path = ep.get("path", "/")
            method = (ep.get("method") or "GET").upper()
            eid = _sanitize_mermaid_id(f"E_{idx}_{method}_{path}")
            ep_id_by_ref[(method, path)] = eid
            ep_ids_ordered.append(eid)

        declared_edges: list[tuple[str, str]] = []
        for rname, refs in repo_method_endpoints.items():
            rid = repo_ids.get(rname)
            if not rid:
                continue
            seen: set[str] = set()
            for key in refs:
                eid = ep_id_by_ref.get(key)
                if eid and eid not in seen:
                    declared_edges.append((rid, eid))
                    seen.add(eid)

        if declared_edges:
            # Honour explicit spec linkage. Only emit nodes for endpoints that
            # actually appear on either side of a declared edge — plus the
            # rest as standalone nodes so they're still discoverable — but
            # keep the visual load down by collapsing leftovers when huge.
            referenced_ids = {eid for _, eid in declared_edges}
            orphan_ids = [e for e in ep_ids_ordered if e not in referenced_ids]
            for idx, ep in enumerate(endpoints):
                path = ep.get("path", "/")
                method = (ep.get("method") or "GET").upper()
                eid = ep_id_by_ref[(method, path)]
                if eid in referenced_ids or len(orphan_ids) <= 4:
                    label = f"{method} {path}"
                    lines.append(
                        f'    {eid}["{_mermaid_label(label)}"]'
                    )
            if len(orphan_ids) > 4:
                api_id = "API_misc"
                lines.append(
                    f'    {api_id}["Other endpoints<br/>'
                    f'{len(orphan_ids)} endpoints"]'
                )
            for rid, eid in declared_edges:
                lines.append(f"    {rid} --> {eid}")
        else:
            # No explicit repo→endpoint linkage anywhere. Don't invent edges
            # — just surface the endpoints as nodes (collapsed when large).
            if len(endpoints) > 4:
                api_id = "API"
                api_label = f"API<br/>{len(endpoints)} endpoints"
                lines.append(f'    {api_id}["{_mermaid_label(api_label)}"]')
            else:
                for idx, ep in enumerate(endpoints):
                    path = ep.get("path", "/")
                    method = (ep.get("method") or "GET").upper()
                    eid = ep_id_by_ref[(method, path)]
                    label = f"{method} {path}"
                    lines.append(f'    {eid}["{_mermaid_label(label)}"]')

    if len(lines) < 3:
        return None
    return "\n".join(lines)


def _load_colors_map(layouts_dir: Path | None) -> dict[str, str]:
    """Load token → hex map from ``{layouts_dir}/Resources/colors.json``.

    Returns an empty dict when the file is missing or malformed.
    """
    if layouts_dir is None:
        return {}
    import json as _json
    candidate = Path(layouts_dir) / "Resources" / "colors.json"
    if not candidate.exists():
        return {}
    try:
        data = _json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in data.items() if isinstance(v, str)}


def _css_color_from_token(token: str, colors: dict[str, str]) -> tuple[str, str] | None:
    """Resolve *token* through *colors* and return (css_color, raw_hex).

    ``colors.json`` stores values as ``#RRGGBB`` or ``#AARRGGBB`` (alpha-first).
    CSS expects ``#RRGGBBAA`` (alpha-last), so we reorder when needed.
    Returns ``None`` if the token is unknown.
    """
    raw = colors.get(token)
    if not raw or not raw.startswith("#"):
        return None
    if len(raw) == 9:  # #AARRGGBB → #RRGGBBAA
        css = f"#{raw[3:5]}{raw[5:7]}{raw[7:9]}{raw[1:3]}"
    else:
        css = raw
    return css, raw


def _render_swatch(token: str, colors: dict[str, str]) -> str:
    """Render ``■ token_name #hex``. Falls back to the raw code if unknown."""
    resolved = _css_color_from_token(token, colors)
    if resolved is None:
        # Literal hex in the layout (no token lookup needed)
        if isinstance(token, str) and token.startswith("#"):
            return f'<span class="swatch"><i style="background:{_e(token)}"></i><code>{_e(token)}</code></span>'
        return f'<code>{_e(token)}</code>'
    css, raw = resolved
    return (
        '<span class="swatch">'
        f'<i style="background:{_e(css)}"></i>'
        f'<code>{_e(token)}</code>'
        f'<span class="swatch-hex">{_e(raw)}</span>'
        '</span>'
    )


def _render_style_description(style: dict[str, Any], colors: dict[str, str]) -> str:
    """Render per-component style attributes as a Pattern-B labeled block."""
    if not isinstance(style, dict) or not style:
        return ""

    rows: list[tuple[str, str]] = []

    # Size
    size_bits: list[str] = []
    if style.get("width") is not None:
        size_bits.append(f"W={_e(style['width'])}")
    if style.get("height") is not None:
        size_bits.append(f"H={_e(style['height'])}")
    if style.get("weight") is not None:
        size_bits.append(f"weight={_e(style['weight'])}")
    if size_bits:
        rows.append(("Size", " ".join(size_bits)))

    # Margins
    margin_bits = [
        f"{k[0]}m={_e(style[k])}"
        for k in ("topMargin", "rightMargin", "bottomMargin", "leftMargin")
        if k in style
    ]
    if margin_bits:
        rows.append(("Margins", " ".join(margin_bits)))

    # Paddings (Android/web style names)
    padding_bits = [
        f"{k[0]}p={_e(style[k])}"
        for k in ("topPadding", "rightPadding", "bottomPadding", "leftPadding", "padding")
        if k in style
    ]
    if padding_bits:
        rows.append(("Padding", " ".join(padding_bits)))

    # Colors
    color_bits: list[str] = []
    for key, label in (
        ("background", "bg"),
        ("fontColor", "fg"),
        ("borderColor", "border"),
        ("hintColor", "hint"),
        ("tintColor", "tint"),
    ):
        val = style.get(key)
        if isinstance(val, str) and val:
            color_bits.append(
                f'<span class="style-lbl">{label}:</span>{_render_swatch(val, colors)}'
            )
    if color_bits:
        rows.append(("Colors", " ".join(color_bits)))

    # Font
    font_bits: list[str] = []
    if "fontSize" in style:
        font_bits.append(f"{_e(style['fontSize'])}")
    if "font" in style:
        font_bits.append(_e(style["font"]))
    if "textAlign" in style:
        font_bits.append(_e(style["textAlign"]))
    if font_bits:
        rows.append(("Font", " ".join(font_bits)))

    # Shape / visual
    shape_bits: list[str] = []
    for key, label in (
        ("cornerRadius", "r"),
        ("borderWidth", "bw"),
        ("alpha", "α"),
    ):
        if key in style:
            shape_bits.append(f"{label}={_e(style[key])}")
    if "contentMode" in style:
        shape_bits.append(f"mode={_e(style['contentMode'])}")
    if "orientation" in style:
        shape_bits.append(f"dir={_e(style['orientation'])}")
    if "gravity" in style:
        shape_bits.append(f"gravity={_e(style['gravity'])}")
    if shape_bits:
        rows.append(("Shape", " ".join(shape_bits)))

    if not rows:
        return ""

    return (
        '<div class="style-rows">'
        + "".join(
            f'<div class="style-row"><span class="style-key">{_e(k)}</span>{v}</div>'
            for k, v in rows
        )
        + "</div>"
    )


def _render_description_cell(comp: dict, colors: dict[str, str]) -> str:
    """Pattern-B style block (Size / Margins / Colors / Font / Shape).

    Author-written ``description`` is rendered in the Notes column instead,
    so this column is strictly view appearance info.
    """
    style_html = _render_style_description(comp.get("style") or {}, colors)
    return style_html or "-"


_EVENT_BINDING_KEYS = {
    "onClick", "onLongPress", "onValueChange", "onTextChange",
    "onSelect", "onTabChange", "onSubmit", "onSignIn",
    "onAppear", "onDisappear", "onRefresh",
}


def _render_bindings_cell(comp: dict) -> str:
    """Render comp["binding"] as Pattern-C badge rows.

    Events (onClick, onTextChange, ...) get the amber ``event`` badge
    with a one-way arrow (``→``); data bindings (text, enabled, hidden,
    ...) get the blue ``bind`` badge with a two-way arrow (``↔``).
    """
    binding = comp.get("binding") or {}
    if not isinstance(binding, dict) or not binding:
        return "-"

    rows: list[str] = []
    # Events first, bindings second — stable insertion order otherwise.
    events = [(k, v) for k, v in binding.items() if k in _EVENT_BINDING_KEYS]
    data = [(k, v) for k, v in binding.items() if k not in _EVENT_BINDING_KEYS]

    for k, v in events:
        rows.append(
            '<div>'
            '<span class="bind-badge bind-event">event</span> '
            f'<code>{_e(k)}</code> → <code>{_e(v)}</code>'
            '</div>'
        )
    for k, v in data:
        rows.append(
            '<div>'
            '<span class="bind-badge bind-data">bind</span> '
            f'<code>{_e(k)}</code> ↔ <code>{_e(v)}</code>'
            '</div>'
        )
    return '<div class="bind-cell">' + "".join(rows) + '</div>'


def _render_notes_cell(comp: dict) -> str:
    """Notes column: merge author ``description`` + ``notes``.

    Both may be present — description comes first, notes second on its
    own line. Falls back to ``-`` if neither exists.
    """
    desc = (comp.get("description") or "").strip()
    notes = (comp.get("notes") or "").strip()
    parts: list[str] = []
    if desc:
        parts.append(f'<div>{_e(desc)}</div>')
    if notes:
        parts.append(f'<div>{_e(notes)}</div>')
    return "".join(parts) or "-"


_PLATFORM_TOKEN_TO_LABEL = {
    "ios": "iOS", "swift": "iOS", "swiftui": "iOS", "uikit": "iOS",
    "android": "Android", "kotlin": "Android", "java": "Android",
    "compose": "Android", "xml": "Android",
    "web": "Web", "typescript": "Web", "javascript": "Web", "react": "Web",
}


def _render_platform_badge(value) -> str:
    """Render a platform filter (string or override dict) as HTML badges."""
    if not value:
        return '-'
    if isinstance(value, str):
        tokens = [t.strip().lower() for t in value.split(",") if t.strip()]
        labels = []
        seen = set()
        for t in tokens:
            label = _PLATFORM_TOKEN_TO_LABEL.get(t, t)
            if label not in seen:
                labels.append(label)
                seen.add(label)
        return ' '.join(
            f'<span class="platform-badge platform-{_e(l.lower())}">{_e(l)}</span>'
            for l in labels
        )
    if isinstance(value, dict):
        # Dict-valued platform is an override map — show which platforms have overrides
        keys = [k for k in value.keys() if k in ("ios", "android", "web")]
        if not keys:
            return '-'
        return ' '.join(
            f'<span class="platform-badge platform-override platform-{_e(k)}">{_e(k.capitalize())}*</span>'
            for k in keys
        )
    return '-'


def _render_collection_slot(
    parts: list,
    slot: Any,
    title: str,
    wrapper_id: str,
    colors_map: dict[str, str],
) -> None:
    """Render a single cell/header/footer slot.

    Picks the richest representation available:
      * expanded components tree (from layoutFile import) → full Components table
      * layoutFile still set without expansion (file missing) → show the ref
      * legacy layout tree (root/children) → tree-style rendering
    """
    if not slot:
        return
    parts.append(f'<h4>{_e(title)}</h4>')
    if isinstance(slot, dict):
        layout_ref = slot.get("layoutFile") or slot.get("layout")
        if layout_ref and not slot.get("components"):
            parts.append(f'<p><em>Layout file not found: <code>{_e(layout_ref)}</code></em></p>')
            return
        if slot.get("components"):
            _append_components_table(
                parts,
                slot["components"],
                colors_map,
                title=f'{title} — Components',
                initial_depth=2,
                wrapper_id=wrapper_id,
            )
            return
    parts.append('<pre class="layout-tree">')
    parts.append(_render_layout_tree_html(slot))
    parts.append('</pre>')


def _format_section_ref(ref: Any) -> str:
    if not ref:
        return '-'
    if isinstance(ref, str):
        return f'<code>{_e(ref)}</code>'
    if isinstance(ref, dict):
        name = ref.get("layoutFile") or ref.get("layout") or ref.get("id") or ""
        return f'<code>{_e(name)}</code>' if name else '-'
    return '-'


def _append_components_table(
    parts: list,
    components: list,
    colors_map: dict[str, str],
    *,
    title: str,
    initial_depth: int = 2,
    wrapper_id: str = "",
) -> None:
    """Append the collapsible tree-style components table to *parts*.

    Used both by the main spec's "UI Components" section and by Collection
    cell/header/footer expansions. When *wrapper_id* is empty the tree IDs
    are unsuffixed (keeps the top-level table DOM stable); when supplied it
    is injected into every `data-row-id` / `data-parent-id` so multiple
    tables on the same page don't collide.
    """
    def _prefix(base: str) -> str:
        return f"{wrapper_id}-{base}" if wrapper_id else base

    parts.append(f'<div class="tree-wrapper" data-initial-depth="{initial_depth}">')
    parts.append('<div class="tree-table-header">')
    parts.append(f'<h3>{_e(title)}</h3>')
    parts.append(
        '<div class="tree-controls">'
        '<button type="button" class="tree-expand-all">Expand all</button>'
        '<button type="button" class="tree-collapse-all">Collapse all</button>'
        '</div>'
    )
    parts.append('</div>')
    parts.append('<table class="tree-table">')
    parts.append(
        '<thead><tr><th>Component</th><th>ID</th><th>Platform</th>'
        '<th>Description</th><th>Bindings</th><th>Notes</th></tr></thead>'
    )
    parts.append('<tbody>')

    def _render_comp_row(comp: dict, depth: int, path: tuple[int, ...]) -> None:
        row_id = _prefix("-".join(str(n) for n in path))
        parent_id = _prefix("-".join(str(n) for n in path[:-1])) if depth > 0 else ""
        children = [c for c in (comp.get("children") or []) if isinstance(c, dict)]
        has_children = bool(children)

        attrs = [f'data-row-id="{_e(row_id)}"']
        if parent_id:
            attrs.append(f'data-parent-id="{_e(parent_id)}"')
        if has_children:
            attrs.append('data-has-children="true"')

        indent_px = depth * 16
        toggle = (
            '<span class="tree-toggle" role="button" aria-label="toggle">▶</span>'
            if has_children else '<span class="tree-spacer"></span>'
        )
        parts.append(f'<tr {" ".join(attrs)}>')
        parts.append(
            '<td class="tree-col">'
            f'<span class="tree-indent" style="width:{indent_px}px"></span>'
            f'{toggle}'
            f'<span class="component-type">{_e(comp.get("type", "-"))}</span>'
            '</td>'
        )
        parts.append(f'<td><code>{_e(comp.get("id", "-"))}</code></td>')
        parts.append(f'<td>{_render_platform_badge(comp.get("platform"))}</td>')
        parts.append(f'<td>{_render_description_cell(comp, colors_map)}</td>')
        parts.append(f'<td>{_render_bindings_cell(comp)}</td>')
        parts.append(f'<td>{_render_notes_cell(comp)}</td>')
        parts.append('</tr>')
        for i, child in enumerate(children, start=1):
            _render_comp_row(child, depth + 1, path + (i,))

    for i, comp in enumerate(components, start=1):
        _render_comp_row(comp, 0, (i,))
    parts.append('</tbody></table>')
    parts.append('</div>')  # tree-wrapper


def _render_layout_tree_html(layout: dict) -> str:
    """Render layout structure as HTML tree."""
    lines = []
    root = layout.get("root", "root")
    children = layout.get("children", [])

    lines.append(_e(root))

    def render_children(children_list: list, depth: int, is_parent_last: bool) -> list[str]:
        result = []
        for i, child in enumerate(children_list):
            is_last = i == len(children_list) - 1
            prefix = "└── " if is_last else "├── "
            indent = ""
            for d in range(depth):
                indent += "    " if is_parent_last else "│   "

            if isinstance(child, str):
                result.append(f"{indent}{prefix}{_e(child)}")
            elif isinstance(child, dict):
                child_id = child.get("id", "?")
                result.append(f"{indent}{prefix}{_e(child_id)}")
                nested = child.get("children", [])
                if nested:
                    result.extend(render_children(nested, depth + 1, is_last))
        return result

    lines.extend(render_children(children, 0, False))
    return "\n".join(lines)


def _format_json_html(schema: dict) -> str:
    """Format JSON schema for HTML display."""
    import json
    return _e(json.dumps(schema, indent=2, ensure_ascii=False))


def _get_html_header(title: str, has_sidebar: bool = False) -> str:
    """Get HTML header with styles."""
    sidebar_styles = ""
    if has_sidebar:
        sidebar_styles = '''
        /* Sidebar layout styles */
        body { padding: 0; }
        .layout-with-sidebar { display: flex; min-height: 100vh; }
        .sidebar {
            width: 280px;
            min-width: 280px;
            background: #1e293b;
            color: #e2e8f0;
            padding: 1.5rem;
            position: sticky;
            top: 0;
            height: 100vh;
            overflow-y: auto;
            box-shadow: 2px 0 5px rgba(0,0,0,0.1);
        }
        .sidebar h2 {
            font-size: 1.1rem;
            margin: 0 0 1rem 0;
            padding-bottom: 0.5rem;
            border-bottom: 1px solid #475569;
            color: #f8fafc;
        }
        .sidebar .back-link {
            display: block;
            color: #94a3b8;
            text-decoration: none;
            font-size: 0.9rem;
            margin-bottom: 1rem;
            padding: 0.5rem;
            border-radius: 4px;
            transition: background-color 0.2s;
        }
        .sidebar .back-link:hover { background: #334155; color: #f8fafc; }
        .sidebar-section { margin-bottom: 1rem; }
        .sidebar-title {
            font-size: 0.85rem;
            font-weight: 600;
            color: #94a3b8;
            cursor: pointer;
            padding: 0.5rem;
            border-radius: 4px;
            display: flex;
            align-items: center;
            gap: 0.5rem;
            transition: background-color 0.2s;
        }
        .sidebar-title:hover { background: #334155; }
        .sidebar-title .arrow { font-size: 0.7rem; transition: transform 0.2s; }
        .sidebar-title.collapsed .arrow { transform: rotate(-90deg); }
        .sidebar-title .count {
            background: #475569;
            color: #e2e8f0;
            padding: 0.1rem 0.4rem;
            border-radius: 10px;
            font-size: 0.75rem;
            margin-left: auto;
        }
        .sidebar-title.spec { color: #a78bfa; }
        .sidebar-title.component { color: #34d399; }
        .sidebar-title.flow { color: #60a5fa; }
        .sidebar-title.app { color: #38bdf8; font-weight: bold; }
        .sidebar-subtitle { font-size: 0.8rem; color: #94a3b8; cursor: pointer; display: flex; align-items: center; gap: 0.4rem; padding: 5px 8px; border-radius: 4px; transition: background-color 0.2s; }
        .sidebar-subtitle:hover { background: #334155; }
        .sidebar-subtitle .arrow { transition: transform 0.3s; font-size: 0.65rem; }
        .sidebar-subtitle.collapsed .arrow { transform: rotate(-90deg); }
        .sidebar-subtitle .count { background: #475569; color: #e2e8f0; padding: 1px 6px; border-radius: 8px; font-size: 0.7rem; margin-left: auto; }
        .sidebar-subsection { margin-left: 8px; margin-bottom: 2px; }
        hr.sidebar-divider { border: none; border-top: 1px solid #475569; margin: 8px 12px; }
        .sidebar-list { padding: 0; }
        .sidebar-list.collapsed { display: none; }
        .sidebar-list ul { list-style: none; padding: 0; margin: 0; }
        .sidebar-list li { margin: 0; }
        .sidebar-list a {
            display: block;
            color: #cbd5e1;
            text-decoration: none;
            padding: 0.4rem 0.5rem 0.4rem 1.5rem;
            font-size: 0.85rem;
            border-radius: 4px;
            transition: background-color 0.2s;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .sidebar-list a:hover { background: #334155; color: #f8fafc; }
        .sidebar-list a.current { background: #3b82f6; color: #fff; }
        .main-content { flex: 1; padding: 2rem; overflow-x: auto; }
        .main-content .container { max-width: none; }
'''
    return f'''<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{_e(title)}</title>
    <style>
        :root {{
            --primary-color: #2563eb;
            --bg-color: #f8fafc;
            --text-color: #1e293b;
            --border-color: #e2e8f0;
            --code-bg: #f1f5f9;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6;
            color: var(--text-color);
            background: var(--bg-color);
            padding: 2rem;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            padding: 2rem;
            border-radius: 8px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }}
        h1 {{ color: var(--text-color); margin-bottom: 1.5rem; font-size: 2rem; }}
        h2 {{ color: var(--text-color); margin: 2rem 0 1rem; padding-bottom: 0.5rem; border-bottom: 2px solid var(--border-color); }}
        h3 {{ color: var(--text-color); margin: 1.5rem 0 0.75rem; }}
        h4 {{ color: #64748b; margin: 1rem 0 0.5rem; }}
        section {{ margin-bottom: 2rem; }}
        table {{ width: 100%; border-collapse: collapse; margin: 1rem 0; }}
        th, td {{ padding: 0.75rem; text-align: left; border: 1px solid var(--border-color); }}
        th {{ background: var(--bg-color); font-weight: 600; }}
        tr:hover {{ background: #f8fafc; }}
        code {{ background: var(--code-bg); padding: 0.2em 0.4em; border-radius: 4px; font-family: 'SF Mono', Monaco, monospace; font-size: 0.9em; }}
        pre {{ background: var(--code-bg); padding: 1rem; border-radius: 8px; overflow-x: auto; font-family: 'SF Mono', Monaco, monospace; font-size: 0.9em; line-height: 1.5; }}
        .meta-table {{ width: auto; }}
        .meta-table th {{ background: transparent; border: none; padding: 0.25rem 1rem 0.25rem 0; }}
        .meta-table td {{ border: none; padding: 0.25rem 0; }}
        .component-type {{ background: var(--bg-color); color: var(--text-color); padding: 0.2em 0.5em; border-radius: 4px; font-size: 0.85em; border: 1px solid var(--border-color); }}
        .platform-badge {{ display: inline-block; padding: 0.15em 0.5em; margin-right: 0.25em; border-radius: 3px; font-size: 0.75em; font-weight: 600; }}
        .platform-ios {{ background: #dbeafe; color: #1e40af; }}
        .platform-android {{ background: #dcfce7; color: #166534; }}
        .platform-web {{ background: #fef3c7; color: #92400e; }}
        .platform-override {{ opacity: 0.75; font-style: italic; }}
        /* ViewModel / event-handler collapsible sections */
        details.vm-section {{ margin: 1rem 0; }}
        details.vm-section > summary {{
            cursor: pointer;
            font-size: 1.15em;
            font-weight: 600;
            padding: 0.4rem 0.5rem;
            border-left: 3px solid var(--border-color);
            background: var(--code-bg);
            border-radius: 0 4px 4px 0;
            user-select: none;
            margin-bottom: 0.5rem;
            list-style: none;
            display: flex;
            align-items: center;
            gap: 0.4em;
        }}
        details.vm-section > summary::-webkit-details-marker {{ display: none; }}
        details.vm-section > summary::before {{
            content: "\\25B6";
            font-size: 0.75em;
            transition: transform 0.15s ease;
            display: inline-block;
            color: var(--text-color);
            opacity: 0.5;
        }}
        details.vm-section[open] > summary::before {{
            transform: rotate(90deg);
        }}
        details.vm-section > summary:hover {{ border-left-color: #3b82f6; }}
        .count-badge {{
            display: inline-block;
            padding: 0.1em 0.55em;
            border-radius: 10px;
            background: var(--bg-color);
            color: var(--text-color);
            font-size: 0.78em;
            font-weight: 500;
            border: 1px solid var(--border-color);
            margin-left: auto;
        }}
        .flag-chip {{
            display: inline-block;
            padding: 0.1em 0.45em;
            margin-right: 0.25em;
            border-radius: 3px;
            font-size: 0.75em;
            font-weight: 500;
            background: var(--bg-color);
            color: var(--text-color);
            border: 1px solid var(--border-color);
        }}
        .flag-observable {{ background: #ede9fe; color: #5b21b6; border-color: #ddd6fe; }}
        .flag-optional   {{ background: #fef3c7; color: #92400e; border-color: #fde68a; }}
        .flag-readonly   {{ background: #e0e7ff; color: #3730a3; border-color: #c7d2fe; }}
        .section-intro   {{ color: #64748b; font-size: 0.9em; margin: 0.25rem 0 0.5rem; }}
        .layout-tree {{ background: #1e293b; color: #e2e8f0; padding: 1.5rem; }}
        .display-logic {{ background: #fef3c7; border-left: 4px solid #f59e0b; }}
        .notes {{ color: #64748b; font-style: italic; margin-top: 0.5rem; }}
        .http-method {{ padding: 0.2em 0.5em; border-radius: 4px; font-weight: 600; font-size: 0.85em; }}
        .method-get {{ background: #22c55e; color: white; }}
        .method-post {{ background: #3b82f6; color: white; }}
        .method-put {{ background: #f59e0b; color: white; }}
        .method-patch {{ background: #8b5cf6; color: white; }}
        .method-delete {{ background: #ef4444; color: white; }}
        .json {{ background: #1e293b; color: #e2e8f0; }}
        .mermaid {{ background: white; padding: 1rem; border: 1px solid var(--border-color); border-radius: 8px; margin: 1rem 0; }}
        ul {{ margin: 0.5rem 0; padding-left: 1.5rem; }}
        li {{ margin: 0.25rem 0; }}
        .custom-component-name {{ background: #fef3c7; color: #92400e; padding: 0.2em 0.5em; border-radius: 4px; font-weight: 600; font-size: 0.9em; }}
        .component-link {{ color: var(--primary-color); text-decoration: none; }}
        .component-link:hover {{ text-decoration: underline; }}
        .swatch {{ display: inline-flex; align-items: center; gap: 4px; white-space: nowrap; }}
        .swatch > i {{ display: inline-block; width: 12px; height: 12px; border-radius: 3px; border: 1px solid rgba(0,0,0,0.15); background-clip: padding-box; flex-shrink: 0; }}
        .swatch > code {{ background: var(--code-bg); padding: 0.1em 0.35em; font-size: 0.85em; }}
        .swatch-hex {{ color: #64748b; font-family: 'SF Mono', Monaco, monospace; font-size: 0.8em; }}
        .style-rows {{ display: flex; flex-direction: column; gap: 0.2rem; }}
        .style-row {{ display: flex; gap: 0.5rem; align-items: flex-start; line-height: 1.5; flex-wrap: wrap; }}
        .style-key {{ color: #64748b; font-weight: 600; font-size: 0.7rem; min-width: 56px; text-transform: uppercase; letter-spacing: 0.04em; padding-top: 0.15rem; flex-shrink: 0; }}
        .style-lbl {{ color: #94a3b8; font-size: 0.75rem; margin-right: 2px; }}
        .bind-cell {{ display: flex; flex-direction: column; gap: 3px; font-size: 0.8rem; line-height: 1.6; }}
        .bind-badge {{ display: inline-block; padding: 0 0.4em; border-radius: 3px; font-size: 0.7rem; font-weight: 700; letter-spacing: 0.03em; text-transform: uppercase; vertical-align: baseline; }}
        .bind-event {{ background: #fef3c7; color: #92400e; }}
        .bind-data {{ background: #dbeafe; color: #1e40af; }}
        .tree-table-header {{ display: flex; align-items: center; justify-content: space-between; gap: 1rem; margin: 1.5rem 0 0.5rem; }}
        .tree-table-header h3 {{ margin: 0; }}
        .tree-controls button {{ font: inherit; font-size: 0.8rem; padding: 0.25em 0.75em; margin-left: 0.4rem; border: 1px solid var(--border-color); background: white; color: var(--text-color); border-radius: 4px; cursor: pointer; }}
        .tree-controls button:hover {{ background: var(--bg-color); border-color: #94a3b8; }}
        .tree-col {{ white-space: nowrap; }}
        .tree-indent {{ display: inline-block; vertical-align: middle; }}
        .tree-toggle {{ display: inline-block; width: 16px; text-align: center; cursor: pointer; color: #64748b; font-size: 0.7em; transition: transform 0.15s ease; user-select: none; margin-right: 4px; }}
        .tree-toggle:hover {{ color: var(--primary-color); }}
        .tree-toggle.expanded {{ transform: rotate(90deg); }}
        .tree-spacer {{ display: inline-block; width: 16px; margin-right: 4px; }}
        tr.tree-group > td {{ background: #f8fafc; font-weight: 600; }}
        tr.tree-group .tree-group-name {{ color: var(--text-color); }}
        tr.tree-group .tree-group-count {{ display: inline-block; margin-left: 0.4rem; padding: 0.05em 0.5em; background: var(--border-color); color: #475569; border-radius: 10px; font-size: 0.75rem; font-weight: 600; }}
        {sidebar_styles}
    </style>
</head>
<body>
'''


def _get_html_footer(has_sidebar: bool = False) -> str:
    """Get HTML footer with Mermaid script."""
    toggle_script = ""
    if has_sidebar:
        toggle_script = '''
<script>
    function toggleSection(sectionId) {
        const title = document.getElementById(sectionId + '-title');
        const list = document.getElementById(sectionId + '-list');
        if (title && list) {
            title.classList.toggle('collapsed');
            list.classList.toggle('collapsed');
        }
    }
</script>
'''
    tree_script = '''
<script>
(function() {
  function initWrapper(wrapper) {
    const table = wrapper.querySelector('table.tree-table');
    if (!table) return;
    const expanded = new Set();
    const initialDepth = parseInt(wrapper.dataset.initialDepth || '2', 10);
    function rowById(id) { return table.querySelector('tr[data-row-id="' + id + '"]'); }
    function visible(tr) {
      let pid = tr.dataset.parentId;
      while (pid) {
        if (!expanded.has(pid)) return false;
        const p = rowById(pid);
        pid = p ? p.dataset.parentId : null;
      }
      return true;
    }
    function apply() {
      table.querySelectorAll('tr[data-parent-id]').forEach(tr => {
        tr.style.display = visible(tr) ? '' : 'none';
      });
    }
    function updateChevrons() {
      table.querySelectorAll('tr[data-has-children] .tree-toggle').forEach(t => {
        const id = t.closest('tr').dataset.rowId;
        t.classList.toggle('expanded', expanded.has(id));
      });
    }
    function expandAll() {
      table.querySelectorAll('tr[data-has-children]').forEach(tr => expanded.add(tr.dataset.rowId));
      apply(); updateChevrons();
    }
    function collapseAll() { expanded.clear(); apply(); updateChevrons(); }
    // Initial: expand rows whose depth is < initialDepth (row-id dashes < initialDepth)
    table.querySelectorAll('tr[data-has-children]').forEach(tr => {
      const depth = (tr.dataset.rowId.match(/-/g) || []).length;
      if (depth < initialDepth) expanded.add(tr.dataset.rowId);
    });
    table.querySelectorAll('tr[data-has-children] .tree-toggle').forEach(btn => {
      btn.addEventListener('click', e => {
        e.stopPropagation();
        const id = btn.closest('tr').dataset.rowId;
        if (expanded.has(id)) expanded.delete(id); else expanded.add(id);
        apply(); updateChevrons();
      });
    });
    wrapper.querySelectorAll('.tree-expand-all').forEach(b => b.addEventListener('click', expandAll));
    wrapper.querySelectorAll('.tree-collapse-all').forEach(b => b.addEventListener('click', collapseAll));
    apply(); updateChevrons();
  }
  function init() {
    document.querySelectorAll('.tree-wrapper').forEach(initWrapper);
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
</script>
'''
    return f'''
<script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
<script>
    mermaid.initialize({{ startOnLoad: true, theme: 'default' }});
</script>
{toggle_script}
{tree_script}
</body>
</html>
'''


def generate_component_html(
    spec_data: dict,
    all_tests_nav: dict | None = None,
    current_path: str | None = None
) -> str:
    """
    Generate HTML documentation for a component specification.

    Args:
        spec_data: Parsed component specification JSON data
        all_tests_nav: Navigation data for sidebar (if provided, adds sidebar)
        current_path: Current page's relative path (for highlighting in sidebar)

    Returns:
        Generated HTML string
    """
    metadata = spec_data.get("metadata", {})
    name = metadata.get("name", "Component")
    display_name = metadata.get("displayName", name)
    description = metadata.get("description", "")
    category = metadata.get("category", "other")

    props = spec_data.get("props", {}).get("items", [])
    slots = spec_data.get("slots", {}).get("items", [])
    structure = spec_data.get("structure", {})
    state_mgmt = spec_data.get("stateManagement", {})
    usage = spec_data.get("usage", {})

    has_sidebar = all_tests_nav is not None
    page_title = f"{display_name} - Component Specification"

    parts = []

    # HTML header with shared styles
    parts.append(_get_html_header(page_title, has_sidebar))

    # Additional component-specific styles
    parts.append('''<style>
        .badge { display: inline-block; padding: 4px 12px; border-radius: 4px; font-size: 12px; font-weight: bold; margin-left: 10px; }
        .badge-category { background: #e3f2fd; color: #1976d2; }
        .badge-required { background: #ffebee; color: #c62828; }
        .badge-optional { background: #e8f5e9; color: #2e7d32; }
        .badge-non-lazy { background: #fff3e0; color: #e65100; }
        .type { font-family: monospace; color: #7c4dff; }
        .default { font-family: monospace; color: #ff9800; }
    </style>''')

    # Sidebar (if navigation data provided)
    if has_sidebar:
        from ..test_doc.html.sidebar import generate_spec_sidebar
        parts.append('<div class="layout-with-sidebar">')
        sidebar_parts = generate_spec_sidebar(display_name, all_tests_nav, current_path)
        parts.extend(sidebar_parts)
        parts.append('<main class="main-content">')

    # Main content
    parts.append('<div class="container">')
    parts.append(f'<h1>{_e(display_name)} <span class="badge badge-category">{_e(category)}</span></h1>')
    parts.append(f'<p>{_e(description)}</p>')

    # Props section
    if props:
        parts.append('<section id="props">')
        parts.append('<h2>Props</h2>')
        parts.append('<table>')
        parts.append('<thead><tr><th>Name</th><th>Type</th><th>Required</th><th>Default</th><th>Description</th></tr></thead>')
        parts.append('<tbody>')
        for prop in props:
            required = prop.get("required", True)
            badge = '<span class="badge badge-required">Required</span>' if required else '<span class="badge badge-optional">Optional</span>'
            default_val = prop.get("default", "-")
            if default_val is None:
                default_val = "null"
            parts.append(f'<tr><td><code>{_e(str(prop.get("name", "")))}</code></td>')
            parts.append(f'<td class="type">{_e(str(prop.get("type", "")))}</td>')
            parts.append(f'<td>{badge}</td>')
            parts.append(f'<td class="default">{_e(str(default_val))}</td>')
            parts.append(f'<td>{_e(str(prop.get("description", "")))}</td></tr>')
        parts.append('</tbody></table>')
        parts.append('</section>')

    # Slots section
    if slots:
        parts.append('<section id="slots">')
        parts.append('<h2>Slots</h2>')
        parts.append('<table>')
        parts.append('<thead><tr><th>Name</th><th>Required</th><th>Description</th></tr></thead>')
        parts.append('<tbody>')
        for slot in slots:
            required = slot.get("required", False)
            badge = '<span class="badge badge-required">Required</span>' if required else '<span class="badge badge-optional">Optional</span>'
            parts.append(f'<tr><td><code>{_e(str(slot.get("name", "")))}</code></td>')
            parts.append(f'<td>{badge}</td>')
            parts.append(f'<td>{_e(str(slot.get("description", "")))}</td></tr>')
        parts.append('</tbody></table>')
        parts.append('</section>')

    # Structure section
    components = structure.get("components", [])
    if components:
        parts.append('<section id="structure">')
        parts.append('<h2>Structure</h2>')
        parts.append('<h3>Components</h3>')
        parts.append('<table>')
        parts.append('<thead><tr><th>Type</th><th>ID</th><th>Description</th></tr></thead>')
        parts.append('<tbody>')
        for comp in components:
            parts.append(f'<tr><td><code>{_e(str(comp.get("type", "")))}</code></td>')
            parts.append(f'<td><code>{_e(str(comp.get("id", "")))}</code></td>')
            parts.append(f'<td>{_e(str(comp.get("description", "")))}</td></tr>')
        parts.append('</tbody></table>')
        parts.append('</section>')

    # State Management section
    internal_states = state_mgmt.get("internalStates", [])
    exposed_events = state_mgmt.get("exposedEvents", [])

    if internal_states or exposed_events:
        parts.append('<section id="state-management">')
        parts.append('<h2>State Management</h2>')

        if internal_states:
            parts.append('<h3>Internal States</h3>')
            parts.append('<table>')
            parts.append('<thead><tr><th>Name</th><th>Type</th><th>Initial Value</th><th>Description</th></tr></thead>')
            parts.append('<tbody>')
            for state in internal_states:
                initial = state.get("initialValue", "-")
                if initial is None:
                    initial = "null"
                parts.append(f'<tr><td><code>{_e(str(state.get("name", "")))}</code></td>')
                parts.append(f'<td class="type">{_e(str(state.get("type", "")))}</td>')
                parts.append(f'<td class="default">{_e(str(initial))}</td>')
                parts.append(f'<td>{_e(str(state.get("description", "")))}</td></tr>')
            parts.append('</tbody></table>')

        if exposed_events:
            parts.append('<h3>Exposed Events</h3>')
            parts.append('<table>')
            parts.append('<thead><tr><th>Name</th><th>Parameters</th><th>Description</th></tr></thead>')
            parts.append('<tbody>')
            for event in exposed_events:
                params = event.get("parameters", [])
                param_str = ", ".join([f"{p.get('name', '')}: {p.get('type', '')}" for p in params]) if params else "-"
                parts.append(f'<tr><td><code>{_e(str(event.get("name", "")))}</code></td>')
                parts.append(f'<td class="type">{_e(param_str)}</td>')
                parts.append(f'<td>{_e(str(event.get("description", "")))}</td></tr>')
            parts.append('</tbody></table>')

        parts.append('</section>')

    # Usage section
    example = usage.get("example")
    used_in_screens = usage.get("usedInScreens", [])

    if example or used_in_screens:
        parts.append('<section id="usage">')
        parts.append('<h2>Usage</h2>')

        if example:
            parts.append('<h3>Example</h3>')
            parts.append(f'<pre><code>{_e(example)}</code></pre>')

        if used_in_screens:
            parts.append('<h3>Used In Screens</h3>')
            parts.append('<ul>')
            for screen in used_in_screens:
                parts.append(f'<li>{_e(screen)}</li>')
            parts.append('</ul>')

        parts.append('</section>')

    parts.append('</div>')  # container

    # Close sidebar layout if present
    if has_sidebar:
        parts.append('</main>')  # main-content
        parts.append('</div>')  # layout-with-sidebar

    # Footer
    parts.append(_get_html_footer(has_sidebar))

    return "\n".join(parts)


def generate_component_markdown(spec_data: dict) -> str:
    """Generate Markdown documentation for a component specification."""
    metadata = spec_data.get("metadata", {})
    name = metadata.get("name", "Component")
    display_name = metadata.get("displayName", name)
    description = metadata.get("description", "")
    category = metadata.get("category", "other")

    props = spec_data.get("props", {}).get("items", [])
    slots = spec_data.get("slots", {}).get("items", [])
    structure = spec_data.get("structure", {})
    state_mgmt = spec_data.get("stateManagement", {})
    usage = spec_data.get("usage", {})

    md = f"# {display_name}\n\n"
    md += f"**Category:** {category}\n\n"
    md += f"{description}\n\n"

    # Props
    if props:
        md += "## Props\n\n"
        md += "| Name | Type | Required | Default | Description |\n"
        md += "|------|------|----------|---------|-------------|\n"
        for prop in props:
            required = "Yes" if prop.get("required", True) else "No"
            default_val = prop.get("default", "-")
            if default_val is None:
                default_val = "null"
            md += f"| `{prop.get('name', '')}` | `{prop.get('type', '')}` | {required} | `{default_val}` | {prop.get('description', '')} |\n"
        md += "\n"

    # Slots
    if slots:
        md += "## Slots\n\n"
        md += "| Name | Required | Description |\n"
        md += "|------|----------|-------------|\n"
        for slot in slots:
            required = "Yes" if slot.get("required", False) else "No"
            md += f"| `{slot.get('name', '')}` | {required} | {slot.get('description', '')} |\n"
        md += "\n"

    # Structure
    components = structure.get("components", [])
    if components:
        md += "## Structure\n\n"
        md += "### Components\n\n"
        md += "| Type | ID | Description |\n"
        md += "|------|----|--------------|\n"
        for comp in components:
            md += f"| `{comp.get('type', '')}` | `{comp.get('id', '')}` | {comp.get('description', '')} |\n"
        md += "\n"

    # State Management
    internal_states = state_mgmt.get("internalStates", [])
    exposed_events = state_mgmt.get("exposedEvents", [])

    if internal_states or exposed_events:
        md += "## State Management\n\n"

        if internal_states:
            md += "### Internal States\n\n"
            md += "| Name | Type | Initial Value | Description |\n"
            md += "|------|------|---------------|-------------|\n"
            for state in internal_states:
                initial = state.get("initialValue", "-")
                if initial is None:
                    initial = "null"
                md += f"| `{state.get('name', '')}` | `{state.get('type', '')}` | `{initial}` | {state.get('description', '')} |\n"
            md += "\n"

        if exposed_events:
            md += "### Exposed Events\n\n"
            md += "| Name | Parameters | Description |\n"
            md += "|------|------------|-------------|\n"
            for event in exposed_events:
                params = event.get("parameters", [])
                param_str = ", ".join([f"{p.get('name', '')}: {p.get('type', '')}" for p in params]) if params else "-"
                md += f"| `{event.get('name', '')}` | `{param_str}` | {event.get('description', '')} |\n"
            md += "\n"

    # Usage
    example = usage.get("example")
    used_in_screens = usage.get("usedInScreens", [])

    if example or used_in_screens:
        md += "## Usage\n\n"

        if example:
            md += "### Example\n\n"
            md += f"```json\n{example}\n```\n\n"

        if used_in_screens:
            md += "### Used In Screens\n\n"
            for screen in used_in_screens:
                md += f"- {screen}\n"
            md += "\n"

    return md
