"""CSS styles for HTML documentation generation."""


def get_common_styles() -> list[str]:
    """Get common CSS styles shared across all HTML pages."""
    return [
        "    * { box-sizing: border-box; }",
        "    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 0; line-height: 1.6; display: flex; }",
    ]


def get_sidebar_base_styles() -> list[str]:
    """Get base sidebar styles shared across page types (dark theme)."""
    return [
        "    /* Sidebar - dark theme */",
        "    .sidebar { width: 280px; min-width: 280px; height: 100vh; position: fixed; top: 0; left: 0; background: #1e293b; color: #e2e8f0; overflow-y: auto; padding: 20px; box-shadow: 2px 0 5px rgba(0,0,0,0.1); }",
        "    .sidebar h2 { font-size: 1.1em; color: #f8fafc; margin: 0 0 15px 0; padding-bottom: 10px; border-bottom: 1px solid #475569; }",
        "    .sidebar-section { margin-bottom: 15px; }",
        "    .sidebar-title { font-size: 0.85em; color: #94a3b8; font-weight: 600; cursor: pointer; display: flex; align-items: center; gap: 0.5rem; padding: 8px 10px; border-radius: 6px; margin-bottom: 5px; transition: background-color 0.2s; }",
        "    .sidebar-title:hover { background: #334155; }",
        "    .sidebar-title .arrow { transition: transform 0.3s; font-size: 0.7em; }",
        "    .sidebar-title.collapsed .arrow { transform: rotate(-90deg); }",
        "    .sidebar-title .count { background: #475569; color: #e2e8f0; padding: 2px 8px; border-radius: 10px; font-size: 0.75em; margin-left: auto; }",
        "    .sidebar-title.flow { color: #60a5fa; }",
        "    .sidebar-title.spec { color: #a78bfa; }",
        "    .sidebar-title.component { color: #34d399; }",
        "    .sidebar-title.doc { color: #4ade80; }",
        "    .sidebar-title.api { color: #fb923c; }",
        "    .sidebar-title.md { color: #f97316; }",
        "    .sidebar-title.figma { color: #f472b6; }",
        "    .sidebar-title.app { color: #38bdf8; font-weight: bold; }",
        "    hr.sidebar-divider { border: none; border-top: 1px solid #475569; margin: 8px 12px; }",
        "    .sidebar-subsection { margin-left: 8px; margin-bottom: 2px; }",
        "    .sidebar-subtitle { font-size: 0.8em; color: #94a3b8; cursor: pointer; display: flex; align-items: center; gap: 0.4rem; padding: 5px 8px; border-radius: 4px; transition: background-color 0.2s; }",
        "    .sidebar-subtitle:hover { background: #334155; }",
        "    .sidebar-subtitle .arrow { transition: transform 0.3s; font-size: 0.65em; }",
        "    .sidebar-subtitle.collapsed .arrow { transform: rotate(-90deg); }",
        "    .sidebar-subtitle .count { background: #475569; color: #e2e8f0; padding: 1px 6px; border-radius: 8px; font-size: 0.7em; margin-left: auto; }",
        "    .sidebar-list { overflow: hidden; padding: 0; }",
        "    .sidebar-list.collapsed { display: none; }",
        "    .sidebar ul { list-style: none; padding: 0; margin: 0; }",
        "    .sidebar li { margin: 0; display: flex; align-items: center; }",
        "    .sidebar li .doc-link { margin-left: auto; padding: 2px 6px; font-size: 0.9em; }",
        "    .back-link { display: block; padding: 10px 12px; margin-bottom: 15px; color: #94a3b8; font-size: 0.9em; text-decoration: none; border-bottom: 1px solid #475569; border-radius: 4px; transition: background-color 0.2s; }",
        "    .back-link:hover { background: #334155; color: #f8fafc; }",
        "    .nav-link { display: block; padding: 6px 12px 6px 24px; color: #cbd5e1; text-decoration: none; border-radius: 4px; font-size: 0.85em; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; transition: background-color 0.2s; }",
        "    .nav-link:hover { background: #334155; color: #f8fafc; }",
        "    .nav-link.current { background: #3b82f6; color: #fff; }",
    ]


def get_nav_sidebar_styles() -> list[str]:
    """Get sidebar styles for the nav-list page family (DB tables, ERD,
    contract check).

    Same palette as get_sidebar_base_styles(); only the markup differs
    (nav-section / nav-list instead of collapsible sidebar-section), so the
    whole generated site shares one sidebar look.
    """
    return [
        "    /* Sidebar - dark theme (nav-list markup) */",
        "    .sidebar { width: 280px; min-width: 280px; height: 100vh; position: fixed; top: 0; left: 0; background: #1e293b; color: #e2e8f0; overflow-y: auto; padding: 20px; box-shadow: 2px 0 5px rgba(0,0,0,0.1); }",
        "    .sidebar-header { padding-bottom: 15px; margin-bottom: 15px; border-bottom: 1px solid #475569; }",
        "    .sidebar .back-link { display: block; color: #94a3b8; text-decoration: none; font-size: 0.9em; padding: 4px 0; transition: color 0.2s; }",
        "    .sidebar .back-link:hover { color: #f8fafc; }",
        "    .sidebar-nav { padding: 0; }",
        "    .nav-section { margin-bottom: 20px; }",
        "    .nav-section-title { font-size: 0.75em; font-weight: 600; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 8px; }",
        "    .nav-list { list-style: none; }",
        "    .nav-list li { margin: 2px 0; }",
        "    .nav-list li a { display: block; padding: 6px 12px; color: #cbd5e1; text-decoration: none; border-radius: 4px; font-size: 0.85em; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; transition: background-color 0.2s; }",
        "    .nav-list li a:hover { background: #334155; color: #f8fafc; }",
        "    .nav-list li.active a { background: #3b82f6; color: #fff; }",
    ]


def get_nav_sidebar_scroll_script() -> list[str]:
    """Bring the active nav entry into view inside the sidebar on load.

    scrollTop is set directly instead of calling scrollIntoView: the sidebar
    is position:fixed, so letting the browser walk scrollable ancestors can
    move the document rather than the list.
    """
    return [
        "  <script>",
        "    document.addEventListener('DOMContentLoaded', function () {",
        "      var sidebar = document.querySelector('.sidebar');",
        "      var active = sidebar && sidebar.querySelector('.nav-list li.active a');",
        "      if (!active) return;",
        "      var top = active.getBoundingClientRect().top",
        "        - sidebar.getBoundingClientRect().top + sidebar.scrollTop;",
        "      sidebar.scrollTop = Math.max(",
        "        0, top - sidebar.clientHeight / 2 + active.offsetHeight / 2);",
        "    });",
        "  </script>",
    ]


def get_responsive_styles() -> list[str]:
    """Get responsive CSS styles."""
    return [
        "    /* Responsive */",
        "    @media (max-width: 768px) {",
        "      .sidebar { display: none; }",
        "      .main-content { margin-left: 0; padding: 20px; }",
        "    }",
    ]


def get_toggle_script() -> list[str]:
    """Get the toggle section JavaScript."""
    return [
        "  <script>",
        "    function toggleSection(id) {",
        "      const title = document.getElementById(id + '-title');",
        "      const list = document.getElementById(id + '-list');",
        "      title.classList.toggle('collapsed');",
        "      list.classList.toggle('collapsed');",
        "    }",
        "    document.addEventListener('DOMContentLoaded', function() {",
        "      var cur = document.querySelector('.sidebar .nav-link.current');",
        "      if (!cur) return;",
        "      var el = cur.closest('.sidebar-list.collapsed, .sidebar-list');",
        "      while (el) {",
        "        if (el.classList.contains('collapsed')) {",
        "          el.classList.remove('collapsed');",
        "          var titleId = el.id.replace('-list', '-title');",
        "          var t = document.getElementById(titleId);",
        "          if (t) t.classList.remove('collapsed');",
        "        }",
        "        var parent = el.parentElement ? el.parentElement.closest('.sidebar-list') : null;",
        "        el = parent;",
        "      }",
        "      setTimeout(function() { cur.scrollIntoView({block:'center',behavior:'smooth'}); }, 100);",
        "    });",
        "  </script>",
    ]


def get_screen_styles() -> list[str]:
    """Get CSS styles for screen test HTML pages."""
    styles = get_common_styles()
    styles.extend(get_sidebar_base_styles())
    styles.extend([
        "    .sidebar a { display: flex; align-items: flex-start; padding: 8px 12px; color: #cbd5e1; text-decoration: none; border-radius: 6px; font-size: 0.9em; transition: all 0.2s; }",
        "    .sidebar a:hover { background: #334155; color: #f8fafc; }",
        "    .sidebar a.active { background: #3b82f6; color: white; }",
        "    .case-number { flex-shrink: 0; width: 24px; height: 24px; line-height: 24px; text-align: center; background: #475569; color: #e2e8f0; border-radius: 50%; font-size: 0.75em; font-weight: 600; margin-right: 8px; }",
        "    .case-name { flex: 1; word-break: break-word; }",
        "    .sidebar a:hover .case-number { background: #64748b; }",
        "    .sidebar a.active .case-number { background: rgba(255,255,255,0.3); }",
        "    /* Main content */",
        "    .main-content { margin-left: 280px; padding: 30px 40px; max-width: 900px; flex: 1; }",
        "    h1 { color: #333; border-bottom: 2px solid #007AFF; padding-bottom: 10px; margin-top: 0; }",
        "    h2 { color: #555; margin-top: 30px; }",
        "    h3 { color: #666; margin-top: 25px; scroll-margin-top: 20px; }",
        "    table { border-collapse: collapse; width: 100%; margin: 15px 0; }",
        "    th, td { border: 1px solid #ddd; padding: 10px; text-align: left; }",
        "    th { background: #f5f5f5; }",
        "    code { background: #f0f0f0; padding: 2px 6px; border-radius: 3px; font-size: 0.9em; }",
        "    .info { background: #f9f9f9; padding: 15px; border-radius: 5px; margin: 15px 0; }",
        "    .description { color: #666; font-style: italic; margin-bottom: 20px; }",
        "    .action { color: #007AFF; font-weight: 500; }",
        "    .assert { color: #34C759; font-weight: 500; }",
        "    .summary { color: #333; margin-bottom: 10px; }",
        "    .case-name-label { color: #888; font-size: 0.9em; margin: -10px 0 15px 0; }",
        "    .case-name-label code { background: #f5f5f5; color: #666; }",
        "    .test-description { color: #666; font-size: 0.95rem; font-weight: normal; max-width: 75ch; margin: 5px 0 20px 0; white-space: pre-wrap; }",
        "    .desc-section { margin: 10px 0; padding-left: 10px; border-left: 3px solid #e0e0e0; }",
        "    .desc-section ul, .desc-section ol { margin: 5px 0; padding-left: 25px; }",
        "    .notes { color: #666; font-style: italic; background: #fffbf0; padding: 10px; border-radius: 5px; }",
        "    a { color: #007AFF; text-decoration: none; }",
        "    a:hover { text-decoration: underline; }",
        "    /* Args display */",
        "    .case-args, .step-args { background: #f0f7ff; padding: 10px 15px; border-radius: 5px; margin: 10px 0; border-left: 3px solid #007AFF; }",
        "    .case-args ul, .step-args ul { margin: 5px 0 0 0; padding-left: 20px; }",
        "    .case-args li, .step-args li { margin: 3px 0; }",
    ])
    styles.extend(get_responsive_styles())
    return styles


def get_unit_styles() -> list[str]:
    """CSS for unit contract (hand-written business logic) pages.

    Built on the screen page's styles rather than beside them: a unit target
    page is the same shape — a sidebar of case names and a table of cases —
    and a second theme would make two pages that document the same project
    look like two products.

    Only the per-face status badges are new. Their colours carry the one
    distinction the page exists to make, so `missing` and `never_runs` are
    deliberately NOT the same red: a case that is declared and unwritten and
    a case that is written but which the runner will never execute need
    opposite actions from the reader.
    """
    styles = get_screen_styles()
    styles.extend([
        # Only unit pages render this sidebar section, so the rule lives here
        # rather than in the shared sidebar base — adding it there would
        # restyle every screen and flow page for a section they do not have.
        "    .sidebar-title.unit { color: #a5b4fc; }",
        "    /* Unit contract status badges */",
        "    .status { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 0.8em; font-weight: 600; white-space: nowrap; }",
        "    .status-implemented { background: #e6f7ed; color: #1d7a44; }",
        "    .status-missing { background: #fdeaea; color: #b3261e; }",
        "    .status-never_runs { background: #fff3e0; color: #a15c00; }",
        "    .status-not_declared_for_face { background: #f1f3f5; color: #6b7280; }",
        "    .status-undeclared { background: #f3e8fd; color: #7b2cbf; }",
        "    .status-unknown { background: #f1f3f5; color: #6b7280; }",
        "    /* Per-face roll-up */",
        "    .face-table td.num { text-align: right; font-variant-numeric: tabular-nums; }",
        "    .face-table td.zero { color: #9ca3af; }",
        "    .impl-files { margin: 8px 0 0 0; padding-left: 20px; }",
        "    .impl-files li { margin: 3px 0; font-size: 0.9em; }",
        "    .problem { background: #fdeaea; border-left: 3px solid #b3261e; padding: 10px 15px; border-radius: 5px; margin: 10px 0; }",
        "    .not-checked { background: #fff3e0; border-left: 3px solid #a15c00; padding: 10px 15px; border-radius: 5px; margin: 10px 0; }",
        "    .denominator { color: #666; font-size: 0.9em; margin: 5px 0 20px 0; }",
    ])
    return styles


def get_flow_styles() -> list[str]:
    """Get CSS styles for flow test HTML pages."""
    styles = get_common_styles()
    styles.extend(get_sidebar_base_styles())
    styles.extend([
        "    .sidebar a { display: flex; align-items: center; padding: 8px 12px; color: #cbd5e1; text-decoration: none; border-radius: 6px; font-size: 0.85em; transition: all 0.2s; }",
        "    .sidebar a:hover { background: #334155; color: #f8fafc; }",
        "    .step-num { flex-shrink: 0; width: 22px; height: 22px; line-height: 22px; text-align: center; background: #475569; color: #e2e8f0; border-radius: 50%; font-size: 0.7em; font-weight: 600; margin-right: 8px; }",
        "    .step-icon { margin-right: 6px; font-size: 0.9em; width: 16px; height: 16px; display: inline-block; border-radius: 3px; }",
        "    .step-icon.file { background: #1e3a5f; }",
        "    .step-icon.block { background: #4a3520; }",
        "    .step-icon.action { background: #1e3a5f; }",
        "    .step-icon.assert { background: #1a3a2a; }",
        "    .step-label { flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }",
        "    .checkpoint-item { padding: 6px 12px; color: #94a3b8; font-size: 0.85em; display: flex; align-items: center; }",
        "    .checkpoint-item::before { content: '🏁'; margin-right: 8px; }",
        "    .sidebar a.active { background: #3b82f6; color: white; }",
        "    /* Main content */",
        "    .main-content { margin-left: 280px; padding: 30px 40px; max-width: 900px; flex: 1; }",
        "    h1 { color: #333; border-bottom: 2px solid #7b1fa2; padding-bottom: 10px; margin-top: 0; }",
        "    h2 { color: #555; margin-top: 30px; }",
        "    .info { background: #f9f9f9; padding: 15px; border-radius: 5px; margin: 15px 0; }",
        "    .test-description { color: #666; font-size: 0.95rem; font-weight: normal; max-width: 75ch; margin: 5px 0 20px 0; white-space: pre-wrap; }",
        "    code { background: #f0f0f0; padding: 2px 6px; border-radius: 3px; font-size: 0.9em; }",
        "    /* Flow steps */",
        "    .flow-step { background: #fff; border-radius: 8px; margin: 12px 0; box-shadow: 0 2px 4px rgba(0,0,0,0.1); overflow: hidden; }",
        "    .flow-step.file-ref { }",
        "    .flow-step.inline-action { }",
        "    .flow-step.inline-assert { }",
        "    .step-header { display: flex; align-items: center; padding: 12px 15px; background: #f8f9fa; border-bottom: 1px solid #eee; }",
        "    .step-number { width: 28px; height: 28px; line-height: 28px; text-align: center; background: #7b1fa2; color: white; border-radius: 50%; font-size: 0.85em; font-weight: 600; margin-right: 12px; }",
        "    .step-type-badge { padding: 4px 10px; border-radius: 12px; font-size: 0.8em; font-weight: 500; }",
        "    .step-type-badge.file { background: #e3f2fd; color: #1976d2; }",
        "    .step-type-badge.block { background: #fff3e0; color: #e65100; }",
        "    .step-type-badge.action { background: #e3f2fd; color: #007AFF; }",
        "    .step-type-badge.assert { background: #e8f5e9; color: #34C759; }",
        "    .step-content { padding: 15px; }",
        "    .step-detail { margin: 6px 0; }",
        "    .step-detail strong { color: #555; }",
        "    .inline-action .step-header, .inline-assert .step-header { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }",
        "    .inline-step-action { font-size: 0.95em; padding: 2px 6px; background: #f5f5f5; border-radius: 4px; }",
        "    .inline-step-target { color: #666; font-size: 0.9em; }",
        "    .inline-step-target code { background: #f0f0f0; padding: 2px 4px; border-radius: 3px; }",
        "    .inline-step-details { color: #888; font-size: 0.85em; }",
        "    /* Block steps */",
        "    .flow-step.block-step { }",
        "    .block-title { font-weight: 500; margin-left: 10px; color: #333; }",
        "    .block-steps { margin-top: 12px; padding: 12px; background: #fafafa; border-radius: 6px; border: 1px solid #eee; }",
        "    .block-steps-header { font-size: 0.85em; font-weight: 600; color: #666; margin-bottom: 10px; padding-bottom: 8px; border-bottom: 1px solid #e0e0e0; }",
        "    .block-steps table { width: 100%; border-collapse: collapse; font-size: 0.85em; margin-top: 8px; }",
        "    .block-steps th, .block-steps td { border: 1px solid #ddd; padding: 6px 8px; text-align: left; }",
        "    .block-steps th { background: #f0f0f0; font-weight: 500; }",
        "    .block-steps .action { color: #007AFF; font-weight: 500; }",
        "    .block-steps .assert { color: #34C759; font-weight: 500; }",
        "    /* Setup/Teardown */",
        "    .setup-teardown { background: #fffbf0; border-radius: 8px; padding: 10px; margin: 10px 0; }",
        "    .setup-teardown .flow-step { margin: 8px 0; box-shadow: none; border: 1px solid #eee; }",
        "    /* Checkpoints */",
        "    .checkpoint-list { list-style: none; padding: 0; }",
        "    .checkpoint-list li { padding: 10px 15px; background: #f3e5f5; border-radius: 6px; margin: 8px 0; }",
        "    /* Referenced cases */",
        "    .referenced-cases { margin-top: 15px; padding-top: 15px; border-top: 1px solid #eee; }",
        "    .ref-cases-header { font-weight: 600; color: #1976d2; margin-bottom: 10px; font-size: 0.9em; }",
        "    .ref-case { padding: 12px 0; margin: 8px 0; }",
        "    .ref-case-title { font-weight: 500; color: #333; margin-bottom: 4px; }",
        "    .ref-case-name { color: #666; font-size: 0.85em; margin-bottom: 10px; }",
        "    .ref-case-name code { background: #e8e8e8; }",
        "    .ref-steps-table { width: 100%; border-collapse: collapse; font-size: 0.85em; margin-top: 8px; }",
        "    .ref-steps-table th, .ref-steps-table td { border: 1px solid #ddd; padding: 6px 8px; text-align: left; }",
        "    .ref-steps-table th { background: #f0f0f0; font-weight: 500; }",
        "    .ref-steps-table .action { color: #007AFF; font-weight: 500; }",
        "    .ref-steps-table .assert { color: #34C759; font-weight: 500; }",
        "    .step-detail.warning { color: #ff9800; font-style: italic; }",
        "    .ref-desc-section { margin: 10px 0; padding-left: 10px; border-left: 3px solid #e0e0e0; }",
        "    .ref-desc-section ul, .ref-desc-section ol { margin: 5px 0; padding-left: 25px; }",
        "    .ref-desc-section li { margin: 2px 0; }",
        "    .ref-notes { color: #666; font-style: italic; background: #fffbf0; padding: 10px; border-radius: 5px; margin: 10px 0; }",
        "    /* Args display */",
        "    .step-args { background: #f0f7ff; padding: 10px 15px; border-radius: 5px; margin: 10px 0; border-left: 3px solid #007AFF; }",
        "    .step-args ul { margin: 5px 0 0 0; padding-left: 20px; }",
        "    .step-args li { margin: 3px 0; }",
    ])
    styles.extend(get_responsive_styles())
    return styles


def get_index_styles() -> list[str]:
    """Get CSS styles for index HTML page."""
    styles = get_common_styles()
    styles.extend([
        "    body { background: #fafafa; }",
    ])
    styles.extend(get_sidebar_base_styles())
    styles.extend([
        "    .sidebar a { display: block; padding: 6px 12px 6px 24px; color: #cbd5e1; text-decoration: none; border-radius: 4px; font-size: 0.85em; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; transition: background-color 0.2s; }",
        "    .sidebar a:hover { background: #334155; color: #f8fafc; }",
        "    /* Main content */",
        "    .main-content { margin-left: 280px; padding: 30px 40px; flex: 1; max-width: 900px; }",
        "    h1 { color: #333; border-bottom: 2px solid #007AFF; padding-bottom: 10px; margin-top: 0; }",
        "    .summary { background: #fff; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 30px; display: flex; flex-wrap: wrap; gap: 20px; }",
        "    .summary-item { text-align: center; min-width: 80px; }",
        "    .summary-value { font-size: 2em; font-weight: bold; color: #007AFF; }",
        "    .summary-label { color: #666; font-size: 0.9em; }",
        "    /* Collapsible category */",
        "    .category { margin-bottom: 25px; }",
        "    .category-header { display: flex; align-items: center; justify-content: space-between; background: #fff; padding: 15px 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); cursor: pointer; user-select: none; }",
        "    .category-header:hover { box-shadow: 0 4px 8px rgba(0,0,0,0.15); }",
        "    .category-header h2 { margin: 0; color: #333; font-size: 1.2em; display: flex; align-items: center; gap: 10px; }",
        "    .category-header .arrow { transition: transform 0.3s; font-size: 0.8em; color: #666; }",
        "    .category-header.collapsed .arrow { transform: rotate(-90deg); }",
        "    .subcategory { margin: 8px 0 8px 12px; }",
        "    .subcategory-header { display: flex; align-items: center; background: #f8f9fa; padding: 10px 16px; border-radius: 6px; cursor: pointer; user-select: none; }",
        "    .subcategory-header:hover { background: #e9ecef; }",
        "    .subcategory-header h3 { margin: 0; color: #555; font-size: 1em; display: flex; align-items: center; gap: 8px; }",
        "    .subcategory-header .arrow { transition: transform 0.3s; font-size: 0.7em; color: #888; }",
        "    .subcategory-header.collapsed .arrow { transform: rotate(-90deg); }",
        "    .category-badge { padding: 4px 12px; border-radius: 15px; font-size: 0.85em; font-weight: 600; }",
        "    .category-badge.screen { background: #e3f2fd; color: #1976d2; }",
        "    .category-badge.flow { background: #f3e5f5; color: #7b1fa2; }",
        "    .category-badge.doc { background: #e8f5e9; color: #2e7d32; }",
        "    .category-badge.api { background: #fff3e0; color: #f57c00; }",
        "    .category-badge.spec { background: #e0f7fa; color: #00838f; }",
        "    .category-badge.component { background: #fce4ec; color: #c2185b; }",
        "    .category-badge.unit { background: #e8eaf6; color: #3949ab; }",
        "    .category-badge.app { background: #e0f2fe; color: #0369a1; }",
        "    .category-badge.md { background: #fff8e1; color: #f57c00; }",
        "    .category-badge.figma { background: #fce4ec; color: #e91e63; }",
        "    .category-content { max-height: 2000px; overflow: hidden; transition: max-height 0.3s ease-out; }",
        "    .category-content.collapsed { max-height: 0; }",
        "    .canvas-group { margin: 10px 0; }",
        "    .canvas-group-header { display: flex; align-items: center; background: #f5f5f5; padding: 10px 15px; border-radius: 6px; cursor: pointer; user-select: none; }",
        "    .canvas-group-header:hover { background: #eeeeee; }",
        "    .canvas-group-header h3 { margin: 0; color: #555; font-size: 1em; display: flex; align-items: center; gap: 8px; }",
        "    .canvas-group-header .arrow { transition: transform 0.3s; font-size: 0.7em; color: #888; }",
        "    .canvas-group-header.collapsed .arrow { transform: rotate(-90deg); }",
        "    .canvas-group-content { max-height: 2000px; overflow: hidden; transition: max-height 0.3s ease-out; }",
        "    .canvas-group-content.collapsed { max-height: 0; }",
        "    .test-list { list-style: none; padding: 0; margin: 10px 0 0 0; }",
        "    .test-item { background: #fff; margin: 8px 0; padding: 15px 20px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); border-left: 4px solid transparent; }",
        "    .test-item:hover { box-shadow: 0 2px 6px rgba(0,0,0,0.12); }",
        "    .test-item.screen { border-left-color: #1976d2; }",
        "    .test-item.flow { border-left-color: #7b1fa2; }",
        "    .test-item.doc { border-left-color: #2e7d32; }",
        "    .test-item.api { border-left-color: #f57c00; }",
        "    .test-item.spec { border-left-color: #00838f; }",
        "    .test-item.component { border-left-color: #c2185b; }",
        "    .test-item.md { border-left-color: #f57c00; }",
        "    .test-item.figma { border-left-color: #e91e63; }",
        "    .badge-category { font-size: 0.75em; padding: 2px 8px; background: #f5f5f5; color: #666; border-radius: 4px; margin-left: 8px; }",
        "    .test-name { font-size: 1.05em; font-weight: 600; color: #333; text-decoration: none; }",
        "    .test-name:hover { color: #007AFF; }",
        "    .doc-link { text-decoration: none; margin-left: 8px; font-size: 1em; opacity: 0.7; transition: opacity 0.2s; }",
        "    .doc-link:hover { opacity: 1; }",
        "    .test-meta { margin-top: 5px; color: #666; font-size: 0.85em; }",
        "    .test-description { color: #555; margin-top: 5px; font-size: 0.9em; }",
        "    .badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 0.75em; margin-right: 5px; }",
        "    .badge-screen { background: #e3f2fd; color: #1976d2; }",
        "    .badge-flow { background: #f3e5f5; color: #7b1fa2; }",
        "    .badge-platform { background: #e8f5e9; color: #388e3c; }",
        "    /* Flow Diagram link */",
        "    .diagram-link-container { margin-bottom: 25px; }",
        "    .diagram-link { display: flex; align-items: center; gap: 15px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px 25px; border-radius: 12px; text-decoration: none; box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4); transition: transform 0.2s, box-shadow 0.2s; }",
        "    .diagram-link:hover { transform: translateY(-2px); box-shadow: 0 6px 20px rgba(102, 126, 234, 0.5); }",
        "    .diagram-icon { font-size: 2em; }",
        "    .diagram-text { font-size: 1.2em; font-weight: 600; }",
        "    .diagram-desc { font-size: 0.85em; opacity: 0.9; margin-left: auto; }",
        "    .sidebar-diagram-link { margin-bottom: 15px; padding-bottom: 15px; border-bottom: 1px solid #475569; }",
        "    .sidebar-diagram-link a { display: block; padding: 10px 15px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; border-radius: 6px; text-align: center; font-weight: 500; text-decoration: none; }",
        "    .sidebar-diagram-link a:hover { opacity: 0.9; }",
        "    /* Sidebar ER Diagram link */",
        "    .sidebar-erd-link { margin: 5px 0 10px 0; }",
        "    .sidebar-erd-link a { display: block; padding: 8px 12px; background: linear-gradient(135deg, #34d399 0%, #059669 100%); color: white; border-radius: 6px; text-align: center; font-weight: 500; font-size: 0.85em; text-decoration: none; }",
        "    .sidebar-erd-link a:hover { opacity: 0.9; }",
        "    /* ER Diagram link */",
        "    .erd-link-container { margin: 10px 0 15px 0; }",
        "    .erd-link { display: flex; align-items: center; gap: 12px; background: linear-gradient(135deg, #34d399 0%, #059669 100%); color: white; padding: 15px 20px; border-radius: 10px; text-decoration: none; box-shadow: 0 3px 10px rgba(5, 150, 105, 0.3); transition: transform 0.2s, box-shadow 0.2s; }",
        "    .erd-link:hover { transform: translateY(-2px); box-shadow: 0 5px 15px rgba(5, 150, 105, 0.4); }",
        "    .erd-icon { font-size: 1.5em; }",
        "    .erd-text { font-size: 1.1em; font-weight: 600; }",
        "    .erd-desc { font-size: 0.8em; opacity: 0.9; margin-left: auto; }",
        "    .generated { color: #999; font-size: 0.85em; margin-top: 30px; text-align: center; }",
        # Reads directly under the summary, so it cannot borrow `.generated`
        # (centred, 30px above). Emitted unconditionally with the rest of the
        # stylesheet, as `.category-badge.unit` above is: measured, a project
        # with no unitContracts gains exactly these TWO CSS lines in
        # index.html and nothing else — no markup, no section, no counts.
        "    .denominator { color: #666; font-size: 0.9em; margin: -20px 0 25px 0; }",
    ])
    styles.extend(get_responsive_styles())
    return styles


def get_index_scripts() -> list[str]:
    """Get JavaScript for index page."""
    return [
        "  <script>",
        "    function toggleCategory(id) {",
        "      const header = document.getElementById(id + '-header');",
        "      const content = document.getElementById(id + '-content');",
        "      header.classList.toggle('collapsed');",
        "      content.classList.toggle('collapsed');",
        "    }",
        "    function toggleSidebar(id) {",
        "      const title = document.getElementById('sidebar-' + id + '-title');",
        "      const list = document.getElementById('sidebar-' + id + '-list');",
        "      title.classList.toggle('collapsed');",
        "      list.classList.toggle('collapsed');",
        "    }",
        "    function toggleSection(id) {",
        "      const title = document.getElementById(id + '-title');",
        "      const list = document.getElementById(id + '-list');",
        "      title.classList.toggle('collapsed');",
        "      list.classList.toggle('collapsed');",
        "    }",
        "  </script>",
    ]
