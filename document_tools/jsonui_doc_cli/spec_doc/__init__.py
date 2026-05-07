"""Screen and component specification documentation module."""

from .screen_spec_schema import SCREEN_SPEC_SCHEMA
from .component_spec_schema import COMPONENT_SPEC_SCHEMA
from .validator import SpecValidator, SpecValidationResult, SpecValidationMessage
from .markdown_generator import generate_spec_markdown
from .html_generator import generate_spec_html, generate_component_html, generate_component_markdown
from .template import generate_spec_template, create_spec_file, generate_component_template, create_component_file
from .rules_config import (
    CustomRules, load_rules_for_path, find_config_file,
    generate_template_config, generate_flutter_config, CONFIG_FILENAME,
)

__all__ = [
    "SCREEN_SPEC_SCHEMA",
    "COMPONENT_SPEC_SCHEMA",
    "SpecValidator",
    "SpecValidationResult",
    "SpecValidationMessage",
    "generate_spec_markdown",
    "generate_spec_html",
    "generate_component_html",
    "generate_component_markdown",
    "generate_spec_template",
    "create_spec_file",
    "generate_component_template",
    "create_component_file",
    "CustomRules",
    "load_rules_for_path",
    "find_config_file",
    "generate_template_config",
    "generate_flutter_config",
    "CONFIG_FILENAME",
]
