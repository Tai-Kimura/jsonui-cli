"""HTML generation module for JsonUI test documentation."""

from .styles import (
    get_screen_styles,
    get_flow_styles,
    get_index_styles,
)
from .sidebar import (
    generate_screen_sidebar,
    generate_flow_sidebar,
    generate_index_sidebar,
)
from .screen import generate_screen_html
from .flow import generate_flow_html
from .index import generate_index_html
from .document import generate_document_html
from .swagger import (
    is_swagger_file,
    parse_swagger_file,
    generate_swagger_html,
)
from .schema import (
    has_api_paths,
    generate_schema_html,
)
from .erd import generate_erd_html

__all__ = [
    "get_screen_styles",
    "get_flow_styles",
    "get_index_styles",
    "generate_screen_sidebar",
    "generate_flow_sidebar",
    "generate_index_sidebar",
    "generate_screen_html",
    "generate_flow_html",
    "generate_index_html",
    "generate_document_html",
    "is_swagger_file",
    "parse_swagger_file",
    "generate_swagger_html",
    "has_api_paths",
    "generate_schema_html",
    "generate_erd_html",
]
