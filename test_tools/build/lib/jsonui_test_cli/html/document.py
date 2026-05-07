"""Document page HTML generation with sidebar."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from .styles import get_screen_styles, get_toggle_script
from .sidebar import escape_html


def _get_relative_root(doc_path: str) -> str:
    """Calculate relative path to root from document path.

    E.g., 'docs/screens/account.html' -> '../../'
          'docs/test.html' -> '../'
    """
    from pathlib import Path
    depth = len(Path(doc_path).parent.parts)
    if depth == 0:
        return "./"
    return "../" * depth


def generate_document_sidebar(
    title: str,
    all_tests_nav: dict | None = None,
    current_doc_path: str | None = None
) -> list[str]:
    """
    Generate sidebar HTML for document pages.

    Args:
        title: Page title
        all_tests_nav: Navigation data {'screens': [...], 'flows': [...]}
        current_doc_path: Current document's relative path

    Returns:
        List of HTML strings for the sidebar
    """
    # Calculate relative path to root based on document depth
    rel_root = _get_relative_root(current_doc_path) if current_doc_path else "../"

    parts = []
    parts.append("  <nav class='sidebar'>")
    parts.append(f"    <a href='{rel_root}index.html' class='back-link'>&larr; Back to Index</a>")
    parts.append(f"    <h2>{escape_html(title)}</h2>")

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

    # Documents navigation (collapsible, collapsed by default)
    if all_tests_nav and all_tests_nav.get('documents'):
        documents = all_tests_nav['documents']
        parts.append("    <div class='sidebar-section'>")
        parts.append(f"      <div class='sidebar-title doc collapsed' id='documents-title' onclick=\"toggleSection('documents')\"><span class='arrow'>▼</span> Documents <span class='count'>{len(documents)}</span></div>")
        parts.append("      <div class='sidebar-list collapsed' id='documents-list'>")
        parts.append("        <ul>")
        for d in documents:
            is_current = current_doc_path and d['path'] == current_doc_path
            current_class = " current" if is_current else ""
            parts.append(f"          <li><a href='{rel_root}{d['path']}' class='nav-link{current_class}' title='{escape_html(d['name'])}'>{escape_html(d['name'])}</a></li>")
        parts.append("        </ul>")
        parts.append("      </div>")
        parts.append("    </div>")

    parts.append("  </nav>")
    return parts


def _extract_title_from_html(html_content: str) -> str:
    """Extract title from HTML content."""
    # Try to find <title> tag
    title_match = re.search(r'<title[^>]*>([^<]+)</title>', html_content, re.IGNORECASE)
    if title_match:
        return title_match.group(1).strip()

    # Try to find <h1> tag
    h1_match = re.search(r'<h1[^>]*>([^<]+)</h1>', html_content, re.IGNORECASE)
    if h1_match:
        return h1_match.group(1).strip()

    return "Document"


def _extract_body_content(html_content: str) -> str:
    """Extract body content from HTML, or return as-is if no body tag."""
    # Try to extract content between <body> tags
    body_match = re.search(r'<body[^>]*>(.*?)</body>', html_content, re.IGNORECASE | re.DOTALL)
    if body_match:
        content = body_match.group(1).strip()
    elif re.search(r'<html|<!DOCTYPE', html_content, re.IGNORECASE):
        # It's an HTML document but we couldn't find body - return as-is
        content = html_content
    else:
        # It's probably just HTML fragment, return as-is
        content = html_content

    # Convert <pre><code class="language-mermaid"> to <pre class="mermaid"> for Mermaid CDN
    content = _convert_mermaid_blocks(content)
    return content


def _convert_mermaid_blocks(html_content: str) -> str:
    """Convert code blocks with language-mermaid class to Mermaid-compatible format."""
    # Pattern: <pre><code class="language-mermaid">...</code></pre>
    # Replace with: <pre class="mermaid">...</pre>
    pattern = r'<pre>\s*<code\s+class=["\']language-mermaid["\']>(.*?)</code>\s*</pre>'

    def replace_mermaid(match):
        # Get the mermaid content and unescape HTML entities
        content = match.group(1)
        # Unescape common HTML entities that might be in the mermaid code
        content = content.replace('&gt;', '>')
        content = content.replace('&lt;', '<')
        content = content.replace('&amp;', '&')
        content = content.replace('&quot;', '"')
        return f'<pre class="mermaid">{content}</pre>'

    return re.sub(pattern, replace_mermaid, html_content, flags=re.DOTALL | re.IGNORECASE)


def _extract_head_styles(html_content: str) -> str:
    """Extract style tags from HTML head."""
    styles = []

    # Find all <style> tags
    style_matches = re.findall(r'<style[^>]*>(.*?)</style>', html_content, re.IGNORECASE | re.DOTALL)
    for style in style_matches:
        styles.append(style)

    # Find <link rel="stylesheet"> tags (we can't inline these, but note them)
    # For now, we skip external stylesheets

    return '\n'.join(styles)


def generate_document_html(
    source_path: Path,
    title: str | None = None,
    all_tests_nav: dict | None = None,
    current_doc_path: str | None = None
) -> str:
    """
    Generate HTML documentation page with sidebar from source document.

    Embeds body content directly with Mermaid CDN for diagram support.

    Args:
        source_path: Path to the source HTML/MD document
        title: Optional title override
        all_tests_nav: Navigation data {'screens': [...], 'flows': [...], 'documents': [...]}
        current_doc_path: Current document's relative path

    Returns:
        Complete HTML string with sidebar
    """
    # Read source document
    try:
        with open(source_path, 'r', encoding='utf-8') as f:
            source_content = f.read()
    except Exception as e:
        source_content = f"<p class='error'>Error reading document: {e}</p>"

    # Determine if it's markdown or HTML
    is_markdown = source_path.suffix.lower() in ['.md', '.markdown']

    if is_markdown:
        # Convert markdown to HTML (simple conversion)
        body_content = _convert_markdown_to_html(source_content)
        doc_title = title or source_path.stem.replace('_', ' ').title()
        original_styles = ""
    else:
        # Extract parts from HTML for embedding
        doc_title = title or _extract_title_from_html(source_content)
        body_content = _extract_body_content(source_content)
        original_styles = _extract_head_styles(source_content)

    # Build HTML with sidebar
    html_parts = _get_html_header(doc_title, original_styles)
    html_parts.extend(generate_document_sidebar(doc_title, all_tests_nav, current_doc_path))

    # Main content wrapper (same structure as screen test pages)
    html_parts.append("  <main class='main-content'>")
    html_parts.append(body_content)
    html_parts.append("  </main>")

    # Close HTML with Mermaid initialization
    html_parts.extend(get_toggle_script())
    html_parts.extend(_get_mermaid_script())
    html_parts.extend([
        "</body>",
        "</html>"
    ])

    return '\n'.join(html_parts)


def _get_mermaid_script() -> list[str]:
    """Get Mermaid CDN script and initialization."""
    return [
        "  <script src='https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js'></script>",
        "  <script>",
        "    mermaid.initialize({ startOnLoad: true, theme: 'default' });",
        "  </script>",
    ]


def _convert_markdown_to_html(md_content: str) -> str:
    """Simple markdown to HTML conversion."""
    import html as html_module

    lines = md_content.split('\n')
    html_lines = []
    in_code_block = False
    in_list = False
    list_type = None

    for line in lines:
        # Code blocks
        if line.startswith('```'):
            if in_code_block:
                html_lines.append('</code></pre>')
                in_code_block = False
            else:
                lang = line[3:].strip()
                html_lines.append(f'<pre><code class="language-{lang}">' if lang else '<pre><code>')
                in_code_block = True
            continue

        if in_code_block:
            html_lines.append(html_module.escape(line))
            continue

        # Close list if line is empty or not a list item
        if in_list and (not line.strip() or not (line.strip().startswith('- ') or line.strip().startswith('* ') or re.match(r'^\d+\.\s', line.strip()))):
            html_lines.append(f'</{list_type}>')
            in_list = False
            list_type = None

        # Headers
        if line.startswith('######'):
            html_lines.append(f'<h6>{html_module.escape(line[6:].strip())}</h6>')
        elif line.startswith('#####'):
            html_lines.append(f'<h5>{html_module.escape(line[5:].strip())}</h5>')
        elif line.startswith('####'):
            html_lines.append(f'<h4>{html_module.escape(line[4:].strip())}</h4>')
        elif line.startswith('###'):
            html_lines.append(f'<h3>{html_module.escape(line[3:].strip())}</h3>')
        elif line.startswith('##'):
            html_lines.append(f'<h2>{html_module.escape(line[2:].strip())}</h2>')
        elif line.startswith('#'):
            html_lines.append(f'<h1>{html_module.escape(line[1:].strip())}</h1>')
        # Unordered list
        elif line.strip().startswith('- ') or line.strip().startswith('* '):
            if not in_list or list_type != 'ul':
                if in_list:
                    html_lines.append(f'</{list_type}>')
                html_lines.append('<ul>')
                in_list = True
                list_type = 'ul'
            content = line.strip()[2:]
            html_lines.append(f'<li>{_process_inline_markdown(content)}</li>')
        # Ordered list
        elif re.match(r'^\d+\.\s', line.strip()):
            if not in_list or list_type != 'ol':
                if in_list:
                    html_lines.append(f'</{list_type}>')
                html_lines.append('<ol>')
                in_list = True
                list_type = 'ol'
            content = re.sub(r'^\d+\.\s', '', line.strip())
            html_lines.append(f'<li>{_process_inline_markdown(content)}</li>')
        # Horizontal rule
        elif line.strip() in ['---', '***', '___']:
            html_lines.append('<hr>')
        # Paragraph
        elif line.strip():
            html_lines.append(f'<p>{_process_inline_markdown(line)}</p>')
        else:
            html_lines.append('')

    # Close any open list
    if in_list:
        html_lines.append(f'</{list_type}>')

    return '\n'.join(html_lines)


def _process_inline_markdown(text: str) -> str:
    """Process inline markdown (bold, italic, code, links)."""
    import html as html_module

    # Escape HTML first
    text = html_module.escape(text)

    # Code (backticks) - do this first to avoid processing markdown inside code
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)

    # Bold
    text = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'__([^_]+)__', r'<strong>\1</strong>', text)

    # Italic
    text = re.sub(r'\*([^*]+)\*', r'<em>\1</em>', text)
    text = re.sub(r'_([^_]+)_', r'<em>\1</em>', text)

    # Links
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', text)

    return text


def _get_html_header(title: str, additional_styles: str = "") -> list[str]:
    """Generate HTML header with styles."""
    parts = [
        "<!DOCTYPE html>",
        "<html lang='en'>",
        "<head>",
        "  <meta charset='UTF-8'>",
        "  <meta name='viewport' content='width=device-width, initial-scale=1.0'>",
        f"  <title>{escape_html(title)}</title>",
        "  <style>",
    ]
    parts.extend(get_screen_styles())
    # Add minimal document-specific styles (main layout comes from screen styles)
    parts.extend([
        "    /* Document-specific styles */",
        "    .error { color: #d32f2f; background: #ffebee; padding: 15px; border-radius: 5px; }",
    ])
    if additional_styles:
        parts.append("    /* Original document styles */")
        parts.append(f"    {additional_styles}")
    parts.append("  </style>")
    parts.extend([
        "</head>",
        "<body>",
    ])
    return parts
