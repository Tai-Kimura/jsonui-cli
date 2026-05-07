"""Custom validation rules configuration loader."""

from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CONFIG_FILENAME = ".jsonui-doc-rules.json"


@dataclass
class CustomRules:
    """Parsed custom validation rules from config file."""
    config_path: Path | None = None

    # Additional component types
    extra_screen_component_types: set[str] = field(default_factory=set)
    extra_component_types: set[str] = field(default_factory=set)

    # Additional component categories
    extra_component_categories: set[str] = field(default_factory=set)

    # Additional file types
    extra_file_types: set[str] = field(default_factory=set)

    # Event handler overrides
    allowed_event_handler_names: set[str] = field(default_factory=set)
    extra_event_handler_patterns: list[str] = field(default_factory=list)

    # Variable naming overrides
    extra_variable_patterns: list[str] = field(default_factory=list)

    # Prop naming overrides
    extra_prop_patterns: list[str] = field(default_factory=list)

    # Slot naming overrides
    extra_slot_patterns: list[str] = field(default_factory=list)

    # Internal state naming overrides
    extra_internal_state_patterns: list[str] = field(default_factory=list)

    # Exposed event naming overrides
    allowed_exposed_event_names: set[str] = field(default_factory=set)
    extra_exposed_event_patterns: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return self.config_path is None


def find_config_file(start_dir: Path) -> Path | None:
    """Search for config file from start_dir upward."""
    current = start_dir.resolve()
    while True:
        candidate = current / CONFIG_FILENAME
        if candidate.is_file():
            return candidate
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None


def _validate_patterns(patterns: list, field_name: str) -> list[str]:
    """Validate regex patterns and return only valid ones."""
    valid = []
    for p in patterns:
        if not isinstance(p, str):
            continue
        try:
            re.compile(p)
            valid.append(p)
        except re.error:
            print(f"  Warning: Invalid regex in {field_name}: '{p}' (skipped)")
    return valid


def load_config(config_path: Path) -> CustomRules:
    """Load and parse the custom rules config file."""
    with open(config_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    rules = CustomRules(config_path=config_path)
    rules_data = data.get("rules", {})

    # Component types
    comp_types = rules_data.get("componentTypes", {})
    rules.extra_screen_component_types = set(comp_types.get("screen", []))
    rules.extra_component_types = set(comp_types.get("component", []))

    # Component categories
    rules.extra_component_categories = set(rules_data.get("componentCategories", []))

    # File types
    rules.extra_file_types = set(rules_data.get("fileTypes", []))

    # Event handlers
    eh = rules_data.get("eventHandlers", {})
    rules.allowed_event_handler_names = set(eh.get("allowedNames", []))
    rules.extra_event_handler_patterns = _validate_patterns(
        eh.get("additionalPatterns", []), "eventHandlers.additionalPatterns"
    )

    # Variable naming
    vn = rules_data.get("variableNaming", {})
    rules.extra_variable_patterns = _validate_patterns(
        vn.get("additionalPatterns", []), "variableNaming.additionalPatterns"
    )

    # Prop naming
    pn = rules_data.get("propNaming", {})
    rules.extra_prop_patterns = _validate_patterns(
        pn.get("additionalPatterns", []), "propNaming.additionalPatterns"
    )

    # Slot naming
    sn = rules_data.get("slotNaming", {})
    rules.extra_slot_patterns = _validate_patterns(
        sn.get("additionalPatterns", []), "slotNaming.additionalPatterns"
    )

    # Internal state naming
    isn_data = rules_data.get("internalStateNaming", {})
    rules.extra_internal_state_patterns = _validate_patterns(
        isn_data.get("additionalPatterns", []), "internalStateNaming.additionalPatterns"
    )

    # Exposed event naming
    een = rules_data.get("exposedEventNaming", {})
    rules.allowed_exposed_event_names = set(een.get("allowedNames", []))
    rules.extra_exposed_event_patterns = _validate_patterns(
        een.get("additionalPatterns", []), "exposedEventNaming.additionalPatterns"
    )

    return rules


def load_rules_for_path(file_path: Path | None) -> CustomRules:
    """Find and load custom rules for a given file path."""
    if file_path is None:
        start_dir = Path.cwd()
    else:
        start_dir = Path(file_path).resolve().parent

    config_path = find_config_file(start_dir)
    if config_path is None:
        return CustomRules()

    return load_config(config_path)


def generate_template_config() -> dict:
    """Generate a template configuration."""
    return {
        "description": "Custom validation rules for jsonui-doc. All rules are additive to base rules.",
        "version": "1.0",
        "rules": {
            "componentTypes": {
                "screen": [],
                "component": []
            },
            "componentCategories": [],
            "fileTypes": [],
            "eventHandlers": {
                "allowedNames": [],
                "additionalPatterns": []
            },
            "variableNaming": {
                "additionalPatterns": []
            },
            "propNaming": {
                "additionalPatterns": []
            },
            "slotNaming": {
                "additionalPatterns": []
            },
            "internalStateNaming": {
                "additionalPatterns": []
            },
            "exposedEventNaming": {
                "allowedNames": [],
                "additionalPatterns": []
            }
        }
    }


def generate_flutter_config() -> dict:
    """Generate a config pre-populated with Flutter-specific rules."""
    config = generate_template_config()
    rules = config["rules"]
    rules["componentTypes"]["screen"] = [
        "Scaffold", "AppBar", "BottomNavigationBar", "Drawer",
        "FloatingActionButton", "SnackBar", "BottomSheet", "Dialog",
        "ListView", "GridView", "Text", "TextFormField", "Card",
        "Container", "Column", "Row", "Stack", "Expanded", "Padding",
        "TextButton", "ElevatedButton", "OutlinedButton", "IconButton",
        "Icon", "CircularProgressIndicator", "Widget", "SingleChildScrollView",
        "Slider", "GoogleMap", "TabBar", "Tab", "TabBarView", "EmptyStateWidget",
    ]
    rules["componentTypes"]["component"] = [
        "Scaffold", "ListView", "GridView", "Text", "TextFormField",
        "Card", "Container", "Column", "Row", "Stack", "Expanded", "Padding",
        "TextButton", "ElevatedButton", "OutlinedButton", "IconButton",
        "Icon", "CircularProgressIndicator", "Widget", "SingleChildScrollView",
        "Slider",
    ]
    rules["fileTypes"] = [
        "Screen", "State", "Provider", "Widget", "Router",
        "Constants", "ErrorHandler", "BottomSheet",
    ]
    rules["eventHandlers"]["allowedNames"] = [
        "initState", "dispose", "didChangeDependencies",
        "didUpdateWidget", "didChangeAppLifecycleState", "build",
    ]
    rules["variableNaming"]["additionalPatterns"] = ["^_?[a-z][a-zA-Z0-9]*$"]
    rules["propNaming"]["additionalPatterns"] = ["^_?[a-z][a-zA-Z0-9]*$"]
    rules["internalStateNaming"]["additionalPatterns"] = ["^_?[a-z][a-zA-Z0-9]*$"]
    return config


def apply_rules_to_screen_schema(base_schema: dict, rules: CustomRules) -> dict:
    """Return a copy of the schema with custom rules applied."""
    if rules.is_empty:
        return base_schema

    schema = copy.deepcopy(base_schema)
    defs = schema.get("$defs", {})

    # Extend component type enum
    comp_def = defs.get("component", {}).get("properties", {}).get("type", {})
    if "enum" in comp_def and rules.extra_screen_component_types:
        comp_def["enum"] = sorted(set(comp_def["enum"]) | rules.extra_screen_component_types)

    # Extend file type enum
    file_def = defs.get("relatedFile", {}).get("properties", {}).get("type", {})
    if "enum" in file_def and rules.extra_file_types:
        file_def["enum"] = sorted(set(file_def["enum"]) | rules.extra_file_types)

    # Relax naming patterns if additional patterns/names exist
    if rules.extra_variable_patterns:
        var_def = defs.get("uiVariable", {}).get("properties", {}).get("name", {})
        if "pattern" in var_def:
            del var_def["pattern"]

    if rules.extra_event_handler_patterns or rules.allowed_event_handler_names:
        eh_def = defs.get("eventHandler", {}).get("properties", {}).get("name", {})
        if "pattern" in eh_def:
            del eh_def["pattern"]

    return schema


def apply_rules_to_component_schema(base_schema: dict, rules: CustomRules) -> dict:
    """Return a copy of the component schema with custom rules applied."""
    if rules.is_empty:
        return base_schema

    schema = copy.deepcopy(base_schema)
    defs = schema.get("$defs", {})

    # Extend component type enum
    comp_def = defs.get("component", {}).get("properties", {}).get("type", {})
    if "enum" in comp_def and rules.extra_component_types:
        comp_def["enum"] = sorted(set(comp_def["enum"]) | rules.extra_component_types)

    # Extend category enum in metadata
    cat_def = defs.get("metadata", {}).get("properties", {}).get("category", {})
    if "enum" in cat_def and rules.extra_component_categories:
        cat_def["enum"] = sorted(set(cat_def["enum"]) | rules.extra_component_categories)

    # Relax naming patterns if additional patterns exist
    if rules.extra_prop_patterns:
        prop_def = defs.get("propItem", {}).get("properties", {}).get("name", {})
        if "pattern" in prop_def:
            del prop_def["pattern"]

    if rules.extra_slot_patterns:
        slot_def = defs.get("slotItem", {}).get("properties", {}).get("name", {})
        if "pattern" in slot_def:
            del slot_def["pattern"]

    if rules.extra_internal_state_patterns:
        state_def = defs.get("internalState", {}).get("properties", {}).get("name", {})
        if "pattern" in state_def:
            del state_def["pattern"]

    if rules.extra_exposed_event_patterns or rules.allowed_exposed_event_names:
        event_def = defs.get("exposedEvent", {}).get("properties", {}).get("name", {})
        if "pattern" in event_def:
            del event_def["pattern"]

    return schema
