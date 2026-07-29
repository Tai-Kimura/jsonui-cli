"""Test documentation generation module."""

from .generator import (
    DocumentGenerator,
    generate_schema_reference,
    generate_html_directory,
    get_page_failures,
    get_pages_written,
)
from .mermaid import generate_mermaid_diagram, generate_mermaid_html
from .adapter import generate_adapter, SUPPORTED_PLATFORMS as ADAPTER_PLATFORMS

__all__ = [
    "DocumentGenerator",
    "generate_schema_reference",
    "generate_html_directory",
    "get_page_failures",
    "get_pages_written",
    "generate_mermaid_diagram",
    "generate_mermaid_html",
    "generate_adapter",
    "ADAPTER_PLATFORMS",
]
