"""Sidebar generation for HTML documentation."""

from __future__ import annotations


def escape_html(text: str) -> str:
    """Escape HTML special characters."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


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

    # API Docs navigation (collapsible, collapsed by default)
    if all_tests_nav and all_tests_nav.get('api_docs'):
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

    # API Docs navigation (collapsible, collapsed by default)
    if all_tests_nav and all_tests_nav.get('api_docs'):
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

    parts.append("  </nav>")
    return parts


def generate_index_sidebar(
    title: str,
    flow_files: list[dict],
    screen_files: list[dict],
    has_mermaid_diagram: bool = False,
    document_files: list[dict] | None = None,
    api_doc_categories: dict[str, list[dict]] | None = None
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

    # Sidebar - Flow Tests first (collapsible, starts collapsed)
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

    # Sidebar - API Doc categories (one section per directory)
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
            parts.append("        <ul>")
            for d in category_docs:
                parts.append(f"          <li><a href='{d['path']}' title='{escape_html(d['name'])}'>{escape_html(d['name'])}</a></li>")
            parts.append("        </ul>")
            parts.append("      </div>")
            parts.append("    </div>")

    parts.append("  </nav>")
    return parts
