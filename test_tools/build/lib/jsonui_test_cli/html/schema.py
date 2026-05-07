"""Schema-only documentation page HTML generation for OpenAPI files without paths."""

from __future__ import annotations

import json
from pathlib import Path

from .sidebar import escape_html


def has_api_paths(swagger_data: dict) -> bool:
    """
    Check if Swagger/OpenAPI data has actual API paths.

    Args:
        swagger_data: Parsed Swagger/OpenAPI data

    Returns:
        True if the file has API paths, False if schema-only
    """
    paths = swagger_data.get('paths', {})
    return bool(paths)


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
        "          <li><a href='erd.html'>ER Diagram</a></li>",
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
            # Get just the filename for comparison
            current_filename = Path(current_doc_path).name if current_doc_path else ''
            doc_filename = Path(doc_path).name if doc_path else ''
            is_current = current_filename == doc_filename
            active_class = " class='active'" if is_current else ""
            # Use just filename since we're in the same directory
            parts.append(f"          <li{active_class}><a href='{doc_filename}'>{escape_html(doc_name)}</a></li>")
        parts.extend([
            "        </ul>",
            "      </div>",
        ])

    parts.extend([
        "    </nav>",
        "  </aside>",
    ])
    return parts


def generate_schema_html(
    swagger_data: dict,
    title: str | None = None,
    current_doc_path: str | None = None,
    category_docs: list[dict] | None = None
) -> str:
    """
    Generate HTML documentation page for schema-only OpenAPI files.

    Args:
        swagger_data: Parsed Swagger/OpenAPI data
        title: Optional title override
        current_doc_path: Current document's relative path
        category_docs: List of docs in the same category for sidebar navigation

    Returns:
        Complete HTML string with schema documentation
    """
    info = swagger_data.get('info', {})
    doc_title = title or info.get('title', 'Schema Documentation')
    doc_description = info.get('description', '')
    table_name = info.get('x-table-name', '')

    schemas = swagger_data.get('components', {}).get('schemas', {})

    html_parts = _get_html_header(doc_title)

    rel_root = _get_relative_root(current_doc_path) if current_doc_path else "../"

    # Sidebar
    html_parts.extend(_generate_sidebar(category_docs, current_doc_path, rel_root))

    # Main content
    html_parts.extend([
        "  <main class='main-content'>",
        f"    <h1>{escape_html(doc_title)}</h1>",
    ])

    if table_name:
        html_parts.append(f"    <p class='table-name'>Table: <code>{escape_html(table_name)}</code></p>")

    if doc_description:
        html_parts.append(f"    <p class='description'>{escape_html(doc_description)}</p>")

    # Render each schema
    for schema_name, schema_def in schemas.items():
        html_parts.extend(_render_schema(schema_name, schema_def))

    html_parts.extend([
        "  </main>",
        "</body>",
        "</html>",
    ])

    return '\n'.join(html_parts)


def _render_schema(schema_name: str, schema_def: dict) -> list[str]:
    """Render a single schema definition."""
    parts = []

    schema_type = schema_def.get('type', 'object')
    schema_desc = schema_def.get('description', '')
    required_fields = schema_def.get('required', [])

    # Check if this is an enum schema
    if schema_type == 'string' and 'enum' in schema_def:
        parts.extend(_render_enum_schema(schema_name, schema_def))
        return parts

    parts.extend([
        f"    <div class='schema' id='{escape_html(schema_name)}'>",
        f"      <h2 class='schema-name'>{escape_html(schema_name)}</h2>",
    ])

    if schema_desc:
        parts.append(f"      <p class='schema-description'>{escape_html(schema_desc)}</p>")

    # Custom validations
    custom_validations = schema_def.get('x-custom-validations', [])
    if custom_validations:
        parts.extend(_render_custom_validations(custom_validations))

    # Properties table
    properties = schema_def.get('properties', {})
    if properties:
        parts.extend([
            "      <table class='properties-table'>",
            "        <thead>",
            "          <tr>",
            "            <th>Field</th>",
            "            <th>Type</th>",
            "            <th>Description</th>",
            "            <th>Default</th>",
            "            <th>Key</th>",
            "            <th>Constraints</th>",
            "            <th>Notes</th>",
            "          </tr>",
            "        </thead>",
            "        <tbody>",
        ])

        for prop_name, prop_def in properties.items():
            is_required = prop_name in required_fields
            parts.extend(_render_property_row(prop_name, prop_def, is_required))

        parts.extend([
            "        </tbody>",
            "      </table>",
        ])

    parts.append("    </div>")
    return parts


def _render_enum_schema(schema_name: str, schema_def: dict) -> list[str]:
    """Render an enum schema definition."""
    parts = []

    enum_values = schema_def.get('enum', [])
    enum_mapping = schema_def.get('x-enum-values', {})
    description = schema_def.get('description', '')

    parts.extend([
        f"    <div class='schema enum-schema' id='{escape_html(schema_name)}'>",
        f"      <h3 class='enum-name'>{escape_html(schema_name)}</h3>",
    ])

    if description:
        parts.append(f"      <p class='enum-description'>{escape_html(description)}</p>")

    parts.extend([
        "      <table class='enum-table'>",
        "        <thead>",
        "          <tr>",
        "            <th>Value</th>",
        "            <th>Code</th>",
        "          </tr>",
        "        </thead>",
        "        <tbody>",
    ])

    for val in enum_values:
        code = enum_mapping.get(val, '-')
        parts.append(f"          <tr><td><code>{escape_html(str(val))}</code></td><td>{escape_html(str(code))}</td></tr>")

    parts.extend([
        "        </tbody>",
        "      </table>",
        "    </div>",
    ])

    return parts


def _render_custom_validations(validations: list[dict]) -> list[str]:
    """Render custom validations section."""
    parts = [
        "      <div class='custom-validations'>",
        "        <h4>Custom Validations</h4>",
        "        <ul>",
    ]

    for v in validations:
        name = v.get('name', '')
        desc = v.get('description', '')
        conditions = v.get('conditions', '')

        validation_text = f"<strong>{escape_html(name)}</strong>"
        if conditions:
            validation_text += f" <span class='conditions'>({escape_html(conditions)})</span>"
        if desc:
            validation_text += f": {escape_html(desc)}"

        parts.append(f"          <li>{validation_text}</li>")

    parts.extend([
        "        </ul>",
        "      </div>",
    ])

    return parts


def _render_property_row(prop_name: str, prop_def: dict, is_required: bool) -> list[str]:
    """Render a single property row in the table."""
    parts = []

    prop_type = prop_def.get('type', 'any')
    prop_format = prop_def.get('format', '')
    prop_desc = prop_def.get('description', '')
    nullable = prop_def.get('nullable', False)

    # Build type string
    type_str = prop_type
    if prop_format:
        type_str = f"{prop_type} ({prop_format})"
    if nullable:
        type_str += " | null"

    # Build default value
    default_str = '-'
    if 'default' in prop_def:
        default_val = prop_def['default']
        if default_val is None:
            default_str = '<code>null</code>'
        elif isinstance(default_val, bool):
            default_str = f"<code>{str(default_val).lower()}</code>"
        elif isinstance(default_val, str):
            default_str = f"<code>{escape_html(default_val)}</code>"
        else:
            default_str = f"<code>{escape_html(str(default_val))}</code>"

    # Build key info (PRI, UNI, FK, IDX)
    key_parts = []
    if prop_def.get('x-primary-key'):
        key_parts.append("<span class='key-pri'>PRI</span>")
    if prop_def.get('x-unique'):
        key_parts.append("<span class='key-uni'>UNI</span>")
    if prop_def.get('x-foreign-key'):
        fk = prop_def['x-foreign-key']
        if isinstance(fk, dict):
            fk_ref = f"{fk.get('table', '')}.{fk.get('column', '')}"
            key_parts.append(f"<span class='key-fk'>FK</span> <span class='fk-ref'>{escape_html(fk_ref)}</span>")
        else:
            key_parts.append(f"<span class='key-fk'>FK</span> <span class='fk-ref'>{escape_html(str(fk))}</span>")
    if prop_def.get('x-index'):
        key_parts.append("<span class='key-idx'>IDX</span>")
    key_str = ' '.join(key_parts) if key_parts else '-'

    # Build constraints
    constraints = []
    if is_required:
        constraints.append("<span class='required'>required</span>")
    if prop_def.get('x-auto-increment'):
        constraints.append("<span class='auto-increment'>auto_increment</span>")
    if 'maxLength' in prop_def:
        constraints.append(f"maxLength: {prop_def['maxLength']}")
    if 'minLength' in prop_def:
        constraints.append(f"minLength: {prop_def['minLength']}")
    if 'minimum' in prop_def:
        constraints.append(f"min: {prop_def['minimum']}")
    if 'maximum' in prop_def:
        constraints.append(f"max: {prop_def['maximum']}")
    if 'pattern' in prop_def:
        pattern = prop_def['pattern']
        # Escape HTML in pattern
        constraints.append(f"pattern: <code>{escape_html(pattern)}</code>")
    if 'enum' in prop_def:
        enum_vals = ', '.join(str(v) for v in prop_def['enum'])
        constraints.append(f"enum: [{escape_html(enum_vals)}]")

    constraints_str = '<br>'.join(constraints) if constraints else '-'

    # Build notes
    notes_str = '-'
    if 'x-notes' in prop_def:
        notes = prop_def['x-notes']
        if isinstance(notes, list):
            notes_str = '<br>'.join(escape_html(str(n)) for n in notes)
        else:
            notes_str = escape_html(str(notes))

    parts.append("          <tr>")
    parts.append(f"            <td><code>{escape_html(prop_name)}</code></td>")
    parts.append(f"            <td><code>{escape_html(type_str)}</code></td>")
    parts.append(f"            <td>{escape_html(prop_desc)}</td>")
    parts.append(f"            <td>{default_str}</td>")
    parts.append(f"            <td>{key_str}</td>")
    parts.append(f"            <td>{constraints_str}</td>")
    parts.append(f"            <td class='notes-cell'>{notes_str}</td>")
    parts.append("          </tr>")

    return parts


def _get_html_header(title: str) -> list[str]:
    """Generate HTML header with styles for schema documentation."""
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
        "    .table-name {",
        "      color: #666;",
        "      font-size: 0.9em;",
        "      margin-bottom: 10px;",
        "    }",
        "    .table-name code {",
        "      background: #e9ecef;",
        "      padding: 2px 6px;",
        "      border-radius: 3px;",
        "      font-family: 'SF Mono', Monaco, Consolas, monospace;",
        "    }",
        "    .description {",
        "      color: #666;",
        "      margin-bottom: 30px;",
        "    }",
        "    .schema {",
        "      background: white;",
        "      border-radius: 8px;",
        "      padding: 20px;",
        "      margin-bottom: 20px;",
        "      box-shadow: 0 2px 4px rgba(0,0,0,0.1);",
        "      overflow-x: auto;",
        "    }",
        "    .schema-name {",
        "      font-size: 22px;",
        "      color: #2c5282;",
        "      margin-bottom: 8px;",
        "      padding-bottom: 8px;",
        "      border-bottom: 2px solid #e2e8f0;",
        "    }",
        "    .schema-description {",
        "      color: #555;",
        "      margin-bottom: 15px;",
        "    }",
        "    .properties-table {",
        "      width: 100%;",
        "      border-collapse: collapse;",
        "      font-size: 13px;",
        "      border: 1px solid #dee2e6;",
        "      table-layout: auto;",
        "    }",
        "    .properties-table th {",
        "      background: #f8f9fa;",
        "      padding: 8px 10px;",
        "      text-align: left;",
        "      border: 1px solid #dee2e6;",
        "      font-weight: 600;",
        "      white-space: nowrap;",
        "    }",
        "    .properties-table td {",
        "      padding: 8px 10px;",
        "      border: 1px solid #dee2e6;",
        "      vertical-align: top;",
        "    }",
        "    .properties-table td:nth-child(1) { white-space: nowrap; }",
        "    .properties-table td:nth-child(2) { white-space: nowrap; }",
        "    .properties-table td:nth-child(5) { white-space: nowrap; }",
        "    .properties-table tr:hover {",
        "      background: #f8f9fa;",
        "    }",
        "    .properties-table code {",
        "      font-family: 'SF Mono', Monaco, Consolas, monospace;",
        "      font-size: 13px;",
        "    }",
        "    .required {",
        "      color: #e53e3e;",
        "      font-weight: 600;",
        "      font-size: 12px;",
        "    }",
        "    .auto-increment {",
        "      color: #6b7280;",
        "      font-size: 12px;",
        "    }",
        "    .key-pri {",
        "      background: #fef3c7;",
        "      color: #92400e;",
        "      padding: 2px 6px;",
        "      border-radius: 3px;",
        "      font-size: 11px;",
        "      font-weight: 600;",
        "    }",
        "    .key-uni {",
        "      background: #dbeafe;",
        "      color: #1e40af;",
        "      padding: 2px 6px;",
        "      border-radius: 3px;",
        "      font-size: 11px;",
        "      font-weight: 600;",
        "    }",
        "    .key-fk {",
        "      background: #dcfce7;",
        "      color: #166534;",
        "      padding: 2px 6px;",
        "      border-radius: 3px;",
        "      font-size: 11px;",
        "      font-weight: 600;",
        "    }",
        "    .fk-ref {",
        "      color: #166534;",
        "      font-size: 11px;",
        "    }",
        "    .key-idx {",
        "      background: #f3e8ff;",
        "      color: #7c3aed;",
        "      padding: 2px 6px;",
        "      border-radius: 3px;",
        "      font-size: 11px;",
        "      font-weight: 600;",
        "    }",
        "    .notes-cell {",
        "      font-size: 12px;",
        "      color: #666;",
        "      max-width: 300px;",
        "    }",
        "    .enum-schema {",
        "      background: #f0f9ff;",
        "      border-left: 4px solid #3182ce;",
        "    }",
        "    .enum-name {",
        "      font-size: 16px;",
        "      color: #3182ce;",
        "      margin-bottom: 8px;",
        "    }",
        "    .enum-description {",
        "      color: #555;",
        "      font-size: 13px;",
        "      margin-bottom: 10px;",
        "    }",
        "    .enum-table {",
        "      width: auto;",
        "      min-width: 200px;",
        "      border-collapse: collapse;",
        "      font-size: 13px;",
        "    }",
        "    .enum-table th {",
        "      background: #e2e8f0;",
        "      padding: 8px 12px;",
        "      text-align: left;",
        "    }",
        "    .enum-table td {",
        "      padding: 6px 12px;",
        "      border-bottom: 1px solid #e2e8f0;",
        "    }",
        "    .custom-validations {",
        "      background: #fffbeb;",
        "      border: 1px solid #fcd34d;",
        "      border-radius: 6px;",
        "      padding: 12px 15px;",
        "      margin-bottom: 15px;",
        "    }",
        "    .custom-validations h4 {",
        "      color: #92400e;",
        "      font-size: 14px;",
        "      margin-bottom: 8px;",
        "    }",
        "    .custom-validations ul {",
        "      margin-left: 20px;",
        "      font-size: 13px;",
        "    }",
        "    .custom-validations li {",
        "      margin-bottom: 4px;",
        "    }",
        "    .custom-validations .conditions {",
        "      color: #666;",
        "      font-style: italic;",
        "    }",
        "    /* Responsive */",
        "    @media (max-width: 768px) {",
        "      .sidebar { display: none; }",
        "      .main-content { margin-left: 0; padding: 20px; }",
        "    }",
        "  </style>",
        "</head>",
        "<body>",
    ]
    return parts
