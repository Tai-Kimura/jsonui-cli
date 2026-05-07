"""Markdown HTML generator using marked.js + highlight.js CDN."""

from __future__ import annotations

from pathlib import Path

from .sidebar import escape_html, _render_api_docs_with_subgroups


def generate_markdown_html(
    markdown_content: str,
    title: str,
    all_tests_nav: dict | None = None,
    current_path: str | None = None,
    md_files_by_dir: dict[str, list[dict]] | None = None
) -> str:
    """
    Generate HTML page that renders markdown content using marked.js + highlight.js.

    Args:
        markdown_content: Raw markdown content to render
        title: Page title
        all_tests_nav: Navigation data for sidebar
        current_path: Current page's relative HTML path
        md_files_by_dir: Markdown files grouped by directory for sidebar

    Returns:
        Generated HTML string
    """
    has_sidebar = all_tests_nav is not None or md_files_by_dir is not None

    parts = []
    parts.append(_get_html_header(title, has_sidebar))

    if has_sidebar:
        parts.append('<div class="layout-with-sidebar">')
        sidebar_parts = generate_markdown_sidebar(
            title, all_tests_nav, current_path, md_files_by_dir
        )
        parts.extend(sidebar_parts)
        parts.append('<main class="main-content">')

    # Main content container
    parts.append('<div class="container">')
    parts.append(f'<h1>{escape_html(title)}</h1>')

    # Markdown content will be rendered by marked.js
    # We escape the content and put it in a template element
    parts.append('<div id="markdown-content"></div>')
    parts.append('<template id="markdown-source">')
    # Use base64 encoding to safely embed markdown with special characters
    import base64
    encoded_content = base64.b64encode(markdown_content.encode('utf-8')).decode('ascii')
    parts.append(encoded_content)
    parts.append('</template>')

    parts.append('</div>')  # container

    if has_sidebar:
        parts.append('</main>')
        parts.append('</div>')  # layout-with-sidebar

    parts.append(_get_html_footer(has_sidebar))

    return "\n".join(parts)


def generate_markdown_sidebar(
    title: str,
    all_tests_nav: dict | None = None,
    current_path: str | None = None,
    md_files_by_dir: dict[str, list[dict]] | None = None
) -> list[str]:
    """
    Generate sidebar HTML for markdown pages.

    Args:
        title: Page title
        all_tests_nav: Navigation data for other tests/specs
        current_path: Current page's relative path
        md_files_by_dir: Markdown files grouped by directory

    Returns:
        List of HTML strings for the sidebar
    """
    # Calculate relative path prefix based on current path depth
    # e.g., "md/plan/file.html" has depth 2, needs "../../" to reach root
    if current_path:
        depth = len(Path(current_path).parts) - 1  # -1 because filename doesn't count
        rel_prefix = "../" * depth if depth > 0 else "./"
    else:
        rel_prefix = "../"

    parts = []
    parts.append("  <nav class='sidebar'>")
    parts.append(f"    <a href='{rel_prefix}index.html' class='back-link'>&larr; Back to Index</a>")
    parts.append(f"    <h2>{escape_html(title)}</h2>")

    # Markdown files grouped by directory (collapsible per directory, with subdir grouping)
    if md_files_by_dir:
        for dir_name, md_files in md_files_by_dir.items():
            dir_id = dir_name.replace('/', '-').replace(' ', '_')
            is_current_dir = current_path and any(f['path'] == current_path for f in md_files)
            collapsed_class = "" if is_current_dir else " collapsed"

            parts.append("    <div class='sidebar-section'>")
            clean_name = dir_name.replace('-', ' ').replace('_', ' ')
            display_name = clean_name.title() if len(dir_name) > 3 else clean_name.upper()
            parts.append(f"      <div class='sidebar-title md{collapsed_class}' id='{dir_id}-title' onclick=\"toggleSection('{dir_id}')\"><span class='arrow'>▼</span> {escape_html(display_name)} <span class='count'>{len(md_files)}</span></div>")
            parts.append(f"      <div class='sidebar-list{collapsed_class}' id='{dir_id}-list'>")
            has_subdirs = any(f.get('subdir') for f in md_files)
            if has_subdirs:
                parts.extend(_render_api_docs_with_subgroups(
                    md_files, href_prefix=rel_prefix, current_path=current_path, id_prefix=dir_id))
            else:
                parts.append("        <ul>")
                for f in md_files:
                    is_current = current_path and f['path'] == current_path
                    current_class = " current" if is_current else ""
                    parts.append(f"          <li><a href='{rel_prefix}{f['path']}' class='nav-link{current_class}' title='{escape_html(f['name'])}'>{escape_html(f['name'])}</a></li>")
                parts.append("        </ul>")
            parts.append("      </div>")
            parts.append("    </div>")

    # Screen Specs navigation
    if all_tests_nav and all_tests_nav.get('specs'):
        specs = all_tests_nav['specs']
        parts.append("    <div class='sidebar-section'>")
        parts.append(f"      <div class='sidebar-title spec collapsed' id='specs-title' onclick=\"toggleSection('specs')\"><span class='arrow'>▼</span> Screen Specs <span class='count'>{len(specs)}</span></div>")
        parts.append("      <div class='sidebar-list collapsed' id='specs-list'>")
        parts.append("        <ul>")
        for s in specs:
            parts.append(f"          <li><a href='{rel_prefix}{s['path']}' class='nav-link' title='{escape_html(s['name'])}'>{escape_html(s['name'])}</a></li>")
        parts.append("        </ul>")
        parts.append("      </div>")
        parts.append("    </div>")

    # Components navigation
    if all_tests_nav and all_tests_nav.get('components'):
        components = all_tests_nav['components']
        parts.append("    <div class='sidebar-section'>")
        parts.append(f"      <div class='sidebar-title component collapsed' id='components-title' onclick=\"toggleSection('components')\"><span class='arrow'>▼</span> Components <span class='count'>{len(components)}</span></div>")
        parts.append("      <div class='sidebar-list collapsed' id='components-list'>")
        parts.append("        <ul>")
        for c in components:
            parts.append(f"          <li><a href='{rel_prefix}{c['path']}' class='nav-link' title='{escape_html(c['name'])}'>{escape_html(c['name'])}</a></li>")
        parts.append("        </ul>")
        parts.append("      </div>")
        parts.append("    </div>")

    # Flow Tests navigation
    if all_tests_nav and all_tests_nav.get('flows'):
        flows = all_tests_nav['flows']
        parts.append("    <div class='sidebar-section'>")
        parts.append(f"      <div class='sidebar-title flow collapsed' id='flows-title' onclick=\"toggleSection('flows')\"><span class='arrow'>▼</span> Flow Tests <span class='count'>{len(flows)}</span></div>")
        parts.append("      <div class='sidebar-list collapsed' id='flows-list'>")
        parts.append("        <ul>")
        for f in flows:
            parts.append(f"          <li><a href='{rel_prefix}{f['path']}' class='nav-link' title='{escape_html(f['name'])}'>{escape_html(f['name'])}</a></li>")
        parts.append("        </ul>")
        parts.append("      </div>")
        parts.append("    </div>")

    # Screen Tests navigation
    if all_tests_nav and all_tests_nav.get('screens'):
        screens = all_tests_nav['screens']
        parts.append("    <div class='sidebar-section'>")
        parts.append(f"      <div class='sidebar-title collapsed' id='screens-title' onclick=\"toggleSection('screens')\"><span class='arrow'>▼</span> Screen Tests <span class='count'>{len(screens)}</span></div>")
        parts.append("      <div class='sidebar-list collapsed' id='screens-list'>")
        parts.append("        <ul>")
        for s in screens:
            parts.append(f"          <li><a href='{rel_prefix}{s['path']}' class='nav-link' title='{escape_html(s['name'])}'>{escape_html(s['name'])}</a></li>")
        parts.append("        </ul>")
        parts.append("      </div>")
        parts.append("    </div>")

    parts.append("  </nav>")
    return parts


def _get_html_header(title: str, has_sidebar: bool = False) -> str:
    """Get HTML header with styles for markdown rendering."""
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
        .sidebar-title.md { color: #f97316; }
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
        .sidebar-subsection { margin-left: 8px; margin-bottom: 2px; }
        .sidebar-subtitle { font-size: 0.8em; color: #94a3b8; cursor: pointer; display: flex; align-items: center; gap: 0.4rem; padding: 5px 8px; border-radius: 4px; transition: background-color 0.2s; }
        .sidebar-subtitle:hover { background: #334155; }
        .sidebar-subtitle .arrow { transition: transform 0.3s; font-size: 0.65em; }
        .sidebar-subtitle.collapsed .arrow { transform: rotate(-90deg); }
        .sidebar-subtitle .count { background: #475569; color: #e2e8f0; padding: 1px 6px; border-radius: 8px; font-size: 0.7em; margin-left: auto; }
        .main-content { flex: 1; padding: 2rem; overflow-x: auto; }
        .main-content .container { max-width: none; }
'''

    return f'''<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{escape_html(title)}</title>
    <!-- highlight.js styles -->
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github-dark.min.css">
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
            max-width: 900px;
            margin: 0 auto;
            background: white;
            padding: 2rem;
            border-radius: 8px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }}
        /* Markdown content styles */
        #markdown-content h1 {{ font-size: 2rem; margin: 2rem 0 1rem; padding-bottom: 0.5rem; border-bottom: 2px solid var(--border-color); }}
        #markdown-content h2 {{ font-size: 1.5rem; margin: 1.5rem 0 1rem; padding-bottom: 0.3rem; border-bottom: 1px solid var(--border-color); }}
        #markdown-content h3 {{ font-size: 1.25rem; margin: 1.25rem 0 0.75rem; }}
        #markdown-content h4 {{ font-size: 1.1rem; margin: 1rem 0 0.5rem; color: #64748b; }}
        #markdown-content p {{ margin: 1rem 0; }}
        #markdown-content ul, #markdown-content ol {{ margin: 1rem 0; padding-left: 2rem; }}
        #markdown-content li {{ margin: 0.25rem 0; }}
        #markdown-content code {{
            background: var(--code-bg);
            padding: 0.2em 0.4em;
            border-radius: 4px;
            font-family: 'SF Mono', Monaco, monospace;
            font-size: 0.9em;
        }}
        #markdown-content pre {{
            background: #1e293b;
            padding: 1rem;
            border-radius: 8px;
            overflow-x: auto;
            margin: 1rem 0;
        }}
        #markdown-content pre code {{
            background: transparent;
            padding: 0;
            color: #e2e8f0;
        }}
        #markdown-content blockquote {{
            border-left: 4px solid var(--primary-color);
            margin: 1rem 0;
            padding: 0.5rem 1rem;
            background: #f0f9ff;
            color: #334155;
        }}
        #markdown-content table {{
            width: 100%;
            border-collapse: collapse;
            margin: 1rem 0;
        }}
        #markdown-content th, #markdown-content td {{
            padding: 0.75rem;
            text-align: left;
            border: 1px solid var(--border-color);
        }}
        #markdown-content th {{
            background: var(--bg-color);
            font-weight: 600;
        }}
        #markdown-content tr:hover {{
            background: #f8fafc;
        }}
        #markdown-content a {{
            color: var(--primary-color);
            text-decoration: none;
        }}
        #markdown-content a:hover {{
            text-decoration: underline;
        }}
        #markdown-content img {{
            max-width: 100%;
            height: auto;
            border-radius: 4px;
            margin: 1rem 0;
        }}
        #markdown-content hr {{
            border: none;
            border-top: 1px solid var(--border-color);
            margin: 2rem 0;
        }}
        {sidebar_styles}
    </style>
</head>
<body>
'''


def _get_html_footer(has_sidebar: bool = False) -> str:
    """Get HTML footer with marked.js + highlight.js scripts."""
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
    return f'''
<!-- marked.js + highlight.js CDN -->
<script src="https://cdnjs.cloudflare.com/ajax/libs/marked/12.0.0/marked.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"></script>
<script>
    // Configure marked to use highlight.js for code blocks
    marked.setOptions({{
        highlight: function(code, lang) {{
            if (lang && hljs.getLanguage(lang)) {{
                try {{
                    return hljs.highlight(code, {{ language: lang }}).value;
                }} catch (e) {{}}
            }}
            return hljs.highlightAuto(code).value;
        }},
        breaks: true,
        gfm: true
    }});

    // Render markdown content
    document.addEventListener('DOMContentLoaded', function() {{
        const template = document.getElementById('markdown-source');
        const container = document.getElementById('markdown-content');
        if (template && container) {{
            // Decode base64 content
            const encodedContent = template.innerHTML.trim();
            const markdownContent = decodeURIComponent(escape(atob(encodedContent)));
            container.innerHTML = marked.parse(markdownContent);
        }}
    }});
</script>
{toggle_script}
</body>
</html>
'''
