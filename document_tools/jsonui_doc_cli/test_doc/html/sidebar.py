"""Sidebar generation for HTML documentation."""

from __future__ import annotations
from collections import OrderedDict


def escape_html(text: str) -> str:
    """Escape HTML special characters."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _make_safe_id(name: str) -> str:
    """Create a safe HTML ID from a name."""
    return name.replace('/', '-').replace(' ', '_').replace('.', '_')


def _get_rel_root(current_path: str | None) -> str:
    """Calculate relative path to root from a page's path.

    E.g., 'specs/login.html' -> '../'
          'client/specs/login.html' -> '../../'
    """
    if not current_path:
        return "../"
    from pathlib import Path
    depth = len(Path(current_path).parent.parts)
    if depth == 0:
        return "./"
    return "../" * depth


def _render_figma_tree(
    parts: list[str],
    screens: list[dict],
    href_prefix: str,
    current_path: str | None,
    id_prefix: str,
    indent: int = 12,
) -> None:
    """Recursively render screens grouped by their section hierarchy.

    Screens with no remaining sections are rendered as list items.
    Screens with sections are grouped into collapsible subsections,
    then recursed into with the first section level consumed.

    Args:
        parts: List to append HTML strings to
        screens: List of screen dicts with 'name', 'path', 'sections'
        href_prefix: Prefix for href links
        current_path: Current page path for highlighting
        id_prefix: ID prefix for toggle elements (e.g. 'figma-Canvas1')
        indent: Current indentation level (spaces)
    """
    pad = " " * indent

    # Separate: screens with no remaining sections vs those with sections
    top_level = []
    by_section: OrderedDict[str, list[dict]] = OrderedDict()
    for fg in screens:
        sections = fg.get('sections', [])
        if not sections:
            top_level.append(fg)
        else:
            first = sections[0]
            if first not in by_section:
                by_section[first] = []
            # Create a copy with the first section consumed
            by_section[first].append({**fg, 'sections': sections[1:]})

    # Render section groups first (collapsible subsections)
    for section_name, section_screens in by_section.items():
        safe_id = f"{id_prefix}-{_make_safe_id(section_name)}"
        total = len(section_screens)
        parts.append(f"{pad}<div class='sidebar-subsection'>")
        parts.append(f"{pad}  <div class='sidebar-subtitle collapsed' id='{safe_id}-title' onclick=\"toggleSection('{safe_id}')\"><span class='arrow'>▼</span> {escape_html(section_name)} <span class='count'>{total}</span></div>")
        parts.append(f"{pad}  <div class='sidebar-list collapsed' id='{safe_id}-list'>")

        # Check if any sub-screens still have sections (need further nesting)
        has_subsections = any(fg.get('sections') for fg in section_screens)
        if has_subsections:
            _render_figma_tree(parts, section_screens, href_prefix, current_path, safe_id, indent + 4)
        else:
            # All screens are leaves - render as flat list
            parts.append(f"{pad}    <ul>")
            for fg in section_screens:
                is_current = current_path and fg['path'] == current_path
                current_class = " current" if is_current else ""
                parts.append(f"{pad}      <li><a href='{href_prefix}{fg['path']}' class='nav-link{current_class}' title='{escape_html(fg['name'])}'>{escape_html(fg['name'])}</a></li>")
            parts.append(f"{pad}    </ul>")

        parts.append(f"{pad}  </div>")
        parts.append(f"{pad}</div>")

    # Render top-level screens (no section) as flat list
    if top_level:
        parts.append(f"{pad}<ul>")
        for fg in top_level:
            is_current = current_path and fg['path'] == current_path
            current_class = " current" if is_current else ""
            parts.append(f"{pad}  <li><a href='{href_prefix}{fg['path']}' class='nav-link{current_class}' title='{escape_html(fg['name'])}'>{escape_html(fg['name'])}</a></li>")
        parts.append(f"{pad}</ul>")


def _render_api_docs_with_subgroups(
    docs: list[dict],
    href_prefix: str,
    current_path: str | None,
    id_prefix: str,
    indent: int = 8,
) -> None:
    """Render API docs grouped by subdir as collapsible subsections.

    If docs have no subdir, they are rendered as a flat list.
    If docs have subdirs, they are grouped into collapsible subsections.

    Args:
        docs: List of dicts with 'name', 'path', 'subdir'
        href_prefix: Prefix for href links
        current_path: Current page path for highlighting
        id_prefix: ID prefix for toggle elements
        indent: Current indentation level (spaces)

    Returns:
        List of HTML strings
    """
    parts: list[str] = []
    pad = " " * indent

    # Separate top-level (no subdir) from those with subdirs
    top_level = []
    by_subdir: OrderedDict[str, list[dict]] = OrderedDict()
    for d in docs:
        subdir = d.get('subdir', '')
        if not subdir:
            top_level.append(d)
        else:
            # Use first path component as the group key
            first_part = subdir.split('/')[0]
            if first_part not in by_subdir:
                by_subdir[first_part] = []
            by_subdir[first_part].append(d)

    # Render subdir groups first
    for subdir_name, subdir_docs in by_subdir.items():
        safe_id = f"{id_prefix}-{_make_safe_id(subdir_name)}"
        display_name = subdir_name.replace('_', ' ').replace('-', ' ').title()
        # Auto-expand sub-group if it contains the current page
        contains_current = current_path and any(d['path'] == current_path for d in subdir_docs)
        collapsed_class = "" if contains_current else " collapsed"
        parts.append(f"{pad}<div class='sidebar-subsection'>")
        parts.append(f"{pad}  <div class='sidebar-subtitle{collapsed_class}' id='{safe_id}-title' onclick=\"toggleSection('{safe_id}')\"><span class='arrow'>▼</span> {escape_html(display_name)} <span class='count'>{len(subdir_docs)}</span></div>")
        parts.append(f"{pad}  <div class='sidebar-list{collapsed_class}' id='{safe_id}-list'>")
        parts.append(f"{pad}    <ul>")
        for d in subdir_docs:
            is_current = current_path and d['path'] == current_path
            current_class = " current" if is_current else ""
            parts.append(f"{pad}      <li><a href='{href_prefix}{d['path']}' class='nav-link{current_class}' title='{escape_html(d['name'])}'>{escape_html(d['name'])}</a></li>")
        parts.append(f"{pad}    </ul>")
        parts.append(f"{pad}  </div>")
        parts.append(f"{pad}</div>")

    # Render top-level docs
    if top_level:
        parts.append(f"{pad}<ul>")
        for d in top_level:
            is_current = current_path and d['path'] == current_path
            current_class = " current" if is_current else ""
            parts.append(f"{pad}  <li><a href='{href_prefix}{d['path']}' class='nav-link{current_class}' title='{escape_html(d['name'])}'>{escape_html(d['name'])}</a></li>")
        parts.append(f"{pad}</ul>")

    return parts


def _render_figma_sidebar_section(
    figma_screens: list[dict],
    href_prefix: str = '../',
    current_path: str | None = None,
    collapsed: bool = True,
    section_id_prefix: str = "figma",
) -> list[str]:
    """Render Figma Screens sidebar section grouped by canvas, then recursively by section.

    Args:
        figma_screens: List of dicts with 'name', 'path', 'canvas', 'sections'
        href_prefix: Prefix for href links (e.g. '../' for subdir pages, '' for index)
        current_path: Current page path for highlighting
        collapsed: Whether the top-level section starts collapsed
        section_id_prefix: Prefix for HTML element IDs (default: "figma")

    Returns:
        List of HTML strings
    """
    parts = []
    collapsed_cls = " collapsed" if collapsed else ""
    parts.append("    <div class='sidebar-section'>")
    parts.append(f"      <div class='sidebar-title figma{collapsed_cls}' id='{section_id_prefix}-title' onclick=\"toggleSection('{section_id_prefix}')\"><span class='arrow'>▼</span> Figma Screens <span class='count'>{len(figma_screens)}</span></div>")
    parts.append(f"      <div class='sidebar-list{collapsed_cls}' id='{section_id_prefix}-list'>")

    # Group by canvas
    canvases: OrderedDict[str, list[dict]] = OrderedDict()
    for fg in figma_screens:
        canvas = fg.get('canvas', '')
        if canvas not in canvases:
            canvases[canvas] = []
        canvases[canvas].append(fg)

    # Canvas-level collapsible groups, then recursive section tree inside
    for canvas_name, screens in canvases.items():
        safe_id = f"{section_id_prefix}-{_make_safe_id(canvas_name)}"
        parts.append("        <div class='sidebar-subsection'>")
        parts.append(f"          <div class='sidebar-subtitle collapsed' id='{safe_id}-title' onclick=\"toggleSection('{safe_id}')\"><span class='arrow'>▼</span> {escape_html(canvas_name)} <span class='count'>{len(screens)}</span></div>")
        parts.append(f"          <div class='sidebar-list collapsed' id='{safe_id}-list'>")

        # Check if any screens have section data
        has_sections = any(fg.get('sections') for fg in screens)
        if has_sections:
            _render_figma_tree(parts, screens, href_prefix, current_path, safe_id, indent=12)
        else:
            # No section hierarchy - flat list
            parts.append("            <ul>")
            for fg in screens:
                is_current = current_path and fg['path'] == current_path
                current_class = " current" if is_current else ""
                parts.append(f"              <li><a href='{href_prefix}{fg['path']}' class='nav-link{current_class}' title='{escape_html(fg['name'])}'>{escape_html(fg['name'])}</a></li>")
            parts.append("            </ul>")

        parts.append("          </div>")
        parts.append("        </div>")

    parts.append("      </div>")
    parts.append("    </div>")
    return parts


def generate_screen_sidebar(
    title: str,
    cases: list[str],
    all_tests_nav: dict | None = None,
    current_test_path: str | None = None
) -> list[str]:
    """
    Generate sidebar HTML for screen test pages.

    Args:
        title: Page title
        cases: List of case display names
        all_tests_nav: Navigation data {'screens': [...], 'flows': [...]}
        current_test_path: Current test's relative HTML path

    Returns:
        List of HTML strings for the sidebar
    """
    parts = []
    parts.append("  <nav class='sidebar'>")
    parts.append("    <a href='../index.html' class='back-link'>&larr; Back to Index</a>")
    parts.append(f"    <h2>{escape_html(title)}</h2>")

    # Test Cases section (collapsible, expanded by default)
    if cases:
        parts.append("    <div class='sidebar-section'>")
        parts.append(f"      <div class='sidebar-title' id='cases-title' onclick=\"toggleSection('cases')\"><span class='arrow'>▼</span> Test Cases <span class='count'>{len(cases)}</span></div>")
        parts.append("      <div class='sidebar-list' id='cases-list'>")
        parts.append("        <ul>")
        for i, case_display in enumerate(cases, 1):
            case_id = f"case-{i}"
            parts.append(f"          <li><a href='#{case_id}'><span class='case-number'>{i}</span><span class='case-name'>{escape_html(case_display)}</span></a></li>")
        parts.append("        </ul>")
        parts.append("      </div>")
        parts.append("    </div>")

    # Flow Tests navigation (collapsible, collapsed by default)
    if all_tests_nav and all_tests_nav.get('flows'):
        flows = all_tests_nav['flows']
        parts.append("    <div class='sidebar-section'>")
        parts.append(f"      <div class='sidebar-title flow collapsed' id='flows-title' onclick=\"toggleSection('flows')\"><span class='arrow'>▼</span> Flow Tests <span class='count'>{len(flows)}</span></div>")
        parts.append("      <div class='sidebar-list collapsed' id='flows-list'>")
        parts.append("        <ul>")
        for f in flows:
            is_current = current_test_path and f['path'] == current_test_path
            current_class = " current" if is_current else ""
            parts.append(f"          <li><a href='../{f['path']}' class='nav-link{current_class}' title='{escape_html(f['name'])}'>{escape_html(f['name'])}</a></li>")
        parts.append("        </ul>")
        parts.append("      </div>")
        parts.append("    </div>")

    # Screen Tests navigation (collapsible, collapsed by default)
    if all_tests_nav and all_tests_nav.get('screens'):
        screens = all_tests_nav['screens']
        parts.append("    <div class='sidebar-section'>")
        parts.append(f"      <div class='sidebar-title collapsed' id='screens-title' onclick=\"toggleSection('screens')\"><span class='arrow'>▼</span> Screen Tests <span class='count'>{len(screens)}</span></div>")
        parts.append("      <div class='sidebar-list collapsed' id='screens-list'>")
        parts.append("        <ul>")
        for s in screens:
            is_current = current_test_path and s['path'] == current_test_path
            current_class = " current" if is_current else ""
            parts.append(f"          <li><a href='../{s['path']}' class='nav-link{current_class}' title='{escape_html(s['name'])}'>{escape_html(s['name'])}</a></li>")
        parts.append("        </ul>")
        parts.append("      </div>")
        parts.append("    </div>")

    # Documents navigation (collapsible, collapsed by default)
    if all_tests_nav and all_tests_nav.get('documents'):
        documents = all_tests_nav['documents']
        parts.append("    <div class='sidebar-section'>")
        parts.append(f"      <div class='sidebar-title doc collapsed' id='documents-title' onclick=\"toggleSection('documents')\"><span class='arrow'>▼</span> Documents <span class='count'>{len(documents)}</span></div>")
        parts.append("      <div class='sidebar-list collapsed' id='documents-list'>")
        parts.append("        <ul>")
        for d in documents:
            parts.append(f"          <li><a href='../{d['path']}' class='nav-link' title='{escape_html(d['name'])}'>{escape_html(d['name'])}</a></li>")
        parts.append("        </ul>")
        parts.append("      </div>")
        parts.append("    </div>")

    # API Docs navigation (collapsible, collapsed by default, with subdir grouping)
    if all_tests_nav and all_tests_nav.get('api_doc_categories'):
        for category_name, category_docs in all_tests_nav['api_doc_categories'].items():
            display_name = category_name.upper() if len(category_name) <= 3 else category_name.title()
            cat_id = f"api-{_make_safe_id(category_name)}"
            parts.append("    <div class='sidebar-section'>")
            parts.append(f"      <div class='sidebar-title api collapsed' id='{cat_id}-title' onclick=\"toggleSection('{cat_id}')\"><span class='arrow'>▼</span> {display_name} <span class='count'>{len(category_docs)}</span></div>")
            parts.append(f"      <div class='sidebar-list collapsed' id='{cat_id}-list'>")
            has_subdirs = any(d.get('subdir') for d in category_docs)
            if has_subdirs:
                parts.extend(_render_api_docs_with_subgroups(
                    category_docs, href_prefix='../', current_path=current_test_path, id_prefix=cat_id))
            else:
                parts.append("        <ul>")
                for d in category_docs:
                    parts.append(f"          <li><a href='../{d['path']}' class='nav-link' title='{escape_html(d['name'])}'>{escape_html(d['name'])}</a></li>")
                parts.append("        </ul>")
            parts.append("      </div>")
            parts.append("    </div>")
    elif all_tests_nav and all_tests_nav.get('api_docs'):
        api_docs = all_tests_nav['api_docs']
        parts.append("    <div class='sidebar-section'>")
        parts.append(f"      <div class='sidebar-title api collapsed' id='api-docs-title' onclick=\"toggleSection('api-docs')\"><span class='arrow'>▼</span> API Docs <span class='count'>{len(api_docs)}</span></div>")
        parts.append("      <div class='sidebar-list collapsed' id='api-docs-list'>")
        parts.append("        <ul>")
        for d in api_docs:
            parts.append(f"          <li><a href='../{d['path']}' class='nav-link' title='{escape_html(d['name'])}'>{escape_html(d['name'])}</a></li>")
        parts.append("        </ul>")
        parts.append("      </div>")
        parts.append("    </div>")

    # Figma Screens navigation (collapsible, collapsed by default, grouped by canvas)
    if all_tests_nav and all_tests_nav.get('figma_screens'):
        parts.extend(_render_figma_sidebar_section(
            all_tests_nav['figma_screens'], href_prefix='../', current_path=current_test_path))

    parts.append("  </nav>")
    return parts


def generate_flow_sidebar(
    name: str,
    steps: list[dict],
    checkpoints: list[dict],
    all_tests_nav: dict | None = None,
    current_test_path: str | None = None
) -> list[str]:
    """
    Generate sidebar HTML for flow test pages.

    Args:
        name: Flow test name
        steps: List of step data dicts with 'num', 'type', 'label'
        checkpoints: List of checkpoint dicts
        all_tests_nav: Navigation data {'screens': [...], 'flows': [...]}
        current_test_path: Current test's relative HTML path

    Returns:
        List of HTML strings for the sidebar
    """
    parts = []
    parts.append("  <nav class='sidebar'>")
    parts.append("    <a href='../index.html' class='back-link'>&larr; Back to Index</a>")
    parts.append(f"    <h2>{escape_html(name)}</h2>")

    # Steps section (collapsible, expanded by default)
    if steps:
        parts.append("    <div class='sidebar-section'>")
        parts.append(f"      <div class='sidebar-title' id='steps-title' onclick=\"toggleSection('steps')\"><span class='arrow'>▼</span> Steps <span class='count'>{len(steps)}</span></div>")
        parts.append("      <div class='sidebar-list' id='steps-list'>")
        parts.append("        <ul>")
        for step in steps:
            step_num = step["num"]
            step_type = step["type"]
            label = step["label"]

            if step_type == "file":
                icon_class = "file"
            elif step_type == "block":
                icon_class = "block"
            elif step_type == "action":
                icon_class = "action"
            else:
                icon_class = "assert"

            parts.append(f"          <li><a href='#step-{step_num}'><span class='step-num'>{step_num}</span><span class='step-icon {icon_class}'></span><span class='step-label'>{escape_html(label)}</span></a></li>")
        parts.append("        </ul>")
        parts.append("      </div>")
        parts.append("    </div>")

    # Checkpoints section
    if checkpoints:
        parts.append("    <div class='sidebar-section'>")
        parts.append(f"      <div class='sidebar-title' id='checkpoints-title' onclick=\"toggleSection('checkpoints')\"><span class='arrow'>▼</span> Checkpoints <span class='count'>{len(checkpoints)}</span></div>")
        parts.append("      <div class='sidebar-list' id='checkpoints-list'>")
        for cp in checkpoints:
            cp_name = cp.get("name", "unnamed")
            parts.append(f"        <div class='checkpoint-item'>{escape_html(cp_name)}</div>")
        parts.append("      </div>")
        parts.append("    </div>")

    # Flow Tests navigation (collapsible, collapsed by default)
    if all_tests_nav and all_tests_nav.get('flows'):
        flows = all_tests_nav['flows']
        parts.append("    <div class='sidebar-section'>")
        parts.append(f"      <div class='sidebar-title collapsed' id='flows-title' onclick=\"toggleSection('flows')\"><span class='arrow'>▼</span> Flow Tests <span class='count'>{len(flows)}</span></div>")
        parts.append("      <div class='sidebar-list collapsed' id='flows-list'>")
        parts.append("        <ul>")
        for f in flows:
            is_current = current_test_path and f['path'] == current_test_path
            current_class = " current" if is_current else ""
            parts.append(f"          <li><a href='../{f['path']}' class='nav-link{current_class}' title='{escape_html(f['name'])}'>{escape_html(f['name'])}</a></li>")
        parts.append("        </ul>")
        parts.append("      </div>")
        parts.append("    </div>")

    # Screen Tests navigation (collapsible, collapsed by default)
    if all_tests_nav and all_tests_nav.get('screens'):
        screens = all_tests_nav['screens']
        parts.append("    <div class='sidebar-section'>")
        parts.append(f"      <div class='sidebar-title screen collapsed' id='screens-title' onclick=\"toggleSection('screens')\"><span class='arrow'>▼</span> Screen Tests <span class='count'>{len(screens)}</span></div>")
        parts.append("      <div class='sidebar-list collapsed' id='screens-list'>")
        parts.append("        <ul>")
        for s in screens:
            is_current = current_test_path and s['path'] == current_test_path
            current_class = " current" if is_current else ""
            parts.append(f"          <li><a href='../{s['path']}' class='nav-link{current_class}' title='{escape_html(s['name'])}'>{escape_html(s['name'])}</a></li>")
        parts.append("        </ul>")
        parts.append("      </div>")
        parts.append("    </div>")

    # Documents navigation (collapsible, collapsed by default)
    if all_tests_nav and all_tests_nav.get('documents'):
        documents = all_tests_nav['documents']
        parts.append("    <div class='sidebar-section'>")
        parts.append(f"      <div class='sidebar-title doc collapsed' id='documents-title' onclick=\"toggleSection('documents')\"><span class='arrow'>▼</span> Documents <span class='count'>{len(documents)}</span></div>")
        parts.append("      <div class='sidebar-list collapsed' id='documents-list'>")
        parts.append("        <ul>")
        for d in documents:
            parts.append(f"          <li><a href='../{d['path']}' class='nav-link' title='{escape_html(d['name'])}'>{escape_html(d['name'])}</a></li>")
        parts.append("        </ul>")
        parts.append("      </div>")
        parts.append("    </div>")

    # API Docs navigation (collapsible, collapsed by default, with subdir grouping)
    if all_tests_nav and all_tests_nav.get('api_doc_categories'):
        for category_name, category_docs in all_tests_nav['api_doc_categories'].items():
            display_name = category_name.upper() if len(category_name) <= 3 else category_name.title()
            cat_id = f"flow-api-{_make_safe_id(category_name)}"
            parts.append("    <div class='sidebar-section'>")
            parts.append(f"      <div class='sidebar-title api collapsed' id='{cat_id}-title' onclick=\"toggleSection('{cat_id}')\"><span class='arrow'>▼</span> {display_name} <span class='count'>{len(category_docs)}</span></div>")
            parts.append(f"      <div class='sidebar-list collapsed' id='{cat_id}-list'>")
            has_subdirs = any(d.get('subdir') for d in category_docs)
            if has_subdirs:
                parts.extend(_render_api_docs_with_subgroups(
                    category_docs, href_prefix='../', current_path=current_test_path, id_prefix=cat_id))
            else:
                parts.append("        <ul>")
                for d in category_docs:
                    parts.append(f"          <li><a href='../{d['path']}' class='nav-link' title='{escape_html(d['name'])}'>{escape_html(d['name'])}</a></li>")
                parts.append("        </ul>")
            parts.append("      </div>")
            parts.append("    </div>")
    elif all_tests_nav and all_tests_nav.get('api_docs'):
        api_docs = all_tests_nav['api_docs']
        parts.append("    <div class='sidebar-section'>")
        parts.append(f"      <div class='sidebar-title api collapsed' id='api-docs-title' onclick=\"toggleSection('api-docs')\"><span class='arrow'>▼</span> API Docs <span class='count'>{len(api_docs)}</span></div>")
        parts.append("      <div class='sidebar-list collapsed' id='api-docs-list'>")
        parts.append("        <ul>")
        for d in api_docs:
            parts.append(f"          <li><a href='../{d['path']}' class='nav-link' title='{escape_html(d['name'])}'>{escape_html(d['name'])}</a></li>")
        parts.append("        </ul>")
        parts.append("      </div>")
        parts.append("    </div>")

    # Figma Screens navigation (collapsible, collapsed by default, grouped by canvas)
    if all_tests_nav and all_tests_nav.get('figma_screens'):
        parts.extend(_render_figma_sidebar_section(
            all_tests_nav['figma_screens'], href_prefix='../', current_path=current_test_path))

    parts.append("  </nav>")
    return parts


def generate_spec_sidebar(
    title: str,
    all_tests_nav: dict | None = None,
    current_path: str | None = None
) -> list[str]:
    """
    Generate sidebar HTML for spec pages.

    Args:
        title: Page title
        all_tests_nav: Navigation data {'screens': [...], 'flows': [...], 'specs': [...], 'components': [...]}
        current_path: Current page's relative HTML path

    Returns:
        List of HTML strings for the sidebar
    """
    rel_root = _get_rel_root(current_path)

    parts = []
    parts.append("  <nav class='sidebar'>")
    parts.append(f"    <a href='{rel_root}index.html' class='back-link'>&larr; Back to Index</a>")
    parts.append(f"    <h2>{escape_html(title)}</h2>")

    # Screen Specs navigation (collapsible, expanded by default for spec pages)
    if all_tests_nav and all_tests_nav.get('specs'):
        specs = all_tests_nav['specs']
        parts.append("    <div class='sidebar-section'>")
        parts.append(f"      <div class='sidebar-title spec' id='specs-title' onclick=\"toggleSection('specs')\"><span class='arrow'>▼</span> Screen Specs <span class='count'>{len(specs)}</span></div>")
        parts.append("      <div class='sidebar-list' id='specs-list'>")
        parts.append("        <ul>")
        for s in specs:
            is_current = current_path and s['path'] == current_path
            current_class = " current" if is_current else ""
            parts.append(f"          <li><a href='{rel_root}{s['path']}' class='nav-link{current_class}' title='{escape_html(s['name'])}'>{escape_html(s['name'])}</a></li>")
        parts.append("        </ul>")
        parts.append("      </div>")
        parts.append("    </div>")

    # Components navigation (collapsible, collapsed by default)
    if all_tests_nav and all_tests_nav.get('components'):
        components = all_tests_nav['components']
        parts.append("    <div class='sidebar-section'>")
        parts.append(f"      <div class='sidebar-title component collapsed' id='components-title' onclick=\"toggleSection('components')\"><span class='arrow'>▼</span> Components <span class='count'>{len(components)}</span></div>")
        parts.append("      <div class='sidebar-list collapsed' id='components-list'>")
        parts.append("        <ul>")
        for c in components:
            is_current = current_path and c['path'] == current_path
            current_class = " current" if is_current else ""
            parts.append(f"          <li><a href='{rel_root}{c['path']}' class='nav-link{current_class}' title='{escape_html(c['name'])}'>{escape_html(c['name'])}</a></li>")
        parts.append("        </ul>")
        parts.append("      </div>")
        parts.append("    </div>")

    # App-specific sections (multi-app mode)
    if all_tests_nav and all_tests_nav.get('apps'):
        for app_name, app_data in all_tests_nav['apps'].items():
            safe_app_id = _make_safe_id(app_name)
            total_items = sum(
                sum(len(files) for files in v.values()) if isinstance(v, dict) else len(v)
                for v in app_data.values()
            )
            parts.append("    <div class='sidebar-section'>")
            parts.append(f"      <div class='sidebar-title app collapsed' id='app-{safe_app_id}-title' onclick=\"toggleSection('app-{safe_app_id}')\"><span class='arrow'>▼</span> {escape_html(app_name)} <span class='count'>{total_items}</span></div>")
            parts.append(f"      <div class='sidebar-list collapsed' id='app-{safe_app_id}-list'>")

            if app_data.get('specs'):
                app_specs = app_data['specs']
                spec_id = f"app-{safe_app_id}-specs"
                parts.append(f"        <div class='sidebar-subsection'>")
                parts.append(f"          <div class='sidebar-subtitle collapsed' id='{spec_id}-title' onclick=\"toggleSection('{spec_id}')\"><span class='arrow'>▼</span> Screen Specs <span class='count'>{len(app_specs)}</span></div>")
                parts.append(f"          <div class='sidebar-list collapsed' id='{spec_id}-list'>")
                parts.append("            <ul>")
                for s in app_specs:
                    is_current = current_path and s['path'] == current_path
                    current_class = " current" if is_current else ""
                    parts.append(f"              <li><a href='{rel_root}{s['path']}' class='nav-link{current_class}' title='{escape_html(s['name'])}'>{escape_html(s['name'])}</a></li>")
                parts.append("            </ul>")
                parts.append("          </div>")
                parts.append("        </div>")

            if app_data.get('components'):
                app_comps = app_data['components']
                comp_id = f"app-{safe_app_id}-components"
                parts.append(f"        <div class='sidebar-subsection'>")
                parts.append(f"          <div class='sidebar-subtitle collapsed' id='{comp_id}-title' onclick=\"toggleSection('{comp_id}')\"><span class='arrow'>▼</span> Components <span class='count'>{len(app_comps)}</span></div>")
                parts.append(f"          <div class='sidebar-list collapsed' id='{comp_id}-list'>")
                parts.append("            <ul>")
                for c in app_comps:
                    is_current = current_path and c['path'] == current_path
                    current_class = " current" if is_current else ""
                    parts.append(f"              <li><a href='{rel_root}{c['path']}' class='nav-link{current_class}' title='{escape_html(c['name'])}'>{escape_html(c['name'])}</a></li>")
                parts.append("            </ul>")
                parts.append("          </div>")
                parts.append("        </div>")

            # App markdown files by directory
            if app_data.get('md_files_by_dir'):
                for dir_name, md_files in app_data['md_files_by_dir'].items():
                    md_id = f"app-{safe_app_id}-md-{_make_safe_id(dir_name)}"
                    clean_name = dir_name.replace('-', ' ').replace('_', ' ')
                    display_name = clean_name.title() if len(dir_name) > 3 else clean_name.upper()
                    parts.append(f"        <div class='sidebar-subsection'>")
                    parts.append(f"          <div class='sidebar-subtitle collapsed' id='{md_id}-title' onclick=\"toggleSection('{md_id}')\"><span class='arrow'>▼</span> {display_name} <span class='count'>{len(md_files)}</span></div>")
                    parts.append(f"          <div class='sidebar-list collapsed' id='{md_id}-list'>")
                    parts.append("            <ul>")
                    for f in md_files:
                        parts.append(f"              <li><a href='{rel_root}{f['path']}' class='nav-link' title='{escape_html(f['name'])}'>{escape_html(f['name'])}</a></li>")
                    parts.append("            </ul>")
                    parts.append("          </div>")
                    parts.append("        </div>")

            if app_data.get('figma_screens'):
                parts.extend(_render_figma_sidebar_section(
                    app_data['figma_screens'], href_prefix=rel_root, current_path=current_path,
                    section_id_prefix=f"app-{safe_app_id}-figma"))

            parts.append("      </div>")
            parts.append("    </div>")

    # Flow Tests navigation (collapsible, collapsed by default)
    if all_tests_nav and all_tests_nav.get('flows'):
        flows = all_tests_nav['flows']
        parts.append("    <div class='sidebar-section'>")
        parts.append(f"      <div class='sidebar-title flow collapsed' id='flows-title' onclick=\"toggleSection('flows')\"><span class='arrow'>▼</span> Flow Tests <span class='count'>{len(flows)}</span></div>")
        parts.append("      <div class='sidebar-list collapsed' id='flows-list'>")
        parts.append("        <ul>")
        for f in flows:
            parts.append(f"          <li><a href='{rel_root}{f['path']}' class='nav-link' title='{escape_html(f['name'])}'>{escape_html(f['name'])}</a></li>")
        parts.append("        </ul>")
        parts.append("      </div>")
        parts.append("    </div>")

    # Screen Tests navigation (collapsible, collapsed by default)
    if all_tests_nav and all_tests_nav.get('screens'):
        screens = all_tests_nav['screens']
        parts.append("    <div class='sidebar-section'>")
        parts.append(f"      <div class='sidebar-title collapsed' id='screens-title' onclick=\"toggleSection('screens')\"><span class='arrow'>▼</span> Screen Tests <span class='count'>{len(screens)}</span></div>")
        parts.append("      <div class='sidebar-list collapsed' id='screens-list'>")
        parts.append("        <ul>")
        for s in screens:
            parts.append(f"          <li><a href='{rel_root}{s['path']}' class='nav-link' title='{escape_html(s['name'])}'>{escape_html(s['name'])}</a></li>")
        parts.append("        </ul>")
        parts.append("      </div>")
        parts.append("    </div>")

    # Figma Screens navigation (collapsible, collapsed by default, grouped by canvas)
    if all_tests_nav and all_tests_nav.get('figma_screens'):
        parts.extend(_render_figma_sidebar_section(
            all_tests_nav['figma_screens'], href_prefix=rel_root, current_path=current_path))

    parts.append("  </nav>")
    return parts


def generate_index_sidebar(
    title: str,
    flow_files: list[dict],
    screen_files: list[dict],
    has_mermaid_diagram: bool = False,
    document_files: list[dict] | None = None,
    api_doc_categories: dict[str, list[dict]] | None = None,
    spec_files: list[dict] | None = None,
    component_files: list[dict] | None = None,
    md_files_by_dir: dict[str, list[dict]] | None = None,
    figma_files: list[dict] | None = None,
    apps_nav: dict[str, dict] | None = None
) -> list[str]:
    """
    Generate sidebar HTML for index page.

    Args:
        title: Page title
        flow_files: List of flow test file dicts
        screen_files: List of screen test file dicts
        has_mermaid_diagram: Whether a Mermaid diagram was generated
        document_files: List of document file dicts
        api_doc_categories: Dict of category name -> list of API doc file dicts
        spec_files: List of screen specification file dicts
        component_files: List of component specification file dicts
        md_files_by_dir: Dict of directory name -> list of markdown file dicts
        figma_files: List of Figma screen file dicts

    Returns:
        List of HTML strings for the sidebar
    """
    parts = []
    parts.append("  <nav class='sidebar'>")
    parts.append(f"    <h2>{escape_html(title)}</h2>")

    # Flow Diagram link (if available)
    if has_mermaid_diagram:
        parts.append("    <div class='sidebar-diagram-link'>")
        parts.append("      <a href='diagram.html'>Flow Diagram</a>")
        parts.append("    </div>")

    # === Other files (top) ===

    # Sidebar - Screen Specs (collapsible, starts collapsed)
    if spec_files:
        parts.append("    <div class='sidebar-section'>")
        parts.append(f"      <div class='sidebar-title spec collapsed' id='sidebar-specs-title' onclick=\"toggleSidebar('specs')\"><span class='arrow'>▼</span>Screen Specs <span class='count'>{len(spec_files)}</span></div>")
        parts.append("      <div class='sidebar-list collapsed' id='sidebar-specs-list'>")
        parts.append("        <ul>")
        for s in spec_files:
            parts.append(f"          <li><a href='{s['path']}' title='{escape_html(s['name'])}'>{escape_html(s['name'])}</a></li>")
        parts.append("        </ul>")
        parts.append("      </div>")
        parts.append("    </div>")

    # Sidebar - Components (collapsible, starts collapsed)
    if component_files:
        parts.append("    <div class='sidebar-section'>")
        parts.append(f"      <div class='sidebar-title component collapsed' id='sidebar-components-title' onclick=\"toggleSidebar('components')\"><span class='arrow'>▼</span>Components <span class='count'>{len(component_files)}</span></div>")
        parts.append("      <div class='sidebar-list collapsed' id='sidebar-components-list'>")
        parts.append("        <ul>")
        for c in component_files:
            parts.append(f"          <li><a href='{c['path']}' title='{escape_html(c['name'])}'>{escape_html(c['name'])}</a></li>")
        parts.append("        </ul>")
        parts.append("      </div>")
        parts.append("    </div>")

    # Sidebar - Documents (collapsible, starts collapsed)
    if document_files:
        parts.append("    <div class='sidebar-section'>")
        parts.append(f"      <div class='sidebar-title doc collapsed' id='sidebar-documents-title' onclick=\"toggleSidebar('documents')\"><span class='arrow'>▼</span>Documents <span class='count'>{len(document_files)}</span></div>")
        parts.append("      <div class='sidebar-list collapsed' id='sidebar-documents-list'>")
        parts.append("        <ul>")
        for d in document_files:
            parts.append(f"          <li><a href='{d['path']}' title='{escape_html(d['name'])}'>{escape_html(d['name'])}</a></li>")
        parts.append("        </ul>")
        parts.append("      </div>")
        parts.append("    </div>")

    # Sidebar - API Doc categories (one section per directory, with subdir grouping)
    if api_doc_categories:
        for category_name, category_docs in api_doc_categories.items():
            display_name = category_name.upper() if len(category_name) <= 3 else category_name.title()
            sidebar_id = f"sidebar-api-{category_name}"
            parts.append("    <div class='sidebar-section'>")
            parts.append(f"      <div class='sidebar-title api collapsed' id='{sidebar_id}-title' onclick=\"toggleSidebar('api-{category_name}')\"><span class='arrow'>▼</span>{display_name} <span class='count'>{len(category_docs)}</span></div>")
            parts.append(f"      <div class='sidebar-list collapsed' id='{sidebar_id}-list'>")
            # Add ER Diagram link for DB category
            if category_name.lower() == 'db':
                parts.append(f"        <div class='sidebar-erd-link'><a href='{category_name}/erd.html'>ER Diagram</a></div>")
            has_subdirs = any(d.get('subdir') for d in category_docs)
            if has_subdirs:
                parts.extend(_render_api_docs_with_subgroups(
                    category_docs, href_prefix='', current_path=None, id_prefix=sidebar_id))
            else:
                parts.append("        <ul>")
                for d in category_docs:
                    parts.append(f"          <li><a href='{d['path']}' title='{escape_html(d['name'])}'>{escape_html(d['name'])}</a></li>")
                parts.append("        </ul>")
            parts.append("      </div>")
            parts.append("    </div>")

    # Sidebar - Markdown files grouped by directory (collapsible, starts collapsed, with subdir grouping)
    if md_files_by_dir:
        for dir_name, md_files in md_files_by_dir.items():
            dir_id = f"sidebar-md-{dir_name.replace('/', '-').replace(' ', '_')}"
            clean_name = dir_name.replace('-', ' ').replace('_', ' ')
            display_name = clean_name.title() if len(dir_name) > 3 else clean_name.upper()
            parts.append("    <div class='sidebar-section'>")
            parts.append(f"      <div class='sidebar-title md collapsed' id='{dir_id}-title' onclick=\"toggleSidebar('md-{dir_name}')\"><span class='arrow'>▼</span>{display_name} <span class='count'>{len(md_files)}</span></div>")
            parts.append(f"      <div class='sidebar-list collapsed' id='{dir_id}-list'>")
            has_subdirs = any(f.get('subdir') for f in md_files)
            if has_subdirs:
                parts.extend(_render_api_docs_with_subgroups(
                    md_files, href_prefix='', current_path=None, id_prefix=dir_id))
            else:
                parts.append("        <ul>")
                for f in md_files:
                    parts.append(f"          <li><a href='{f['path']}' title='{escape_html(f['name'])}'>{escape_html(f['name'])}</a></li>")
                parts.append("        </ul>")
            parts.append("      </div>")
            parts.append("    </div>")

    # Sidebar - Figma Screens (collapsible, starts collapsed, grouped by canvas)
    if figma_files:
        parts.extend(_render_figma_sidebar_section(
            figma_files, href_prefix='', current_path=None))

    # === App-specific sections (multi-app mode) ===
    if apps_nav:
        parts.append("    <hr class='sidebar-divider'>")
        for app_name, app_data in apps_nav.items():
            safe_app_id = _make_safe_id(app_name)
            total_items = sum(
                sum(len(files) for files in v.values()) if isinstance(v, dict) else len(v)
                for v in app_data.values()
            )
            parts.append("    <div class='sidebar-section'>")
            parts.append(f"      <div class='sidebar-title app collapsed' id='sidebar-app-{safe_app_id}-title' onclick=\"toggleSidebar('app-{safe_app_id}')\"><span class='arrow'>▼</span>{escape_html(app_name)} <span class='count'>{total_items}</span></div>")
            parts.append(f"      <div class='sidebar-list collapsed' id='sidebar-app-{safe_app_id}-list'>")

            # App specs
            if app_data.get('specs'):
                app_specs = app_data['specs']
                spec_id = f"sidebar-app-{safe_app_id}-specs"
                parts.append(f"        <div class='sidebar-subsection'>")
                parts.append(f"          <div class='sidebar-subtitle collapsed' id='{spec_id}-title' onclick=\"toggleSection('{spec_id}')\"><span class='arrow'>▼</span> Screen Specs <span class='count'>{len(app_specs)}</span></div>")
                parts.append(f"          <div class='sidebar-list collapsed' id='{spec_id}-list'>")
                parts.append("            <ul>")
                for s in app_specs:
                    parts.append(f"              <li><a href='{s['path']}' title='{escape_html(s['name'])}'>{escape_html(s['name'])}</a></li>")
                parts.append("            </ul>")
                parts.append("          </div>")
                parts.append("        </div>")

            # App components
            if app_data.get('components'):
                app_comps = app_data['components']
                comp_id = f"sidebar-app-{safe_app_id}-components"
                parts.append(f"        <div class='sidebar-subsection'>")
                parts.append(f"          <div class='sidebar-subtitle collapsed' id='{comp_id}-title' onclick=\"toggleSection('{comp_id}')\"><span class='arrow'>▼</span> Components <span class='count'>{len(app_comps)}</span></div>")
                parts.append(f"          <div class='sidebar-list collapsed' id='{comp_id}-list'>")
                parts.append("            <ul>")
                for c in app_comps:
                    parts.append(f"              <li><a href='{c['path']}' title='{escape_html(c['name'])}'>{escape_html(c['name'])}</a></li>")
                parts.append("            </ul>")
                parts.append("          </div>")
                parts.append("        </div>")

            # App markdown files by directory
            if app_data.get('md_files_by_dir'):
                for dir_name, md_files in app_data['md_files_by_dir'].items():
                    md_id = f"sidebar-app-{safe_app_id}-md-{_make_safe_id(dir_name)}"
                    clean_name = dir_name.replace('-', ' ').replace('_', ' ')
                    display_name = clean_name.title() if len(dir_name) > 3 else clean_name.upper()
                    parts.append(f"        <div class='sidebar-subsection'>")
                    parts.append(f"          <div class='sidebar-subtitle collapsed' id='{md_id}-title' onclick=\"toggleSection('{md_id}')\"><span class='arrow'>▼</span> {display_name} <span class='count'>{len(md_files)}</span></div>")
                    parts.append(f"          <div class='sidebar-list collapsed' id='{md_id}-list'>")
                    has_subdirs = any(f.get('subdir') for f in md_files)
                    if has_subdirs:
                        parts.extend(_render_api_docs_with_subgroups(
                            md_files, href_prefix='', current_path=None, id_prefix=md_id))
                    else:
                        parts.append("            <ul>")
                        for f in md_files:
                            parts.append(f"              <li><a href='{f['path']}' title='{escape_html(f['name'])}'>{escape_html(f['name'])}</a></li>")
                        parts.append("            </ul>")
                    parts.append("          </div>")
                    parts.append("        </div>")

            # App figma screens
            if app_data.get('figma_screens'):
                parts.extend(_render_figma_sidebar_section(
                    app_data['figma_screens'], href_prefix='', current_path=None,
                    section_id_prefix=f"app-{safe_app_id}-figma"))

            parts.append("      </div>")
            parts.append("    </div>")

    # === Test files (bottom) ===

    # Sidebar - Flow Tests (collapsible, starts collapsed)
    if flow_files:
        parts.append("    <div class='sidebar-section'>")
        parts.append(f"      <div class='sidebar-title flow collapsed' id='sidebar-flows-title' onclick=\"toggleSidebar('flows')\"><span class='arrow'>▼</span>Flow Tests <span class='count'>{len(flow_files)}</span></div>")
        parts.append("      <div class='sidebar-list collapsed' id='sidebar-flows-list'>")
        parts.append("        <ul>")
        for f in flow_files:
            parts.append(f"          <li><a href='{f['path']}' title='{escape_html(f['name'])}'>{escape_html(f['name'])}</a></li>")
        parts.append("        </ul>")
        parts.append("      </div>")
        parts.append("    </div>")

    # Sidebar - Screen Tests (collapsible, starts collapsed)
    if screen_files:
        parts.append("    <div class='sidebar-section'>")
        parts.append(f"      <div class='sidebar-title collapsed' id='sidebar-screens-title' onclick=\"toggleSidebar('screens')\"><span class='arrow'>▼</span>Screen Tests <span class='count'>{len(screen_files)}</span></div>")
        parts.append("      <div class='sidebar-list collapsed' id='sidebar-screens-list'>")
        parts.append("        <ul>")
        for f in screen_files:
            parts.append(f"          <li><a href='{f['path']}' title='{escape_html(f['name'])}'>{escape_html(f['name'])}</a></li>")
        parts.append("        </ul>")
        parts.append("      </div>")
        parts.append("    </div>")

    parts.append("  </nav>")
    return parts
