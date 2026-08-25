"""Index page HTML generation."""

from __future__ import annotations

from collections import OrderedDict
from datetime import datetime
from pathlib import Path

from .styles import get_index_styles, get_index_scripts
from .sidebar import generate_index_sidebar, escape_html


def _render_test_items(
    html_parts: list[str],
    files: list[dict],
    item_class: str,
    meta_fn,
    indent: int,
) -> None:
    """Render a flat ``<ul>`` of test entries at *indent* spaces."""
    pad = " " * indent
    html_parts.append(f"{pad}<ul class='test-list'>")
    for f in files:
        html_parts.extend([
            f"{pad}  <li class='test-item {item_class}'>",
            f"{pad}    <a href='{f['path']}' class='test-name'>{escape_html(f['name'])}</a>",
            f"{pad}    <div class='test-meta'>",
            f"{pad}      <span class='badge badge-platform'>{f['platform']}</span>",
            f"{pad}      {meta_fn(f)}",
            f"{pad}    </div>",
        ])
        if f['description']:
            html_parts.append(f"{pad}    <div class='test-description'>{escape_html(f['description'])}</div>")
        html_parts.append(f"{pad}  </li>")
    html_parts.append(f"{pad}</ul>")


def _render_test_category(
    html_parts: list[str],
    files: list[dict],
    category_id: str,
    label: str,
    badge_class: str,
    item_class: str,
    meta_fn,
) -> None:
    """Render one test category, split into per-app subsections when the
    project holds more than one app.

    A project with a single app carries no group on its tests and renders as
    the flat list it always did; only a multi-app tree grows the extra level.
    """
    by_group: OrderedDict[str, list[dict]] = OrderedDict()
    ungrouped: list[dict] = []
    for f in files:
        group = f.get('group', '')
        if group:
            by_group.setdefault(group, []).append(f)
        else:
            ungrouped.append(f)

    html_parts.extend([
        "    <div class='category'>",
        f"      <div class='category-header collapsed' id='{category_id}-header' onclick=\"toggleCategory('{category_id}')\">",
        f"        <h2><span class='arrow'>▼</span> {label} <span class='category-badge {badge_class}'>{len(files)}</span></h2>",
        "      </div>",
        f"      <div class='category-content collapsed' id='{category_id}-content'>",
    ])

    if ungrouped:
        _render_test_items(html_parts, ungrouped, item_class, meta_fn, indent=8)

    for group_name, group_files in by_group.items():
        group_display = group_name.replace('_', ' ').replace('-', ' ').title()
        group_id = f"{category_id}-{group_name.replace('/', '-')}"
        html_parts.extend([
            "        <div class='subcategory'>",
            f"          <div class='subcategory-header collapsed' id='{group_id}-header' onclick=\"toggleCategory('{group_id}')\">",
            f"            <h3><span class='arrow'>▼</span> {escape_html(group_display)} <span class='category-badge {badge_class}'>{len(group_files)}</span></h3>",
            "          </div>",
            f"          <div class='category-content collapsed' id='{group_id}-content'>",
        ])
        _render_test_items(html_parts, group_files, item_class, meta_fn, indent=12)
        html_parts.extend([
            "          </div>",
            "        </div>",
        ])

    html_parts.extend([
        "      </div>",
        "    </div>",
    ])


def generate_index_html(
    output_dir: Path,
    files: list[dict],
    title: str,
    has_mermaid_diagram: bool = False,
    document_files: list[dict] | None = None,
    api_doc_categories: dict[str, list[dict]] | None = None,
    spec_files: list[dict] | None = None,
    component_files: list[dict] | None = None,
    md_files_by_dir: dict[str, list[dict]] | None = None,
    figma_files: list[dict] | None = None,
    apps_nav: dict[str, dict] | None = None
) -> None:
    """
    Generate index.html with collapsible categories and sidebar navigation.

    Args:
        output_dir: Output directory path
        files: List of generated file info dicts
        title: Page title
        has_mermaid_diagram: Whether a Mermaid diagram was generated
        document_files: List of document file dicts
        api_doc_categories: Dict of category name -> list of API doc file dicts
        spec_files: List of screen specification file dicts
        component_files: List of component specification file dicts
        md_files_by_dir: Dict of directory name -> list of markdown file dicts
        figma_files: List of Figma screen file dicts
    """
    screen_files = [f for f in files if f['type'] == 'screen']
    flow_files = [f for f in files if f['type'] == 'flow']
    other_files = [f for f in files if f['type'] not in ['screen', 'flow']]

    screen_count = len(screen_files)
    flow_count = len(flow_files)
    doc_count = len(document_files) if document_files else 0
    # Count all API docs across categories
    api_doc_count = sum(len(docs) for docs in (api_doc_categories or {}).values())
    total_cases = sum(f['case_count'] for f in files)
    total_steps = sum(f['step_count'] for f in files)

    spec_count = len(spec_files) if spec_files else 0
    component_count = len(component_files) if component_files else 0

    html_parts = _get_html_header(title)
    html_parts.extend(generate_index_sidebar(title, flow_files, screen_files, has_mermaid_diagram, document_files, api_doc_categories, spec_files, component_files, md_files_by_dir, figma_files, apps_nav=apps_nav))

    # Main content
    html_parts.append("  <main class='main-content'>")
    html_parts.append(f"    <h1>{escape_html(title)}</h1>")

    # Flow Diagram link (if available)
    if has_mermaid_diagram:
        html_parts.extend([
            "    <div class='diagram-link-container'>",
            "      <a href='diagram.html' class='diagram-link'>",
            "        <span class='diagram-icon'>📊</span>",
            "        <span class='diagram-text'>View Flow Diagram</span>",
            "        <span class='diagram-desc'>Screen transition visualization</span>",
            "      </a>",
            "    </div>",
        ])

    # Summary section
    html_parts.extend([
        "    <div class='summary'>",
        "      <div class='summary-item'>",
        f"        <div class='summary-value'>{len(files)}</div>",
        "        <div class='summary-label'>Test Files</div>",
        "      </div>",
        "      <div class='summary-item'>",
        f"        <div class='summary-value'>{screen_count}</div>",
        "        <div class='summary-label'>Screen Tests</div>",
        "      </div>",
        "      <div class='summary-item'>",
        f"        <div class='summary-value'>{flow_count}</div>",
        "        <div class='summary-label'>Flow Tests</div>",
        "      </div>",
        "      <div class='summary-item'>",
        f"        <div class='summary-value'>{total_cases}</div>",
        "        <div class='summary-label'>Test Cases</div>",
        "      </div>",
        "      <div class='summary-item'>",
        f"        <div class='summary-value'>{total_steps}</div>",
        "        <div class='summary-label'>Total Steps</div>",
        "      </div>",
        "    </div>",
    ])

    # Flow Tests category first (collapsible, starts collapsed)
    if flow_files:
        _render_test_category(
            html_parts, flow_files,
            category_id='flows', label='Flow Tests',
            badge_class='flow', item_class='flow',
            meta_fn=lambda f: f"{f['step_count']} steps",
        )

    # Screen Tests category (collapsible, starts collapsed)
    if screen_files:
        _render_test_category(
            html_parts, screen_files,
            category_id='screens', label='Screen Tests',
            badge_class='screen', item_class='screen',
            meta_fn=lambda f: f"{f['case_count']} cases, {f['step_count']} steps",
        )

    # Documents category (collapsible, starts collapsed)
    if document_files:
        html_parts.extend([
            "    <div class='category'>",
            "      <div class='category-header collapsed' id='documents-header' onclick=\"toggleCategory('documents')\">",
            f"        <h2><span class='arrow'>▼</span> Documents <span class='category-badge doc'>{doc_count}</span></h2>",
            "      </div>",
            "      <div class='category-content collapsed' id='documents-content'>",
            "        <ul class='test-list'>",
        ])
        for d in document_files:
            html_parts.extend([
                "          <li class='test-item doc'>",
                f"            <a href='{d['path']}' class='test-name'>{escape_html(d['name'])}</a>",
                "          </li>",
            ])
        html_parts.extend([
            "        </ul>",
            "      </div>",
            "    </div>",
        ])

    # API Docs categories (one section per directory, collapsible, starts collapsed)
    if api_doc_categories:
        for category_name, category_docs in api_doc_categories.items():
            # Format category name for display (e.g., "api" -> "API", "db" -> "DB",
            # multi-DB "db/main" -> "DB: main")
            if category_name.startswith('db/'):
                display_name = f"DB: {category_name[3:]}"
            else:
                display_name = category_name.upper() if len(category_name) <= 3 else category_name.title()
            category_id = f"api-{category_name.replace('/', '-')}"

            # Check if this category has schema-only files (for ER diagram link)
            has_schema_files = any(
                not d.get('has_api_paths', True) for d in category_docs
            )

            html_parts.extend([
                "    <div class='category'>",
                f"      <div class='category-header collapsed' id='{category_id}-header' onclick=\"toggleCategory('{category_id}')\">",
                f"        <h2><span class='arrow'>▼</span> {display_name} <span class='category-badge api'>{len(category_docs)}</span></h2>",
                "      </div>",
                f"      <div class='category-content collapsed' id='{category_id}-content'>",
            ])

            # Add ER Diagram link for DB categories (per-database when the
            # multi-DB layout is in use)
            if category_name.lower() == 'db' or category_name.startswith('db/'):
                html_parts.extend([
                    "        <div class='erd-link-container'>",
                    f"          <a href='{category_name}/erd.html' class='erd-link'>",
                    "            <span class='erd-icon'>📊</span>",
                    "            <span class='erd-text'>View ER Diagram</span>",
                    "            <span class='erd-desc'>Table relationships visualization</span>",
                    "          </a>",
                    "        </div>",
                ])

            # Group by subdir if any
            by_subdir: OrderedDict[str, list[dict]] = OrderedDict()
            top_level_docs = []
            for d in category_docs:
                subdir = d.get('subdir', '')
                if subdir:
                    first_part = subdir.split('/')[0]
                    if first_part not in by_subdir:
                        by_subdir[first_part] = []
                    by_subdir[first_part].append(d)
                else:
                    top_level_docs.append(d)

            if by_subdir:
                for subdir_name, subdir_docs in by_subdir.items():
                    subdir_display = subdir_name.replace('_', ' ').title()
                    subdir_id = f"{category_id}-{subdir_name}"
                    html_parts.extend([
                        "        <div class='subcategory'>",
                        f"          <div class='subcategory-header collapsed' id='{subdir_id}-header' onclick=\"toggleCategory('{subdir_id}')\">",
                        f"            <h3><span class='arrow'>▼</span> {escape_html(subdir_display)} <span class='category-badge api'>{len(subdir_docs)}</span></h3>",
                        "          </div>",
                        f"          <div class='category-content collapsed' id='{subdir_id}-content'>",
                        "            <ul class='test-list'>",
                    ])
                    for d in subdir_docs:
                        desc = d.get('description', '')
                        html_parts.extend([
                            "              <li class='test-item api'>",
                            f"                <a href='{d['path']}' class='test-name'>{escape_html(d['name'])}</a>",
                        ])
                        if desc:
                            html_parts.append(f"                <div class='test-description'>{escape_html(desc)}</div>")
                        html_parts.append("              </li>")
                    html_parts.extend([
                        "            </ul>",
                        "          </div>",
                        "        </div>",
                    ])

            if top_level_docs:
                html_parts.append("        <ul class='test-list'>")
                for d in top_level_docs:
                    desc = d.get('description', '')
                    html_parts.extend([
                        "          <li class='test-item api'>",
                        f"            <a href='{d['path']}' class='test-name'>{escape_html(d['name'])}</a>",
                    ])
                    if desc:
                        html_parts.append(f"            <div class='test-description'>{escape_html(desc)}</div>")
                    html_parts.append("          </li>")
                html_parts.append("        </ul>")

            if not by_subdir and not top_level_docs:
                html_parts.append("        <ul class='test-list'></ul>")

            html_parts.extend([
                "      </div>",
                "    </div>",
            ])

    # Markdown files categories (one section per directory, collapsible, starts collapsed, with subdir grouping)
    if md_files_by_dir:
        for dir_name, md_files in md_files_by_dir.items():
            clean_name = dir_name.replace('-', ' ').replace('_', ' ')
            display_name = clean_name.title() if len(clean_name) > 3 else clean_name.upper()
            category_id = f"md-{dir_name}"

            html_parts.extend([
                "    <div class='category'>",
                f"      <div class='category-header collapsed' id='{category_id}-header' onclick=\"toggleCategory('{category_id}')\">",
                f"        <h2><span class='arrow'>▼</span> {display_name} <span class='category-badge md'>{len(md_files)}</span></h2>",
                "      </div>",
                f"      <div class='category-content collapsed' id='{category_id}-content'>",
            ])
            # Check if files have subdirs for sub-grouping
            has_subdirs = any(f.get('subdir') for f in md_files)
            if has_subdirs:
                # Group by subdir
                top_level = [f for f in md_files if not f.get('subdir')]
                by_subdir: OrderedDict[str, list[dict]] = OrderedDict()
                for f in md_files:
                    subdir = f.get('subdir', '')
                    if subdir:
                        if subdir not in by_subdir:
                            by_subdir[subdir] = []
                        by_subdir[subdir].append(f)

                # Render top-level files first
                if top_level:
                    html_parts.append("        <ul class='test-list'>")
                    for f in top_level:
                        html_parts.extend([
                            "          <li class='test-item md'>",
                            f"            <a href='{f['path']}' class='test-name'>{escape_html(f['name'])}</a>",
                            "          </li>",
                        ])
                    html_parts.append("        </ul>")

                # Render subdirectory groups
                for subdir_name, subdir_files in by_subdir.items():
                    sub_display = subdir_name.replace('_', ' ').replace('-', ' ').title()
                    sub_id = f"{category_id}-{subdir_name}"
                    html_parts.extend([
                        "        <div class='subcategory'>",
                        f"          <div class='subcategory-header collapsed' id='{sub_id}-header' onclick=\"toggleCategory('{sub_id}')\">",
                        f"            <h3><span class='arrow'>▼</span> {escape_html(sub_display)} <span class='category-badge md'>{len(subdir_files)}</span></h3>",
                        "          </div>",
                        f"          <div class='category-content collapsed' id='{sub_id}-content'>",
                        "            <ul class='test-list'>",
                    ])
                    for f in subdir_files:
                        html_parts.extend([
                            "              <li class='test-item md'>",
                            f"                <a href='{f['path']}' class='test-name'>{escape_html(f['name'])}</a>",
                            "              </li>",
                        ])
                    html_parts.extend([
                        "            </ul>",
                        "          </div>",
                        "        </div>",
                    ])
            else:
                html_parts.append("        <ul class='test-list'>")
                for f in md_files:
                    html_parts.extend([
                        "          <li class='test-item md'>",
                        f"            <a href='{f['path']}' class='test-name'>{escape_html(f['name'])}</a>",
                        "          </li>",
                    ])
                html_parts.append("        </ul>")
            html_parts.extend([
                "      </div>",
                "    </div>",
            ])

    # Figma Screens category (collapsible, starts collapsed, grouped by canvas)
    if figma_files:
        # Group by canvas
        figma_by_canvas: OrderedDict[str, list[dict]] = OrderedDict()
        for f in figma_files:
            canvas = f.get('canvas', '')
            if canvas not in figma_by_canvas:
                figma_by_canvas[canvas] = []
            figma_by_canvas[canvas].append(f)

        html_parts.extend([
            "    <div class='category'>",
            "      <div class='category-header collapsed' id='figma-header' onclick=\"toggleCategory('figma')\">",
            f"        <h2><span class='arrow'>▼</span> Figma Screens <span class='category-badge figma'>{len(figma_files)}</span></h2>",
            "      </div>",
            "      <div class='category-content collapsed' id='figma-content'>",
        ])

        # Always group by canvas with sub-headers
        for canvas_name, screens in figma_by_canvas.items():
            safe_id = canvas_name.replace('/', '-').replace(' ', '_').replace('.', '_')
            html_parts.extend([
                f"        <div class='canvas-group'>",
                f"          <div class='canvas-group-header collapsed' id='figma-{safe_id}-header' onclick=\"toggleCategory('figma-{safe_id}')\">",
                f"            <h3><span class='arrow'>▼</span> {escape_html(canvas_name)} <span class='category-badge figma'>{len(screens)}</span></h3>",
                "          </div>",
                f"          <div class='canvas-group-content collapsed' id='figma-{safe_id}-content'>",
                "            <ul class='test-list'>",
            ])
            for f in screens:
                html_parts.extend([
                    "              <li class='test-item figma'>",
                    f"                <a href='{f['path']}' class='test-name'>{escape_html(f['name'])}</a>",
                    "              </li>",
                ])
            html_parts.extend([
                "            </ul>",
                "          </div>",
                "        </div>",
            ])

        html_parts.extend([
            "      </div>",
            "    </div>",
        ])

    # Other Tests category (collapsible, starts collapsed)
    if other_files:
        html_parts.extend([
            "    <div class='category'>",
            "      <div class='category-header collapsed' id='other-header' onclick=\"toggleCategory('other')\">",
            f"        <h2><span class='arrow'>▼</span> Other Tests <span class='category-badge'>{len(other_files)}</span></h2>",
            "      </div>",
            "      <div class='category-content collapsed' id='other-content'>",
            "        <ul class='test-list'>",
        ])
        for f in other_files:
            html_parts.extend([
                "          <li class='test-item'>",
                f"            <a href='{f['path']}' class='test-name'>{escape_html(f['name'])}</a>",
                "            <div class='test-meta'>",
                f"              <span class='badge'>{f['type']}</span>",
                f"              <span class='badge badge-platform'>{f['platform']}</span>",
                "            </div>",
            ])
            if f['description']:
                html_parts.append(f"            <div class='test-description'>{escape_html(f['description'])}</div>")
            html_parts.append("          </li>")
        html_parts.extend([
            "        </ul>",
            "      </div>",
            "    </div>",
        ])

    # Screen Specs category (collapsible, starts collapsed)
    if spec_files:
        html_parts.extend([
            "    <div class='category'>",
            "      <div class='category-header collapsed' id='specs-header' onclick=\"toggleCategory('specs')\">",
            f"        <h2><span class='arrow'>▼</span> Screen Specs <span class='category-badge spec'>{spec_count}</span></h2>",
            "      </div>",
            "      <div class='category-content collapsed' id='specs-content'>",
            "        <ul class='test-list'>",
        ])
        for s in spec_files:
            html_parts.extend([
                "          <li class='test-item spec'>",
                f"            <a href='{s['path']}' class='test-name'>{escape_html(s['name'])}</a>",
                "          </li>",
            ])
        html_parts.extend([
            "        </ul>",
            "      </div>",
            "    </div>",
        ])

    # Components category (collapsible, starts collapsed)
    if component_files:
        html_parts.extend([
            "    <div class='category'>",
            "      <div class='category-header collapsed' id='components-header' onclick=\"toggleCategory('components')\">",
            f"        <h2><span class='arrow'>▼</span> Components <span class='category-badge component'>{component_count}</span></h2>",
            "      </div>",
            "      <div class='category-content collapsed' id='components-content'>",
            "        <ul class='test-list'>",
        ])
        for c in component_files:
            category = c.get('category', 'other')
            html_parts.extend([
                "          <li class='test-item component'>",
                f"            <a href='{c['path']}' class='test-name'>{escape_html(c['name'])}</a>",
                f"            <span class='badge badge-category'>{category}</span>",
                "          </li>",
            ])
        html_parts.extend([
            "        </ul>",
            "      </div>",
            "    </div>",
        ])

    # App-specific sections (multi-app mode)
    if apps_nav:
        for app_name, app_data in apps_nav.items():
            total_items = sum(
                sum(len(files) for files in v.values()) if isinstance(v, dict) else len(v)
                for v in app_data.values()
            )
            safe_id = app_name.replace('/', '-').replace(' ', '_')
            html_parts.extend([
                "    <div class='category'>",
                f"      <div class='category-header collapsed' id='app-{safe_id}-header' onclick=\"toggleCategory('app-{safe_id}')\">",
                f"        <h2><span class='arrow'>▼</span> {escape_html(app_name)} <span class='category-badge app'>{total_items}</span></h2>",
                "      </div>",
                f"      <div class='category-content collapsed' id='app-{safe_id}-content'>",
            ])

            # App specs
            if app_data.get('specs'):
                html_parts.append("        <h3>Screen Specs</h3>")
                html_parts.append("        <ul class='test-list'>")
                for s in app_data['specs']:
                    html_parts.extend([
                        "          <li class='test-item spec'>",
                        f"            <a href='{s['path']}' class='test-name'>{escape_html(s['name'])}</a>",
                        "          </li>",
                    ])
                html_parts.append("        </ul>")

            # App components
            if app_data.get('components'):
                html_parts.append("        <h3>Components</h3>")
                html_parts.append("        <ul class='test-list'>")
                for c in app_data['components']:
                    html_parts.extend([
                        "          <li class='test-item component'>",
                        f"            <a href='{c['path']}' class='test-name'>{escape_html(c['name'])}</a>",
                        "          </li>",
                    ])
                html_parts.append("        </ul>")

            # App markdown files
            if app_data.get('md_files_by_dir'):
                for dir_name, md_files in app_data['md_files_by_dir'].items():
                    clean_name = dir_name.replace('-', ' ').replace('_', ' ')
                    display_name = clean_name.title() if len(dir_name) > 3 else clean_name.upper()
                    html_parts.append(f"        <h3>{escape_html(display_name)}</h3>")
                    html_parts.append("        <ul class='test-list'>")
                    for f in md_files:
                        html_parts.extend([
                            "          <li class='test-item'>",
                            f"            <a href='{f['path']}' class='test-name'>{escape_html(f['name'])}</a>",
                            "          </li>",
                        ])
                    html_parts.append("        </ul>")

            html_parts.extend([
                "      </div>",
                "    </div>",
            ])

    # Footer
    html_parts.extend([
        f"    <p class='generated'>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>",
        "  </main>",
        "</body>",
        "</html>",
    ])

    # Write index.html
    index_path = output_dir / "index.html"
    with open(index_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(html_parts))

    from ..generator import note_page_generated  # late: avoids a cycle
    note_page_generated(index_path, indent="  ")


def _get_html_header(title: str) -> list[str]:
    """Get HTML header with styles for index page."""
    parts = [
        "<!DOCTYPE html>",
        "<html lang='en'>",
        "<head>",
        f"  <title>{escape_html(title)}</title>",
        "  <meta charset='utf-8'>",
        "  <meta name='viewport' content='width=device-width, initial-scale=1'>",
        "  <style>",
    ]
    parts.extend(get_index_styles())
    parts.append("  </style>")
    parts.extend(get_index_scripts())
    parts.extend([
        "</head>",
        "<body>",
    ])
    return parts
