"""Swagger/OpenAPI documentation page HTML generation using Redoc."""

from __future__ import annotations

import json
from pathlib import Path

from .sidebar import escape_html

#: the names a document can have (shared/core/openapi_file.py; ticket 2026-10-23-jsonui-test-mock-generate-yaml-traceback:
#: before 2.3.21 every reader here took *.json only and passed a YAML document by without a word)
DOC_EXTENSIONS = (".json", ".yaml", ".yml")


class OpenApiReadError(ValueError):
    """A document that could not be read: str() is one line naming the file and why."""


def read_openapi(file_path: Path) -> object:
    """One document's data, JSON or YAML (shared/core/openapi_file.py); OpenApiReadError with one line otherwise. A
    tool tree without shared/ reads JSON only."""
    from ... import shared_core

    of = shared_core.load("openapi_file")
    if of is None:
        try:
            return json.loads(Path(file_path).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise OpenApiReadError(f"{file_path}: not readable as JSON (this install has no shared/core to read YAML): {exc}") from None
    try:
        return of.read(file_path)
    except of.OpenApiFileError as exc:
        raise OpenApiReadError(str(exc)) from None


def openapi_files(folder: Path, recursive: bool = True) -> list[Path]:
    """The .json / .yaml / .yml files in folder (and below it when recursive), sorted, dot-files left out."""
    d = Path(folder)
    if not d.is_dir():
        return []
    found = d.rglob("*") if recursive else d.iterdir()
    return sorted(p for p in found if p.is_file() and p.suffix.lower() in DOC_EXTENSIONS and not p.name.startswith("."))


def _said(file_path: Path, exc: Exception) -> None:
    """A YAML document that cannot be read for want of PyYAML is said once on stderr (it is not just skipped)."""
    if "needs PyYAML" in str(exc):
        from ... import run_log

        run_log.warn(f"warning: {exc}")


def is_swagger_file(file_path: Path) -> bool:
    """
    Check if a file is a Swagger/OpenAPI document (JSON or YAML).

    Args:
        file_path: Path to the .json / .yaml / .yml file

    Returns:
        True if the file is a Swagger/OpenAPI document
    """
    if not file_path.exists() or file_path.suffix.lower() not in DOC_EXTENSIONS:
        return False
    try:
        data = read_openapi(file_path)
    except OpenApiReadError as exc:
        _said(file_path, exc)
        return False
    # Check for OpenAPI 3.x or Swagger 2.0
    return isinstance(data, dict) and ('openapi' in data or 'swagger' in data)


def parse_swagger_file(file_path: Path) -> dict | None:
    """
    Parse a Swagger/OpenAPI file and extract relevant information.

    Args:
        file_path: Path to the Swagger/OpenAPI file (JSON or YAML)

    Returns:
        Parsed swagger data dict or None if parsing fails
    """
    try:
        data = read_openapi(file_path)
    except OpenApiReadError:
        return None
    return data if isinstance(data, dict) else None


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
