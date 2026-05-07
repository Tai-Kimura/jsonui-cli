"""Swagger/OpenAPI documentation page HTML generation using Redoc."""

from __future__ import annotations

import json
from pathlib import Path

from .sidebar import escape_html


def is_swagger_file(file_path: Path) -> bool:
    """
    Check if a file is a Swagger/OpenAPI document.

    Args:
        file_path: Path to the JSON file

    Returns:
        True if the file is a Swagger/OpenAPI document
    """
    if not file_path.exists() or file_path.suffix.lower() != '.json':
        return False

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Check for OpenAPI 3.x or Swagger 2.0
        return 'openapi' in data or 'swagger' in data
    except Exception:
        return False


def parse_swagger_file(file_path: Path) -> dict | None:
    """
    Parse a Swagger/OpenAPI file and extract relevant information.

    Args:
        file_path: Path to the Swagger/OpenAPI JSON file

    Returns:
        Parsed swagger data dict or None if parsing fails
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def _get_relative_root(doc_path: str) -> str:
    """Calculate relative path to root from document path."""
    depth = len(Path(doc_path).parent.parts)
    if depth == 0:
        return "./"
    return "../" * depth


def generate_swagger_back_link(
    current_doc_path: str | None = None
) -> list[str]:
    """
    Generate a simple back link header for Swagger documentation pages.

    Redoc has its own comprehensive sidebar, so we only need a back link.

    Args:
        current_doc_path: Current document's relative path

    Returns:
        List of HTML strings for the back link header
    """
    rel_root = _get_relative_root(current_doc_path) if current_doc_path else "../"

    parts = [
        "  <div class='swagger-back-header'>",
        f"    <a href='{rel_root}index.html' class='back-link'>&larr; Back to Index</a>",
        "  </div>",
    ]
    return parts


def generate_swagger_html(
    swagger_data: dict,
    title: str | None = None,
    all_tests_nav: dict | None = None,
    current_doc_path: str | None = None
) -> str:
    """
    Generate HTML documentation page from Swagger/OpenAPI data using Redoc.

    Args:
        swagger_data: Parsed Swagger/OpenAPI data
        title: Optional title override
        all_tests_nav: Navigation data for sidebar
        current_doc_path: Current document's relative path

    Returns:
        Complete HTML string with sidebar and embedded Redoc
    """
    # Extract info
    info = swagger_data.get('info', {})
    doc_title = title or info.get('title', 'API Documentation')

    # Convert swagger data to JSON string for embedding
    swagger_json = json.dumps(swagger_data, ensure_ascii=False)

    # Build HTML
    html_parts = _get_html_header(doc_title)
    html_parts.extend(generate_swagger_back_link(current_doc_path))

    # Main content with Redoc (full width, Redoc has its own sidebar)
    html_parts.extend([
        "    <div id='redoc-container'></div>",
        "",
        "  <!-- Redoc -->",
        "  <script src='https://cdn.redoc.ly/redoc/latest/bundles/redoc.standalone.js'></script>",
        "  <script>",
        f"    const spec = {swagger_json};",
        "    Redoc.init(spec, {",
        "      scrollYOffset: 0,",
        "      hideDownloadButton: false,",
        "      expandResponses: '200,201',",
        "      pathInMiddlePanel: true,",
        "      hideHostname: true,",
        "      nativeScrollbars: true,",
        "    }, document.getElementById('redoc-container'));",
        "  </script>",
    ])

    # Close HTML
    html_parts.extend([
        "</body>",
        "</html>"
    ])

    return '\n'.join(html_parts)


def _get_html_header(title: str) -> list[str]:
    """Generate HTML header with minimal styles for Swagger documentation with Redoc."""
    parts = [
        "<!DOCTYPE html>",
        "<html lang='en'>",
        "<head>",
        "  <meta charset='UTF-8'>",
        "  <meta name='viewport' content='width=device-width, initial-scale=1.0'>",
        f"  <title>{escape_html(title)}</title>",
        "  <style>",
        "    * { margin: 0; padding: 0; box-sizing: border-box; }",
        "    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }",
        "    .swagger-back-header {",
        "      position: fixed;",
        "      top: 0;",
        "      left: 0;",
        "      right: 0;",
        "      z-index: 1000;",
        "      background: #1a1a2e;",
        "      padding: 8px 16px;",
        "      border-bottom: 1px solid #333;",
        "    }",
        "    .swagger-back-header .back-link {",
        "      color: #4dabf7;",
        "      text-decoration: none;",
        "      font-size: 14px;",
        "    }",
        "    .swagger-back-header .back-link:hover {",
        "      text-decoration: underline;",
        "    }",
        "    #redoc-container {",
        "      padding-top: 40px;",
        "    }",
        "  </style>",
        "</head>",
        "<body>",
    ]
    return parts
