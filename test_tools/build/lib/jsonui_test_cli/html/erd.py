"""ER Diagram HTML generation from OpenAPI schema files."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .sidebar import escape_html


def generate_erd_html(
    schema_files: list[dict],
    title: str = "ER Diagram",
    current_doc_path: str = "db/erd.html",
    category_docs: list[dict] | None = None
) -> str:
    """
    Generate HTML page with Mermaid ER diagram from schema files.

    Args:
        schema_files: List of schema file dicts with 'name', 'swagger_data', 'path'
        title: Page title
        current_doc_path: Current document path for navigation
        category_docs: List of docs in the same category for sidebar

    Returns:
        Complete HTML string with ER diagram
    """
    # Build grouped Mermaid diagrams
    groups = _build_grouped_erds(schema_files)
    all_mermaid_code = _build_mermaid_erd(schema_files)

    html_parts = _get_html_header(title)

    rel_root = _get_relative_root(current_doc_path)

    # Sidebar
    html_parts.extend(_generate_sidebar(category_docs, current_doc_path, rel_root))

    # Main content
    html_parts.extend([
        "  <main class='main-content'>",
        f"    <h1>{escape_html(title)}</h1>",
        "    <p class='description'>Database table relationships visualized from schema definitions.</p>",
    ])

    # Tabs
    html_parts.extend([
        "    <div class='tabs'>",
        "      <button class='tab-btn active' onclick=\"switchTab('all')\">All Tables</button>",
    ])
    for group_name in groups.keys():
        display_name = group_name.replace('_', ' ').title()
        html_parts.append(f"      <button class='tab-btn' onclick=\"switchTab('{escape_html(group_name)}')\">{escape_html(display_name)}</button>")
    html_parts.append("    </div>")

    # Zoom controls
    html_parts.extend([
        "    <div class='zoom-controls'>",
        "      <button onclick='zoomOut()' title='Zoom Out'>−</button>",
        "      <span id='zoom-level'>100%</span>",
        "      <button onclick='zoomIn()' title='Zoom In'>+</button>",
        "      <button onclick='resetZoom()' title='Reset'>Reset</button>",
        "      <button onclick='fitToScreen()' title='Fit to Screen'>Fit</button>",
        "    </div>",
    ])

    # All tables diagram
    html_parts.extend([
        "    <div class='tab-content active' id='tab-all'>",
        "      <div class='diagram-wrapper' id='diagram-wrapper-all'>",
        "        <div class='diagram-container' id='diagram-container-all'>",
        "          <pre class='mermaid'>",
        all_mermaid_code,
        "          </pre>",
        "        </div>",
        "      </div>",
        "    </div>",
    ])

    # Group diagrams
    for group_name, mermaid_code in groups.items():
        safe_name = escape_html(group_name)
        html_parts.extend([
            f"    <div class='tab-content' id='tab-{safe_name}'>",
            f"      <div class='diagram-wrapper' id='diagram-wrapper-{safe_name}'>",
            f"        <div class='diagram-container' id='diagram-container-{safe_name}'>",
            "          <pre class='mermaid'>",
            mermaid_code,
            "          </pre>",
            "        </div>",
            "      </div>",
            "    </div>",
        ])

    # Legend
    html_parts.extend([
        "    <div class='legend'>",
        "      <h3>Legend</h3>",
        "      <ul>",
        "        <li><strong>PK</strong> - Primary Key</li>",
        "        <li><strong>FK</strong> - Foreign Key</li>",
        "        <li><strong>UK</strong> - Unique Key</li>",
        "        <li><code>||--o{</code> - One to Many relationship</li>",
        "        <li><code>||--||</code> - One to One relationship</li>",
        "      </ul>",
        "    </div>",
        "  </main>",
    ])

    # Scripts
    html_parts.extend([
        "  <script src='https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js'></script>",
        "  <script>",
        "    let currentZoom = {};",
        "    let activeTab = 'all';",
        "    let renderedTabs = new Set();",
        "    const minZoom = 0.25;",
        "    const maxZoom = 3;",
        "    const zoomStep = 0.25;",
        "",
        "    mermaid.initialize({",
        "      startOnLoad: false,",
        "      theme: 'default',",
        "      er: {",
        "        useMaxWidth: false,",
        "        layoutDirection: 'TB'",
        "      }",
        "    });",
        "",
        "    async function renderTab(tabName) {",
        "      if (renderedTabs.has(tabName)) return;",
        "      const container = document.getElementById('diagram-container-' + tabName);",
        "      if (!container) return;",
        "      const pre = container.querySelector('pre.mermaid');",
        "      if (!pre || pre.dataset.processed) return;",
        "      try {",
        "        const code = pre.textContent;",
        "        const { svg } = await mermaid.render('mermaid-' + tabName, code);",
        "        pre.innerHTML = svg;",
        "        pre.dataset.processed = 'true';",
        "        renderedTabs.add(tabName);",
        "      } catch (e) {",
        "        console.error('Mermaid render error:', e);",
        "      }",
        "    }",
        "",
        "    function getZoom() {",
        "      if (!currentZoom[activeTab]) currentZoom[activeTab] = 1;",
        "      return currentZoom[activeTab];",
        "    }",
        "",
        "    function setZoom(val) {",
        "      currentZoom[activeTab] = val;",
        "    }",
        "",
        "    function updateZoom() {",
        "      const container = document.getElementById('diagram-container-' + activeTab);",
        "      if (container) {",
        "        container.style.transform = `scale(${getZoom()})`;",
        "      }",
        "      document.getElementById('zoom-level').textContent = Math.round(getZoom() * 100) + '%';",
        "    }",
        "",
        "    function zoomIn() {",
        "      if (getZoom() < maxZoom) {",
        "        setZoom(Math.min(maxZoom, getZoom() + zoomStep));",
        "        updateZoom();",
        "      }",
        "    }",
        "",
        "    function zoomOut() {",
        "      if (getZoom() > minZoom) {",
        "        setZoom(Math.max(minZoom, getZoom() - zoomStep));",
        "        updateZoom();",
        "      }",
        "    }",
        "",
        "    function resetZoom() {",
        "      setZoom(1);",
        "      updateZoom();",
        "    }",
        "",
        "    function fitToScreen() {",
        "      const wrapper = document.getElementById('diagram-wrapper-' + activeTab);",
        "      const container = document.getElementById('diagram-container-' + activeTab);",
        "      if (!wrapper || !container) return;",
        "      const svg = container.querySelector('svg');",
        "      if (svg) {",
        "        const wrapperWidth = wrapper.clientWidth - 40;",
        "        const wrapperHeight = wrapper.clientHeight - 40;",
        "        const svgWidth = svg.getBoundingClientRect().width / getZoom();",
        "        const svgHeight = svg.getBoundingClientRect().height / getZoom();",
        "        const scaleX = wrapperWidth / svgWidth;",
        "        const scaleY = wrapperHeight / svgHeight;",
        "        let newZoom = Math.min(scaleX, scaleY, maxZoom);",
        "        newZoom = Math.max(newZoom, minZoom);",
        "        setZoom(newZoom);",
        "        updateZoom();",
        "      }",
        "    }",
        "",
        "    async function switchTab(tabName) {",
        "      // Update buttons",
        "      document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));",
        "      event.target.classList.add('active');",
        "",
        "      // Update content",
        "      document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));",
        "      const tabContent = document.getElementById('tab-' + tabName);",
        "      if (tabContent) tabContent.classList.add('active');",
        "",
        "      activeTab = tabName;",
        "",
        "      // Render diagram if not yet rendered",
        "      await renderTab(tabName);",
        "      updateZoom();",
        "    }",
        "",
        "    // Mouse wheel zoom for active tab",
        "    document.querySelectorAll('.diagram-wrapper').forEach(wrapper => {",
        "      wrapper.addEventListener('wheel', function(e) {",
        "        if (e.ctrlKey || e.metaKey) {",
        "          e.preventDefault();",
        "          if (e.deltaY < 0) {",
        "            zoomIn();",
        "          } else {",
        "            zoomOut();",
        "          }",
        "        }",
        "      }, { passive: false });",
        "    });",
        "",
        "    // Render initial tab on page load",
        "    document.addEventListener('DOMContentLoaded', () => renderTab('all'));",
        "  </script>",
        "</body>",
        "</html>",
    ])

    return '\n'.join(html_parts)


def _build_grouped_erds(schema_files: list[dict]) -> dict[str, str]:
    """
    Build grouped ER diagrams based on x-erd-group and x-erd-main attributes.

    Each table can specify:
    - x-erd-group: Group name for the tab (e.g., "user", "notification")
    - x-erd-main: Boolean, if true this table is the main/center table of the group

    Tables with the same x-erd-group value are grouped together.
    The x-erd-main table is rendered first in the diagram (appears at top).

    Args:
        schema_files: List of schema file dicts

    Returns:
        Dict of group_name -> mermaid_code
    """
    # Extract all tables with their group info
    tables_by_group: dict[str, list[dict]] = {}  # group_name -> [schema_files]
    main_tables: dict[str, str] = {}  # group_name -> main_table_name

    for schema_file in schema_files:
        swagger_data = schema_file.get('swagger_data', {})
        if not swagger_data:
            continue

        info = swagger_data.get('info', {})
        table_name = info.get('x-table-name', '')
        erd_group = info.get('x-erd-group', '')
        erd_main = info.get('x-erd-main', False)

        if not table_name:
            schemas = swagger_data.get('components', {}).get('schemas', {})
            for schema_name, schema_def in schemas.items():
                if schema_def.get('type') == 'string' and 'enum' in schema_def:
                    continue
                table_name = _to_snake_case(schema_name)
                break

        if not table_name:
            continue

        # Only process tables with explicit x-erd-group
        if erd_group:
            if erd_group not in tables_by_group:
                tables_by_group[erd_group] = []
            tables_by_group[erd_group].append(schema_file)

            if erd_main:
                main_tables[erd_group] = table_name

    # Build mermaid code for each group
    result = {}
    for group_name, group_files in tables_by_group.items():
        if not group_files:
            continue

        # Sort files so main table comes first
        main_table = main_tables.get(group_name)
        if main_table:
            # Sort: main table first, then others
            def sort_key(sf: dict) -> int:
                info = sf.get('swagger_data', {}).get('info', {})
                tbl = info.get('x-table-name', '')
                return 0 if tbl == main_table else 1
            group_files = sorted(group_files, key=sort_key)

        result[group_name] = _build_mermaid_erd(group_files, main_table)

    return result


def _build_mermaid_erd(schema_files: list[dict], main_table: str | None = None) -> str:
    """
    Build Mermaid ER diagram code from schema files.

    Args:
        schema_files: List of schema file dicts
        main_table: Optional main table name to be rendered first (center of diagram)

    Returns:
        Mermaid erDiagram code
    """
    lines = ["erDiagram"]

    # Collect all tables and relationships
    tables: dict[str, dict] = {}  # table_name -> {fields, pk, fks}
    relationships: list[tuple[str, str, str, str]] = []  # (from_table, to_table, rel_type, label)

    for schema_file in schema_files:
        swagger_data = schema_file.get('swagger_data', {})
        if not swagger_data:
            continue

        info = swagger_data.get('info', {})
        table_name = info.get('x-table-name', '')

        if not table_name:
            # Try to extract from schema name
            schemas = swagger_data.get('components', {}).get('schemas', {})
            for schema_name, schema_def in schemas.items():
                # Skip enum schemas
                if schema_def.get('type') == 'string' and 'enum' in schema_def:
                    continue
                # Use first non-enum schema name as table name (snake_case)
                table_name = _to_snake_case(schema_name)
                break

        if not table_name:
            continue

        schemas = swagger_data.get('components', {}).get('schemas', {})

        for schema_name, schema_def in schemas.items():
            # Skip enum schemas
            if schema_def.get('type') == 'string' and 'enum' in schema_def:
                continue

            properties = schema_def.get('properties', {})
            required_fields = schema_def.get('required', [])

            fields = []
            pk_field = None
            fk_relations = []

            for prop_name, prop_def in properties.items():
                prop_type = prop_def.get('type', 'string')
                mermaid_type = _map_type_to_mermaid(prop_type, prop_def.get('format', ''))

                # Check for keys
                key_markers = []
                if prop_def.get('x-primary-key'):
                    key_markers.append('PK')
                    pk_field = prop_name
                if prop_def.get('x-unique'):
                    key_markers.append('UK')
                if prop_def.get('x-foreign-key'):
                    key_markers.append('FK')
                    # Extract FK reference
                    fk = prop_def['x-foreign-key']
                    if isinstance(fk, dict):
                        ref_table = fk.get('table', '')
                        ref_column = fk.get('column', 'id')
                    else:
                        # String format: "table.column"
                        parts = str(fk).split('.')
                        ref_table = parts[0] if parts else ''
                        ref_column = parts[1] if len(parts) > 1 else 'id'

                    if ref_table:
                        fk_relations.append((ref_table, prop_name))

                key_str = ','.join(key_markers) if key_markers else ''
                comment = f'"{prop_def.get("description", "")}"' if prop_def.get('description') else ''

                fields.append({
                    'name': prop_name,
                    'type': mermaid_type,
                    'key': key_str,
                    'comment': comment
                })

            tables[table_name] = {
                'fields': fields,
                'pk': pk_field,
                'fks': fk_relations
            }

            # Add relationships
            for ref_table, fk_field in fk_relations:
                relationships.append((ref_table, table_name, '||--o{', fk_field))

    # Generate Mermaid code for tables (main table first if specified)
    table_names = list(tables.keys())
    if main_table and main_table in table_names:
        # Move main table to front
        table_names.remove(main_table)
        table_names.insert(0, main_table)

    for table_name in table_names:
        table_info = tables[table_name]
        # Sanitize table name for Mermaid (replace special chars)
        safe_table_name = _sanitize_mermaid_name(table_name)
        lines.append(f"    {safe_table_name} {{")
        for field in table_info['fields']:
            field_line = f"        {field['type']} {field['name']}"
            if field['key']:
                field_line += f" {field['key']}"
            lines.append(field_line)
        lines.append("    }")

    # Generate relationships
    for from_table, to_table, rel_type, label in relationships:
        safe_from = _sanitize_mermaid_name(from_table)
        safe_to = _sanitize_mermaid_name(to_table)
        # Check if from_table exists in our tables
        if from_table in tables:
            lines.append(f"    {safe_from} {rel_type} {safe_to} : \"{label}\"")
        else:
            # External reference - still show relationship but table won't have fields
            lines.append(f"    {safe_from} {rel_type} {safe_to} : \"{label}\"")

    return '\n'.join(lines)


def _to_snake_case(name: str) -> str:
    """Convert CamelCase to snake_case."""
    import re
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()


def _sanitize_mermaid_name(name: str) -> str:
    """Sanitize name for Mermaid diagram (remove special characters)."""
    # Replace non-alphanumeric chars with underscore
    import re
    return re.sub(r'[^a-zA-Z0-9_]', '_', name)


def _map_type_to_mermaid(json_type: str, format: str = '') -> str:
    """Map JSON Schema type to Mermaid ER diagram type."""
    type_mapping = {
        'integer': 'int',
        'number': 'float',
        'string': 'string',
        'boolean': 'bool',
        'array': 'array',
        'object': 'json',
    }

    base_type = type_mapping.get(json_type, 'string')

    # Handle specific formats
    if format == 'date-time':
        return 'datetime'
    elif format == 'date':
        return 'date'
    elif format == 'uuid':
        return 'uuid'
    elif format == 'email':
        return 'string'

    return base_type


def _get_relative_root(doc_path: str) -> str:
    """Calculate relative path to root from document path."""
    depth = len(Path(doc_path).parent.parts)
    if depth == 0:
        return "./"
    return "../" * depth


def _generate_sidebar(
    category_docs: list[dict] | None,
    current_doc_path: str | None,
    rel_root: str
) -> list[str]:
    """Generate sidebar with navigation links."""
    parts = [
        "  <aside class='sidebar'>",
        "    <div class='sidebar-header'>",
        f"      <a href='{rel_root}index.html' class='sidebar-title'>&larr; Back to Index</a>",
        "    </div>",
        "    <nav class='sidebar-nav'>",
        "      <div class='nav-section'>",
        "        <div class='nav-section-title'>ER Diagram</div>",
        "        <ul class='nav-list'>",
        "          <li class='active'><a href='erd.html'>ER Diagram</a></li>",
        "        </ul>",
        "      </div>",
    ]

    if category_docs:
        parts.extend([
            "      <div class='nav-section'>",
            "        <div class='nav-section-title'>Tables</div>",
            "        <ul class='nav-list'>",
        ])
        for doc in category_docs:
            doc_name = doc.get('name', '')
            doc_path = doc.get('path', '')
            doc_filename = Path(doc_path).name if doc_path else ''
            parts.append(f"          <li><a href='{doc_filename}'>{escape_html(doc_name)}</a></li>")
        parts.extend([
            "        </ul>",
            "      </div>",
        ])

    parts.extend([
        "    </nav>",
        "  </aside>",
    ])
    return parts


def _get_html_header(title: str) -> list[str]:
    """Generate HTML header with styles for ER diagram page."""
    parts = [
        "<!DOCTYPE html>",
        "<html lang='ja'>",
        "<head>",
        "  <meta charset='UTF-8'>",
        "  <meta name='viewport' content='width=device-width, initial-scale=1.0'>",
        f"  <title>{escape_html(title)}</title>",
        "  <style>",
        "    * { margin: 0; padding: 0; box-sizing: border-box; }",
        "    body {",
        "      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', sans-serif;",
        "      background: #f5f5f5;",
        "      color: #333;",
        "      line-height: 1.6;",
        "      display: flex;",
        "    }",
        "    .sidebar {",
        "      width: 280px;",
        "      min-width: 280px;",
        "      height: 100vh;",
        "      position: fixed;",
        "      top: 0;",
        "      left: 0;",
        "      background: #f8f9fa;",
        "      border-right: 1px solid #e0e0e0;",
        "      overflow-y: auto;",
        "      padding: 20px;",
        "    }",
        "    .sidebar-header {",
        "      padding-bottom: 15px;",
        "      margin-bottom: 15px;",
        "      border-bottom: 1px solid #e0e0e0;",
        "    }",
        "    .sidebar-title {",
        "      color: #007AFF;",
        "      text-decoration: none;",
        "      font-size: 0.9em;",
        "    }",
        "    .sidebar-title:hover {",
        "      text-decoration: underline;",
        "    }",
        "    .sidebar-nav {",
        "      padding: 0;",
        "    }",
        "    .nav-section {",
        "      margin-bottom: 20px;",
        "    }",
        "    .nav-section-title {",
        "      font-size: 0.75em;",
        "      font-weight: 600;",
        "      color: #888;",
        "      text-transform: uppercase;",
        "      letter-spacing: 0.5px;",
        "      margin-bottom: 8px;",
        "    }",
        "    .nav-list {",
        "      list-style: none;",
        "    }",
        "    .nav-list li {",
        "      margin: 2px 0;",
        "    }",
        "    .nav-list li.active a {",
        "      background: #007AFF;",
        "      color: white;",
        "    }",
        "    .nav-list li a {",
        "      display: block;",
        "      padding: 6px 12px;",
        "      color: #555;",
        "      text-decoration: none;",
        "      border-radius: 4px;",
        "      font-size: 0.85em;",
        "    }",
        "    .nav-list li a:hover {",
        "      background: #e9ecef;",
        "      color: #007AFF;",
        "    }",
        "    .main-content {",
        "      margin-left: 280px;",
        "      flex: 1;",
        "      padding: 30px 40px;",
        "      min-width: 0;",
        "    }",
        "    h1 {",
        "      color: #333;",
        "      border-bottom: 2px solid #007AFF;",
        "      padding-bottom: 10px;",
        "      margin-top: 0;",
        "      margin-bottom: 10px;",
        "    }",
        "    .description {",
        "      color: #666;",
        "      margin-bottom: 20px;",
        "    }",
        "    .tabs {",
        "      display: flex;",
        "      flex-wrap: wrap;",
        "      gap: 8px;",
        "      margin-bottom: 15px;",
        "      padding: 10px;",
        "      background: #f8f9fa;",
        "      border-radius: 8px;",
        "      border: 1px solid #e0e0e0;",
        "    }",
        "    .tab-btn {",
        "      padding: 10px 20px;",
        "      border: 1px solid #ddd;",
        "      background: white;",
        "      border-radius: 6px;",
        "      cursor: pointer;",
        "      font-size: 14px;",
        "      font-weight: 500;",
        "      transition: all 0.2s;",
        "      color: #555;",
        "    }",
        "    .tab-btn:hover {",
        "      background: #e9ecef;",
        "      border-color: #007AFF;",
        "      color: #007AFF;",
        "    }",
        "    .tab-btn.active {",
        "      background: #007AFF;",
        "      color: white;",
        "      border-color: #007AFF;",
        "    }",
        "    .tab-content {",
        "      display: none;",
        "    }",
        "    .tab-content.active {",
        "      display: block;",
        "    }",
        "    .zoom-controls {",
        "      display: flex;",
        "      align-items: center;",
        "      gap: 10px;",
        "      margin-bottom: 15px;",
        "      padding: 10px 15px;",
        "      background: #f8f9fa;",
        "      border-radius: 8px;",
        "      border: 1px solid #e0e0e0;",
        "    }",
        "    .zoom-controls button {",
        "      padding: 8px 16px;",
        "      border: 1px solid #ddd;",
        "      background: white;",
        "      border-radius: 4px;",
        "      cursor: pointer;",
        "      font-size: 14px;",
        "      font-weight: 500;",
        "      transition: all 0.2s;",
        "    }",
        "    .zoom-controls button:hover {",
        "      background: #007AFF;",
        "      color: white;",
        "      border-color: #007AFF;",
        "    }",
        "    .zoom-controls button:active {",
        "      transform: scale(0.95);",
        "    }",
        "    #zoom-level {",
        "      min-width: 50px;",
        "      text-align: center;",
        "      font-weight: 600;",
        "      color: #333;",
        "    }",
        "    .diagram-wrapper {",
        "      background: white;",
        "      border-radius: 8px;",
        "      margin-bottom: 30px;",
        "      box-shadow: 0 2px 4px rgba(0,0,0,0.1);",
        "      overflow: auto;",
        "      height: 600px;",
        "      position: relative;",
        "      cursor: grab;",
        "    }",
        "    .diagram-wrapper:active {",
        "      cursor: grabbing;",
        "    }",
        "    .diagram-container {",
        "      padding: 30px;",
        "      transform-origin: top left;",
        "      transition: transform 0.1s ease-out;",
        "      display: inline-block;",
        "      min-width: 100%;",
        "    }",
        "    .mermaid {",
        "      text-align: center;",
        "    }",
        "    .mermaid svg {",
        "      max-width: none !important;",
        "    }",
        "    .legend {",
        "      background: #f8f9fa;",
        "      border-radius: 8px;",
        "      padding: 20px;",
        "      border: 1px solid #e0e0e0;",
        "    }",
        "    .legend h3 {",
        "      font-size: 14px;",
        "      color: #666;",
        "      margin-bottom: 10px;",
        "    }",
        "    .legend ul {",
        "      list-style: none;",
        "      display: flex;",
        "      flex-wrap: wrap;",
        "      gap: 20px;",
        "    }",
        "    .legend li {",
        "      font-size: 13px;",
        "      color: #555;",
        "    }",
        "    .legend code {",
        "      background: #e9ecef;",
        "      padding: 2px 6px;",
        "      border-radius: 3px;",
        "      font-family: 'SF Mono', Monaco, Consolas, monospace;",
        "      font-size: 12px;",
        "    }",
        "    /* Responsive */",
        "    @media (max-width: 768px) {",
        "      .sidebar { display: none; }",
        "      .main-content { margin-left: 0; padding: 20px; }",
        "      .legend ul { flex-direction: column; gap: 8px; }",
        "    }",
        "  </style>",
        "</head>",
        "<body>",
    ]
    return parts
