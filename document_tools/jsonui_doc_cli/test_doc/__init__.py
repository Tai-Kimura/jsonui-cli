"""Test documentation generation module."""

from .generator import (
    DocumentGenerator,
    generate_schema_reference,
    generate_html_directory,
    get_diagram_errors,
    get_page_failures,
    get_pages_written,
    generation_summary_line,
    generation_warnings,
    diagram_document_href,
)
from .mermaid import generate_mermaid_diagram, generate_mermaid_html
from .mermaid.generator import DiagramResult, TransitionError, build_diagram
from .adapter import generate_adapter, SUPPORTED_PLATFORMS as ADAPTER_PLATFORMS

__all__ = [
    "DocumentGenerator",
    "generate_schema_reference",
    "generate_html_directory",
    "get_diagram_errors",
    "get_page_failures",
    "get_pages_written",
    "generation_summary_line",
    "generation_warnings",
    "generate_mermaid_diagram",
    "generate_mermaid_html",
    "build_diagram",
    "diagram_document_href",
    "DiagramResult",
    "TransitionError",
    "generate_adapter",
    "ADAPTER_PLATFORMS",
]
