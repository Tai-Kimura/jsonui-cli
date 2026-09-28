"""HTML for a spec's prose fields: plain text, or Markdown from a texts file.

Which one a value is was decided where the spec was read
(`shared/core/spec_texts.py`): a `MarkdownText` came from a `{"md": ...}`
reference and is rendered as Markdown; any other string is the author's plain
text and is escaped, with its line breaks kept — a `\\n` the author wrote is a
line break they meant, and collapsing it into one run of text is what made a
long description unreadable.

Markdown is rendered by markdown-it-py (CommonMark + tables + strikethrough)
with raw HTML OFF: a texts file is prose, and letting it carry `<script>` or
its own `style=` would make every page's look depend on its authors rather
than on the stylesheet. markdown-it also refuses `javascript:` links.
"""

from __future__ import annotations

import html
from typing import Any

from . import shared_core

_INSTALL_HINT = "pip install markdown-it-py"
_md = None


def markdown_available() -> bool:
    try:
        import markdown_it  # noqa: F401
    except ImportError:
        return False
    return True


def missing_renderer_message() -> str:
    return ("markdown-it-py is not installed, so texts-file references cannot "
            f"be rendered — {_INSTALL_HINT}")


def _renderer():
    global _md
    if _md is None:
        from markdown_it import MarkdownIt
        _md = (MarkdownIt("commonmark", {"html": False, "breaks": False})
               .enable("table").enable("strikethrough"))
    return _md


def is_markdown(value: Any) -> bool:
    texts = shared_core.load("spec_texts")
    return texts is not None and texts.is_markdown(value)


def render_markdown(text: str) -> str:
    """Markdown -> HTML, wrapped in `div.md` so the stylesheet can scope it."""
    return f'<div class="md">{_renderer().render(str(text)).strip()}</div>'


def plain_html(value: Any) -> str:
    """Escaped, with the author's line breaks kept."""
    if value is None:
        return ""
    return html.escape(str(value)).replace("\r\n", "\n").replace("\n", "<br>")


def prose_html(value: Any) -> str:
    """Inline use (a table cell, after a label): Markdown or plain text."""
    if is_markdown(value):
        return render_markdown(value)
    return plain_html(value)


def prose_block(value: Any, css_class: str = "") -> str:
    """Block use: a `<p>` for plain text, `div.md` for Markdown.

    Not a `<p>` around the Markdown: its output is block content (paragraphs,
    lists, tables), and a `<p>` cannot contain any of it.
    """
    cls = f' class="{css_class}"' if css_class else ""
    if is_markdown(value):
        return (f'<div{cls}>{render_markdown(value)}</div>' if css_class
                else render_markdown(value))
    return f'<p{cls}>{plain_html(value)}</p>'


def labelled_block(label: str, value: Any, css_class: str = "notes") -> str:
    """`<p class="notes"><strong>Notes:</strong> …</p>`, or its block form."""
    if is_markdown(value):
        return (f'<div class="{css_class} md-labelled">'
                f'<strong>{html.escape(label)}:</strong>'
                f'{render_markdown(value)}</div>')
    return (f'<p class="{css_class}"><strong>{html.escape(label)}:</strong> '
            f'{plain_html(value)}</p>')


#: Rules for `div.md`, appended to each page's stylesheet. Written against the
#: variables every page already defines (`--border-color`, `--code-bg`, …) so
#: a texts file looks like the page around it instead of a pasted document.
MARKDOWN_CSS = """
        .md { line-height: 1.7; }
        .md > :first-child { margin-top: 0; }
        .md > :last-child { margin-bottom: 0; }
        .md p { margin: 0.5em 0; }
        .md h1, .md h2, .md h3, .md h4, .md h5, .md h6 {
            margin: 1.2em 0 0.5em; line-height: 1.35; border: none; padding: 0;
        }
        .md h1 { font-size: 1.3em; }
        .md h2 { font-size: 1.2em; }
        .md h3 { font-size: 1.1em; }
        .md h4, .md h5, .md h6 { font-size: 1em; }
        .md ul, .md ol { margin: 0.5em 0; padding-left: 1.6em; }
        .md li { margin: 0.2em 0; }
        .md li > ul, .md li > ol { margin: 0.2em 0; }
        .md code {
            background: var(--code-bg, #f1f5f9); padding: 0.1em 0.35em;
            border-radius: 4px; font-size: 0.9em;
        }
        .md pre {
            background: var(--code-bg, #f1f5f9); padding: 0.75em 1em;
            border-radius: 6px; overflow-x: auto; line-height: 1.5;
        }
        .md pre code { background: none; padding: 0; font-size: 0.85em; }
        .md blockquote {
            margin: 0.75em 0; padding: 0.25em 1em; color: #475569;
            border-left: 4px solid var(--border-color, #e2e8f0);
            background: rgba(148, 163, 184, 0.08);
        }
        .md table { border-collapse: collapse; margin: 0.75em 0; width: auto; }
        .md th, .md td {
            border: 1px solid var(--border-color, #e2e8f0);
            padding: 0.35em 0.7em; text-align: left; vertical-align: top;
        }
        .md th { background: var(--code-bg, #f1f5f9); }
        .md hr { border: none; border-top: 1px solid var(--border-color, #e2e8f0); margin: 1em 0; }
        .md a { color: var(--primary-color, #2563eb); }
        .md-labelled > strong { display: block; margin-bottom: 0.25em; }
        .notes .md { font-style: normal; color: inherit; }
        td .md { font-size: inherit; }
"""


def with_markdown_css(page: str) -> str:
    """Add `MARKDOWN_CSS` to a page that renders Markdown, and only to one.

    Only then, so a page with no texts-file reference is byte-identical to
    what it was before texts files existed — regenerating a site does not
    touch every page to add rules nothing on it uses.
    """
    if '<div class="md">' not in page:
        return page
    head, sep, tail = page.partition("</style>")
    if not sep:
        return page
    return head + MARKDOWN_CSS + sep + tail
