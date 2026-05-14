"""Validator for screen and component specification JSON files."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .screen_spec_schema import SCREEN_SPEC_SCHEMA
from .component_spec_schema import COMPONENT_SPEC_SCHEMA
from .rules_config import CustomRules, load_rules_for_path


def _has_external_layout_ref(node: dict) -> bool:
    """True when a cellNode/header/footer references an external Layout JSON.

    Callers that use ``layoutFile`` (or the legacy ``layout`` key) describe
    the tree in ``{layouts_directory}/{layoutFile}.json`` rather than inline.
    Inline-layout checks (``children`` required, etc.) must be skipped for
    these nodes.
    """
    if not isinstance(node, dict):
        return False
    ref = node.get("layoutFile") or node.get("layout")
    return isinstance(ref, str) and bool(ref)


@dataclass
class SpecValidationMessage:
    """A validation message (error or warning)."""
    path: str
    message: str
    level: str = "error"  # "error" or "warning"

    def __str__(self) -> str:
        prefix = "ERROR" if self.level == "error" else "WARNING"
        return f"  [{prefix}] {self.path}: {self.message}"


@dataclass
class SpecValidationResult:
    """Result of validating a specification file."""
    file_path: Path | None = None
    spec_data: dict | None = None
    errors: list[SpecValidationMessage] = field(default_factory=list)
    warnings: list[SpecValidationMessage] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    @property
    def error_count(self) -> int:
        return len(self.errors)

    @property
    def warning_count(self) -> int:
        return len(self.warnings)


class SpecValidator:
    """Validates screen and component specification JSON files."""

    # Valid component types for screen specs
    VALID_SCREEN_COMPONENT_TYPES = {
        "View", "ScrollView", "SafeAreaView",
        "Label", "TextField", "TextView",
        "Button", "Image", "Collection", "TabView",
        "SelectBox", "CheckBox", "Switch", "Web",
        "Spacer", "Divider", "Indicator"
    }

    # Valid component types for component specs (no TabView, SafeAreaView)
    VALID_COMPONENT_TYPES = {
        "View", "ScrollView",
        "Label", "TextField", "TextView",
        "Button", "Image", "Collection",
        "SelectBox", "CheckBox", "Switch", "Web",
        "Spacer", "Divider", "Indicator"
    }

    # Valid component categories
    VALID_COMPONENT_CATEGORIES = {
        "card", "form", "list", "navigation", "input", "display", "layout", "feedback", "other"
    }

    # Valid file types. Multi-platform projects use:
    # - "Extension" for Swift / Kotlin extension files (e.g. ItemListing+Status.swift,
    #   ItemListingExt.kt),
    # - "Component" for React functional components (.tsx),
    # - "Hook" for React custom hooks (.ts).
    VALID_FILE_TYPES = {
        "View", "ViewModel", "Layout", "Repository", "UseCase", "Model", "Test",
        "Extension", "Component", "Hook",
    }

    # Valid HTTP methods
    VALID_HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}

    def __init__(self, custom_rules: CustomRules | None = None):
        self._spec_file_path: Path | None = None
        self._spec_type: str = "screen_spec"  # or "component_spec"
        self._spec_data: dict | None = None
        self._custom_rules: CustomRules = custom_rules or CustomRules()
        self._build_effective_rules()

    def _build_effective_rules(self):
        """Build effective rule sets from base + custom rules."""
        self._effective_screen_component_types = (
            self.VALID_SCREEN_COMPONENT_TYPES | self._custom_rules.extra_screen_component_types
        )
        self._effective_component_types = (
            self.VALID_COMPONENT_TYPES | self._custom_rules.extra_component_types
        )
        self._effective_component_categories = (
            self.VALID_COMPONENT_CATEGORIES | self._custom_rules.extra_component_categories
        )
        self._effective_file_types = (
            self.VALID_FILE_TYPES | self._custom_rules.extra_file_types
        )

    def _matches_pattern_with_fallback(self, value: str, base_pattern: str, extra_patterns: list[str]) -> bool:
        """Check if value matches the base pattern or any extra pattern."""
        if re.match(base_pattern, value):
            return True
        for pattern in extra_patterns:
            if re.match(pattern, value):
                return True
        return False

    def _matches_variable_name(self, name: str) -> bool:
        return self._matches_pattern_with_fallback(
            name, r"^[a-z][a-zA-Z0-9]*$", self._custom_rules.extra_variable_patterns
        )

    def _matches_event_handler_name(self, name: str) -> bool:
        if name in self._custom_rules.allowed_event_handler_names:
            return True
        return self._matches_pattern_with_fallback(
            name, r"^on[A-Z][a-zA-Z0-9]*$", self._custom_rules.extra_event_handler_patterns
        )

    def _matches_prop_name(self, name: str) -> bool:
        return self._matches_pattern_with_fallback(
            name, r"^[a-z][a-zA-Z0-9]*$", self._custom_rules.extra_prop_patterns
        )

    def _matches_slot_name(self, name: str) -> bool:
        return self._matches_pattern_with_fallback(
            name, r"^[a-z][a-zA-Z0-9]*$", self._custom_rules.extra_slot_patterns
        )

    def _matches_internal_state_name(self, name: str) -> bool:
        return self._matches_pattern_with_fallback(
            name, r"^[a-z][a-zA-Z0-9]*$", self._custom_rules.extra_internal_state_patterns
        )

    def _matches_exposed_event_name(self, name: str) -> bool:
        if name in self._custom_rules.allowed_exposed_event_names:
            return True
        return self._matches_pattern_with_fallback(
            name, r"^on[A-Z][a-zA-Z0-9]*$", self._custom_rules.extra_exposed_event_patterns
        )

    def validate_file(self, file_path: Path) -> SpecValidationResult:
        """Validate a screen specification file."""
        self._spec_file_path = Path(file_path).resolve()
        result = SpecValidationResult(file_path=file_path)

        # Auto-discover custom rules if not explicitly provided
        if self._custom_rules.is_empty:
            self._custom_rules = load_rules_for_path(self._spec_file_path)
            self._build_effective_rules()

        # Read and parse JSON
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                result.spec_data = data
        except json.JSONDecodeError as e:
            result.errors.append(SpecValidationMessage(
                path=str(file_path),
                message=f"Invalid JSON: {e}"
            ))
            return result
        except Exception as e:
            result.errors.append(SpecValidationMessage(
                path=str(file_path),
                message=f"Cannot read file: {e}"
            ))
            return result

        # Determine spec type and validate
        spec_type = data.get("type", "screen_spec")
        self._spec_type = spec_type
        self._spec_data = data

        if spec_type == "component_spec":
            self._validate_component_spec(data, result)
        else:
            self._validate_spec(data, result)
        return result

    def validate_data(self, data: dict, name: str = "spec") -> SpecValidationResult:
        """Validate specification data directly."""
        result = SpecValidationResult(file_path=Path(name))
        result.spec_data = data

        spec_type = data.get("type", "screen_spec")
        self._spec_type = spec_type
        self._spec_data = data

        if spec_type == "component_spec":
            self._validate_component_spec(data, result)
        else:
            self._validate_spec(data, result)
        return result

    def _validate_spec(self, data: dict, result: SpecValidationResult):
        """Validate the specification structure."""
        spec_type = data.get("type", "screen_spec")

        # Check required top-level fields based on type
        if spec_type == "screen_sub_spec":
            self._validate_required_fields(data, ["type", "version", "metadata"], "", result)
        elif spec_type == "screen_parent_spec":
            self._validate_required_fields(data, ["type", "version", "metadata", "subSpecs"], "", result)
        else:
            self._validate_required_fields(data, ["type", "version", "metadata", "structure"], "", result)

        # Validate type
        valid_types = ("screen_spec", "screen_sub_spec", "screen_parent_spec")
        if spec_type not in valid_types:
            result.errors.append(SpecValidationMessage(
                path="type",
                message=f"Expected one of {valid_types}, got '{spec_type}'"
            ))

        # Validate version format
        version = data.get("version", "")
        if not re.match(r"^\d+\.\d+$", version):
            result.errors.append(SpecValidationMessage(
                path="version",
                message=f"Invalid version format: '{version}'. Expected 'X.Y' (e.g., '1.0')"
            ))

        # Validate metadata
        if "metadata" in data:
            self._validate_metadata(data["metadata"], result)

        # Validate structure
        if "structure" in data:
            self._validate_structure(data["structure"], result)

        # Validate subSpecs (for screen_parent_spec)
        if "subSpecs" in data:
            self._validate_sub_specs(data["subSpecs"], result)

        # Validate dataFlow
        if "dataFlow" in data and data["dataFlow"]:
            self._validate_data_flow(data["dataFlow"], result)

        # Validate stateManagement
        if "stateManagement" in data and data["stateManagement"]:
            self._validate_state_management(data["stateManagement"], result)

        # Validate userActions
        if "userActions" in data:
            self._validate_user_actions(data["userActions"], result)

        # Validate validation section
        if "validation" in data and data["validation"]:
            self._validate_validation_section(data["validation"], result)

        # Validate transitions
        if "transitions" in data:
            self._validate_transitions(data["transitions"], result)

        # Validate relatedFiles
        if "relatedFiles" in data:
            self._validate_related_files(data["relatedFiles"], result)

        # Cross-reference validation
        self._validate_cross_references(data, result)

    def _validate_required_fields(
        self, data: Any, required: list[str], path_prefix: str, result: SpecValidationResult
    ) -> bool:
        """Check that required fields are present. Returns False if data is not a dict."""
        if not isinstance(data, dict):
            result.errors.append(SpecValidationMessage(
                path=path_prefix or "(root)",
                message=f"Expected object, got {type(data).__name__}"
            ))
            return False
        for field_name in required:
            if field_name not in data:
                path = f"{path_prefix}.{field_name}" if path_prefix else field_name
                result.errors.append(SpecValidationMessage(
                    path=path,
                    message=f"Required field '{field_name}' is missing"
                ))
        return True

    def _validate_metadata(self, metadata: dict, result: SpecValidationResult):
        """Validate metadata section."""
        if self._spec_type == "screen_sub_spec":
            self._validate_required_fields(metadata, ["name", "description"], "metadata", result)
        else:
            self._validate_required_fields(metadata, ["name", "displayName", "description"], "metadata", result)

        # Validate name format (PascalCase for screen_spec, relaxed for screen_sub_spec)
        name = metadata.get("name", "")
        if name and self._spec_type != "screen_sub_spec" and not re.match(r"^[A-Z][a-zA-Z0-9]*$", name):
            result.errors.append(SpecValidationMessage(
                path="metadata.name",
                message=f"Name must be PascalCase: '{name}'"
            ))

        # Validate date formats
        for date_field in ["createdAt", "updatedAt"]:
            if date_field in metadata:
                date_value = metadata[date_field]
                if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_value):
                    result.warnings.append(SpecValidationMessage(
                        path=f"metadata.{date_field}",
                        message=f"Date should be YYYY-MM-DD format: '{date_value}'",
                        level="warning"
                    ))

    def _validate_sub_specs(self, sub_specs: list, result: SpecValidationResult):
        """Validate subSpecs section for screen_parent_spec."""
        if not isinstance(sub_specs, list):
            result.errors.append(SpecValidationMessage(
                path="subSpecs",
                message="subSpecs must be an array"
            ))
            return

        if len(sub_specs) == 0:
            result.errors.append(SpecValidationMessage(
                path="subSpecs",
                message="At least one sub-spec is required"
            ))
            return

        for i, sub_spec in enumerate(sub_specs):
            prefix = f"subSpecs[{i}]"
            self._validate_required_fields(sub_spec, ["file", "name"], prefix, result)

    def _parent_spec_has_layout_file(self) -> bool:
        """True when the current sub-spec declares a `metadata.parentSpec` that
        resolves to a spec with a non-empty `metadata.layoutFile`.

        Sub-specs do not (and should not) duplicate the parent's `layoutFile`;
        `jui build` merges them at generation time. Without this lookup, the
        standalone validator would wrongly require `structure.components` on
        every sub-spec even though the parent authors the UI externally.

        Returns False when parentSpec is missing, unresolvable, or malformed —
        caller falls back to the existing required-components check.
        """
        if self._spec_type != "screen_sub_spec":
            return False
        metadata = (self._spec_data or {}).get("metadata") or {}
        parent_ref = metadata.get("parentSpec")
        if not isinstance(parent_ref, str) or not parent_ref:
            return False
        if not self._spec_file_path:
            return False
        # parentSpec is resolved relative to the sub-spec file directory.
        candidate = (self._spec_file_path.parent / parent_ref).resolve()
        if not candidate.exists():
            # Try a sibling (same spec_directory) resolution as a fallback.
            candidate = (self._spec_file_path.parent.parent / parent_ref).resolve()
            if not candidate.exists():
                return False
        try:
            with open(candidate, "r", encoding="utf-8") as f:
                parent_data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return False
        parent_layout = (parent_data.get("metadata") or {}).get("layoutFile")
        return bool(parent_layout)

    def _validate_structure(self, structure: dict, result: SpecValidationResult):
        """Validate structure section."""
        # A sub-spec without its own layoutFile still counts as "has layout file"
        # when the declared parentSpec provides one, because `jui build` merges
        # the sub-spec into the parent and resolves the layout from there.
        has_layout_file = (
            bool((self._spec_data or {}).get("metadata", {}).get("layoutFile"))
            or self._parent_spec_has_layout_file()
        )

        if self._spec_type in ("screen_sub_spec", "screen_parent_spec"):
            # sub_spec: components required only when no layout file is inherited from parent.
            # parent_spec: structure is free-form (rootComponents, notes, etc.).
            if self._spec_type == "screen_sub_spec" and not has_layout_file:
                self._validate_required_fields(structure, ["components"], "structure", result)
        else:
            if not has_layout_file:
                self._validate_required_fields(structure, ["components", "layout"], "structure", result)

        # Collect all component IDs for cross-reference
        component_ids = set()

        # Validate components (not required for parent_spec or when layoutFile is set)
        components = structure.get("components", [])
        if not components and self._spec_type != "screen_parent_spec" and not has_layout_file:
            result.errors.append(SpecValidationMessage(
                path="structure.components",
                message="At least one component is required (or set metadata.layoutFile)"
            ))

        for i, comp in enumerate(components):
            self._validate_component(comp, f"structure.components[{i}]", result)
            self._collect_component_ids(
                comp, component_ids, f"structure.components[{i}]", result
            )

        # Validate decorative elements (new: A-2)
        for i, elem in enumerate(structure.get("decorativeElements", []) or []):
            self._validate_decorative_element(
                elem, f"structure.decorativeElements[{i}]", component_ids, result
            )

        # Validate wrapper views (new: A-6)
        for i, wv in enumerate(structure.get("wrapperViews", []) or []):
            self._validate_wrapper_view(
                wv, f"structure.wrapperViews[{i}]", component_ids, result
            )

        # Validate layout (skip when layoutFile is set — layout comes from external file)
        if "layout" in structure and not has_layout_file:
            self._validate_layout(structure["layout"], "structure.layout", component_ids, result)

        # Validate collection
        if "collection" in structure and structure["collection"]:
            self._validate_collection(structure["collection"], component_ids, result)

        # Validate tabView
        if "tabView" in structure and structure["tabView"]:
            self._validate_tab_view(structure["tabView"], result)

        # Validate embeds (cross-screen embedding — see specification-rules.md (5))
        if "embeds" in structure and structure["embeds"]:
            self._validate_embeds_section(structure["embeds"], result)

    def _collect_component_ids(
        self, comp: Any, component_ids: set, path: str, result: SpecValidationResult
    ) -> None:
        """Recursively collect component IDs (including nested children)
        and report duplicates."""
        if not isinstance(comp, dict):
            return
        cid = comp.get("id")
        if cid:
            if cid in component_ids:
                result.errors.append(SpecValidationMessage(
                    path=f"{path}.id",
                    message=f"Duplicate component ID: '{cid}'"
                ))
            component_ids.add(cid)
        children = comp.get("children") or []
        if isinstance(children, list):
            for j, child in enumerate(children):
                self._validate_component(
                    child, f"{path}.children[{j}]", result
                )
                self._collect_component_ids(
                    child, component_ids, f"{path}.children[{j}]", result
                )

    def _validate_component(self, comp: Any, path: str, result: SpecValidationResult):
        """Validate a single component in screen spec."""
        if not self._validate_required_fields(comp, ["type", "id", "description"], path, result):
            return

        # Validate type
        comp_type = comp.get("type", "")
        if comp_type and comp_type not in self._effective_screen_component_types:
            result.errors.append(SpecValidationMessage(
                path=f"{path}.type",
                message=f"Invalid component type: '{comp_type}'. Valid types: {', '.join(sorted(self._effective_screen_component_types))}"
            ))

        # Validate ID format (snake_case)
        comp_id = comp.get("id", "")
        if comp_id and not re.match(r"^[a-z][a-z0-9_]*$", comp_id):
            result.errors.append(SpecValidationMessage(
                path=f"{path}.id",
                message=f"ID must be snake_case: '{comp_id}'"
            ))

        # Validate optional style / binding / children (A-1)
        style = comp.get("style")
        if style is not None and not isinstance(style, dict):
            result.errors.append(SpecValidationMessage(
                path=f"{path}.style",
                message=f"'style' must be an object, got {type(style).__name__}"
            ))
        binding = comp.get("binding")
        if binding is not None:
            if not isinstance(binding, dict):
                result.errors.append(SpecValidationMessage(
                    path=f"{path}.binding",
                    message=f"'binding' must be an object, got {type(binding).__name__}"
                ))
            else:
                for k, v in binding.items():
                    if not isinstance(v, str):
                        result.errors.append(SpecValidationMessage(
                            path=f"{path}.binding.{k}",
                            message=(
                                f"binding value must be a string (variable name), "
                                f"got {type(v).__name__}"
                            )
                        ))
        children = comp.get("children")
        if children is not None and not isinstance(children, list):
            result.errors.append(SpecValidationMessage(
                path=f"{path}.children",
                message=f"'children' must be an array, got {type(children).__name__}"
            ))

    def _validate_decorative_element(
        self,
        elem: Any,
        path: str,
        component_ids: set,
        result: SpecValidationResult,
    ) -> None:
        """Validate a decorativeElements[] entry (A-2)."""
        if not isinstance(elem, dict):
            result.errors.append(SpecValidationMessage(
                path=path,
                message=f"Decorative element must be an object, got {type(elem).__name__}"
            ))
            return
        if not self._validate_required_fields(elem, ["id", "components"], path, result):
            return
        eid = elem.get("id", "")
        if eid and not re.match(r"^[a-z][a-z0-9_]*$", eid):
            result.errors.append(SpecValidationMessage(
                path=f"{path}.id",
                message=f"ID must be snake_case: '{eid}'"
            ))
        parent_id = elem.get("parentId")
        if parent_id and parent_id not in component_ids:
            result.warnings.append(SpecValidationMessage(
                path=f"{path}.parentId",
                message=f"parentId '{parent_id}' not found in components list",
                level="warning",
            ))
        comps = elem.get("components") or []
        if isinstance(comps, list):
            for j, child in enumerate(comps):
                self._validate_component(
                    child, f"{path}.components[{j}]", result
                )
                self._collect_component_ids(
                    child, component_ids, f"{path}.components[{j}]", result
                )

    def _validate_wrapper_view(
        self,
        wv: Any,
        path: str,
        component_ids: set,
        result: SpecValidationResult,
    ) -> None:
        """Validate a wrapperViews[] entry (A-6)."""
        if not isinstance(wv, dict):
            result.errors.append(SpecValidationMessage(
                path=path,
                message=f"Wrapper view must be an object, got {type(wv).__name__}"
            ))
            return
        if not self._validate_required_fields(wv, ["id", "wraps"], path, result):
            return
        wid = wv.get("id", "")
        if wid and not re.match(r"^[a-z][a-z0-9_]*$", wid):
            result.errors.append(SpecValidationMessage(
                path=f"{path}.id",
                message=f"ID must be snake_case: '{wid}'"
            ))
        wraps = wv.get("wraps", "")
        if wraps and wraps not in component_ids:
            result.warnings.append(SpecValidationMessage(
                path=f"{path}.wraps",
                message=f"wraps '{wraps}' not found in components list",
                level="warning",
            ))
        style = wv.get("style")
        if style is not None and not isinstance(style, dict):
            result.errors.append(SpecValidationMessage(
                path=f"{path}.style",
                message=f"'style' must be an object, got {type(style).__name__}"
            ))
        if wid:
            component_ids.add(wid)

    def _validate_layout(
        self, layout: dict, path: str, component_ids: set, result: SpecValidationResult
    ):
        """Validate layout structure."""
        self._validate_required_fields(layout, ["root", "children"], path, result)

        root = layout.get("root", "")
        if root and root not in component_ids:
            result.warnings.append(SpecValidationMessage(
                path=f"{path}.root",
                message=f"Root component '{root}' not found in components list",
                level="warning"
            ))

        # Validate children recursively
        children = layout.get("children", [])
        self._validate_layout_children(children, f"{path}.children", component_ids, result)

    def _validate_layout_children(
        self, children: list, path: str, component_ids: set, result: SpecValidationResult
    ):
        """Validate layout children recursively."""
        for i, child in enumerate(children):
            if isinstance(child, str):
                if child not in component_ids:
                    result.warnings.append(SpecValidationMessage(
                        path=f"{path}[{i}]",
                        message=f"Component '{child}' not found in components list",
                        level="warning"
                    ))
            elif isinstance(child, dict):
                child_id = child.get("id", "")
                if child_id and child_id not in component_ids:
                    result.warnings.append(SpecValidationMessage(
                        path=f"{path}[{i}].id",
                        message=f"Component '{child_id}' not found in components list",
                        level="warning"
                    ))
                if "children" in child:
                    self._validate_layout_children(
                        child["children"], f"{path}[{i}].children", component_ids, result
                    )

    def _validate_collection(self, collection: dict, component_ids: set, result: SpecValidationResult):
        """Validate collection structure.

        A collection must declare at least one of:
          * `cell` — single-cell layout (legacy / simple case),
          * `cellClasses` — non-empty array of cell refs (multi-cell Layout JSON),
          * `sections[].cell` — per-section cell refs (dynamic switching).

        Either the legacy single-cell schema OR the modern `cellClasses` +
        `sections` schema is accepted; both are valid and supported at the
        Layout JSON / runtime level.
        """
        self._validate_required_fields(collection, ["id"], "structure.collection", result)

        has_single_cell = "cell" in collection and collection.get("cell")
        has_cell_classes = (
            isinstance(collection.get("cellClasses"), list)
            and len(collection["cellClasses"]) > 0
        )
        sections = collection.get("sections")
        has_section_cells = (
            isinstance(sections, list)
            and any(isinstance(s, dict) and s.get("cell") for s in sections)
        )

        if not (has_single_cell or has_cell_classes or has_section_cells):
            result.errors.append(SpecValidationMessage(
                path="structure.collection",
                message=(
                    "Collection must declare at least one of: 'cell', "
                    "'cellClasses' (non-empty array), or 'sections[].cell'."
                ),
            ))

        # Validate the single-cell slot when present.
        #
        # cellNode has two schemas:
        #   1. Inline: {root, children, ...} — the old `layout` shape (root +
        #      children are required so the structure can be laid out directly).
        #   2. External: {root, layoutFile, uiVariables, ...} — root names the
        #      cell's root component, and the actual tree lives in
        #      {layouts_directory}/{layoutFile}.json. `children` is NOT required
        #      here (it would duplicate what's already in the external layout).
        #
        # _validate_layout enforces the inline shape. Route to it only when
        # the cell does not reference an external Layout JSON. The same rule
        # applies to header/footer slots.
        if has_single_cell and not _has_external_layout_ref(collection["cell"]):
            self._validate_layout(collection["cell"], "structure.collection.cell", component_ids, result)

        header = collection.get("header")
        if isinstance(header, dict) and not _has_external_layout_ref(header):
            self._validate_layout(header, "structure.collection.header", component_ids, result)

        footer = collection.get("footer")
        if isinstance(footer, dict) and not _has_external_layout_ref(footer):
            self._validate_layout(footer, "structure.collection.footer", component_ids, result)

    def _validate_tab_view(self, tab_view: dict, result: SpecValidationResult):
        """Validate tabView structure."""
        self._validate_required_fields(tab_view, ["id", "tabs"], "structure.tabView", result)

        tabs = tab_view.get("tabs", [])
        if not tabs:
            result.errors.append(SpecValidationMessage(
                path="structure.tabView.tabs",
                message="At least one tab is required"
            ))

        for i, tab in enumerate(tabs):
            if not self._validate_required_fields(tab, ["title", "layoutFile"], f"structure.tabView.tabs[{i}]", result):
                continue

    # Cross-screen embedding (Embed view type)
    # Spec form: structure.embeds[] = [{regionId, screen, params?, events?, navigationMode?}]
    # Layout form (validated by jui build, not here): {type: "Embed", id, screen, ...}
    # See specification-rules.md (5) and docs/plans/2026-05-11-embed-feature.md.

    # v1 supports 'delegate' only. 'isolated' (private nav stack) is
    # deferred to v1.5. Keep this tuple aligned with the navigationMode
    # enum in shared/core/attribute_definitions.json :: Embed.
    _EMBED_VALID_NAV_MODES = ("delegate",)

    def _validate_embeds_section(self, embeds: Any, result: SpecValidationResult) -> None:
        """Validate structure.embeds[] — local-only checks.

        Does NOT read the embedded screen's spec. Type contracts beyond
        key/binding existence are runtime responsibilities (v1 scope).
        """
        if not isinstance(embeds, list):
            result.errors.append(SpecValidationMessage(
                path="structure.embeds",
                message=f"embeds must be array, got {type(embeds).__name__}",
            ))
            return
        seen_region_ids: set[str] = set()
        for i, embed in enumerate(embeds):
            path = f"structure.embeds[{i}]"
            if not isinstance(embed, dict):
                result.errors.append(SpecValidationMessage(
                    path=path,
                    message=f"embed entry must be object, got {type(embed).__name__}",
                ))
                continue
            rid = embed.get("regionId")
            if isinstance(rid, str):
                if rid in seen_region_ids:
                    result.errors.append(SpecValidationMessage(
                        path=f"{path}.regionId",
                        message=f"Duplicate regionId: '{rid}'",
                    ))
                seen_region_ids.add(rid)
            self._validate_embed(embed, path, result)

    def _validate_embed(self, embed: dict, path: str, result: SpecValidationResult) -> None:
        """Validate a single structure.embeds[] entry."""
        # 0. regionId required + camelCase (matches Layout JSON Embed.id reference)
        rid = embed.get("regionId")
        if not rid:
            result.errors.append(SpecValidationMessage(
                path=f"{path}.regionId",
                message="Embed requires 'regionId'",
            ))
        elif not isinstance(rid, str) or not re.match(r"^[a-z][a-zA-Z0-9]*$", rid):
            result.errors.append(SpecValidationMessage(
                path=f"{path}.regionId",
                message=(
                    f"regionId must be camelCase (matches the Layout JSON "
                    f"Embed.id), got '{rid}'"
                ),
            ))

        # 1. screen required + snake_case layout JSON filename (no extension)
        screen = embed.get("screen")
        if not screen:
            result.errors.append(SpecValidationMessage(
                path=f"{path}.screen",
                message="Embed requires 'screen' attribute",
            ))
            return
        if not isinstance(screen, str) or not re.match(r"^[a-z][a-z0-9_]*$", screen):
            result.errors.append(SpecValidationMessage(
                path=f"{path}.screen",
                message=(
                    f"Embed.screen must be snake_case layout filename "
                    f"(no extension), got '{screen}'"
                ),
            ))

        # 2. screen reference: best-effort layout JSON file lookup
        if (
            isinstance(screen, str)
            and re.match(r"^[a-z][a-z0-9_]*$", screen)
            and self._spec_file_path
        ):
            spec_dir = self._spec_file_path.parent
            candidates = (
                list(spec_dir.glob(f"../layouts/{screen}.json"))
                + list(spec_dir.glob(f"../../layouts/{screen}.json"))
                + list(spec_dir.glob(f"**/layouts/{screen}.json"))
            )
            if not candidates:
                result.warnings.append(SpecValidationMessage(
                    path=f"{path}.screen",
                    message=(
                        f"Layout JSON '{screen}.json' not found near "
                        f"{spec_dir}. Make sure the embedded screen's "
                        f"layout exists."
                    ),
                    level="warning",
                ))

        # 3. params: object & camelCase keys & binding resolves to parent VM var
        params = embed.get("params")
        if params is not None:
            if not isinstance(params, dict):
                result.errors.append(SpecValidationMessage(
                    path=f"{path}.params",
                    message=f"params must be object, got {type(params).__name__}",
                ))
            else:
                vm_vars = self._collect_vm_var_names()
                for k, v in params.items():
                    if not re.match(r"^[a-z][a-zA-Z0-9]*$", k):
                        result.errors.append(SpecValidationMessage(
                            path=f"{path}.params.{k}",
                            message=f"params key must be camelCase, got '{k}'",
                        ))
                    if isinstance(v, str):
                        m = re.match(r"^@\{([a-zA-Z0-9_.]+)\}$", v)
                        if m and vm_vars:
                            head = m.group(1).split(".")[0]
                            if head not in vm_vars:
                                result.errors.append(SpecValidationMessage(
                                    path=f"{path}.params.{k}",
                                    message=(
                                        f"binding '{v}' references unknown var "
                                        f"'{head}'; not in dataFlow.viewModel.vars "
                                        f"or stateManagement.uiVariables"
                                    ),
                                ))

        # 4. navigationMode enum
        nav_mode = embed.get("navigationMode", "delegate")
        if nav_mode not in self._EMBED_VALID_NAV_MODES:
            result.errors.append(SpecValidationMessage(
                path=f"{path}.navigationMode",
                message=(
                    f"navigationMode must be one of "
                    f"{self._EMBED_VALID_NAV_MODES}, got '{nav_mode}'"
                ),
            ))

        # 5. events: object & on[A-Z]... keys & handler exists on parent VM
        events = embed.get("events")
        if events is not None:
            if not isinstance(events, dict):
                result.errors.append(SpecValidationMessage(
                    path=f"{path}.events",
                    message=f"events must be object, got {type(events).__name__}",
                ))
            else:
                handlers = self._collect_vm_handler_names()
                for k, v in events.items():
                    if not re.match(r"^on[A-Z][a-zA-Z0-9]*$", k):
                        result.errors.append(SpecValidationMessage(
                            path=f"{path}.events.{k}",
                            message=(
                                f"event key must match ^on[A-Z][a-zA-Z0-9]*$, "
                                f"got '{k}'"
                            ),
                        ))
                    if isinstance(v, str) and handlers and v not in handlers:
                        result.errors.append(SpecValidationMessage(
                            path=f"{path}.events.{k}",
                            message=(
                                f"handler '{v}' not found in "
                                f"dataFlow.viewModel.methods or "
                                f"stateManagement.eventHandlers"
                            ),
                        ))

    def _collect_vm_var_names(self) -> set[str]:
        """Names available as @{binding} sources from the parent VM.

        Returns empty set if the spec has no viewModel/uiVariables sections,
        which signals callers to skip the existence check (we cannot prove
        a binding is unresolvable without a contract).
        """
        if not isinstance(self._spec_data, dict):
            return set()
        names: set[str] = set()
        view_model = (self._spec_data.get("dataFlow") or {}).get("viewModel") or {}
        for var in view_model.get("vars", []) or []:
            if isinstance(var, dict) and isinstance(var.get("name"), str):
                names.add(var["name"])
        state_mgmt = self._spec_data.get("stateManagement") or {}
        for var in state_mgmt.get("uiVariables", []) or []:
            if isinstance(var, dict) and isinstance(var.get("name"), str):
                names.add(var["name"])
        return names

    def _collect_vm_handler_names(self) -> set[str]:
        """Names available as event handler targets on the parent VM.

        Returns empty set when neither section is present (skip check).
        """
        if not isinstance(self._spec_data, dict):
            return set()
        names: set[str] = set()
        view_model = (self._spec_data.get("dataFlow") or {}).get("viewModel") or {}
        for method in view_model.get("methods", []) or []:
            if isinstance(method, str):
                names.add(method)
            elif isinstance(method, dict) and isinstance(method.get("name"), str):
                names.add(method["name"])
        state_mgmt = self._spec_data.get("stateManagement") or {}
        for handler in state_mgmt.get("eventHandlers", []) or []:
            if isinstance(handler, dict) and isinstance(handler.get("name"), str):
                names.add(handler["name"])
        return names

    def _validate_data_flow(self, data_flow: dict, result: SpecValidationResult):
        """Validate dataFlow section."""
        # Validate Mermaid diagram
        diagram = data_flow.get("diagram", "")
        if diagram:
            self._validate_mermaid_diagram(diagram, result)

        # Validate viewModel (dataFlow.viewModel)
        view_model = data_flow.get("viewModel")
        if view_model is not None:
            self._validate_view_model(view_model, result)

        # Validate repositories
        repo_names = set()
        repos = data_flow.get("repositories", [])
        for i, repo in enumerate(repos):
            if not self._validate_required_fields(repo, ["name", "methods"], f"dataFlow.repositories[{i}]", result):
                continue
            repo_name = repo.get("name", "")
            if repo_name:
                repo_names.add(repo_name)
            # Validate structured method params
            for j, method in enumerate(repo.get("methods", [])):
                if isinstance(method, dict):
                    self._validate_repository_method(method, f"dataFlow.repositories[{i}].methods[{j}]", result)

        # Validate useCases
        use_cases = data_flow.get("useCases", [])
        for i, uc in enumerate(use_cases):
            if not self._validate_required_fields(uc, ["name", "methods"], f"dataFlow.useCases[{i}]", result):
                continue
            # Validate that referenced repositories exist
            for dep_repo in uc.get("repositories", []):
                if repo_names and dep_repo not in repo_names:
                    result.warnings.append(SpecValidationMessage(
                        path=f"dataFlow.useCases[{i}].repositories",
                        message=f"Referenced repository '{dep_repo}' not found in dataFlow.repositories",
                        level="warning"
                    ))
            # Validate methods
            for j, method in enumerate(uc.get("methods", [])):
                if isinstance(method, dict):
                    self._validate_repository_method(method, f"dataFlow.useCases[{i}].methods[{j}]", result)

        # Validate API endpoints
        endpoints = data_flow.get("apiEndpoints", [])
        for i, endpoint in enumerate(endpoints):
            if not self._validate_required_fields(endpoint, ["path", "method"], f"dataFlow.apiEndpoints[{i}]", result):
                continue

            method = endpoint.get("method", "")
            if method and method not in self.VALID_HTTP_METHODS:
                result.errors.append(SpecValidationMessage(
                    path=f"dataFlow.apiEndpoints[{i}].method",
                    message=f"Invalid HTTP method: '{method}'. Valid methods: {', '.join(self.VALID_HTTP_METHODS)}"
                ))

    # Swift-only / iOS-only type tokens that do not compile on Kotlin / TS
    # when used without a platforms: ["ios"] filter.
    _IOS_ONLY_TOKENS = ("inout ", "UIImage", "CGImage", "NSImage", "AnyView")

    def _validate_repository_method(self, method: dict, path: str, result: SpecValidationResult):
        """Validate a structured repositoryMethod object."""
        if "name" not in method:
            result.errors.append(SpecValidationMessage(
                path=path, message="Required field 'name' is missing"
            ))
        # Validate structured params
        params = method.get("params")
        if isinstance(params, list):
            for k, param in enumerate(params):
                if isinstance(param, dict):
                    self._validate_required_fields(param, ["name", "type"], f"{path}.params[{k}]", result)

        # Warn about iOS-only types when the method isn't scoped to iOS
        platforms = method.get("platforms") or []
        is_ios_only = isinstance(platforms, list) and platforms == ["ios"]
        if not is_ios_only:
            type_strings: list[str] = []
            if isinstance(params, list):
                for param in params:
                    if isinstance(param, dict):
                        t = param.get("type")
                        if isinstance(t, str):
                            type_strings.append(t)
            ret = method.get("returnType")
            if isinstance(ret, str):
                type_strings.append(ret)
            # Tuple types on a multi-platform method need an explicit mapping.
            for ts in type_strings:
                if ts.startswith("(") and ts.endswith(")") and ":" in ts:
                    result.warnings.append(SpecValidationMessage(
                        path=f"{path}.returnType" if ts == ret else f"{path}.params",
                        message=(
                            f"Swift tuple type '{ts}' has no automatic Kotlin/TS "
                            "equivalent — scope the method with platforms: [\"ios\"] "
                            "or split into a dedicated data class."
                        ),
                        level="warning",
                    ))
                for tok in self._IOS_ONLY_TOKENS:
                    if tok in ts:
                        result.warnings.append(SpecValidationMessage(
                            path=f"{path}.returnType" if ts == ret else f"{path}.params",
                            message=(
                                f"Type contains iOS-only token '{tok.strip()}' — "
                                "add platforms: [\"ios\"] to keep this method out of "
                                "Android/Web code generation."
                            ),
                            level="warning",
                        ))
                        break

    def _validate_view_model(self, view_model: dict, result: SpecValidationResult):
        """Validate ``dataFlow.viewModel`` (methods + vars)."""
        if not isinstance(view_model, dict):
            result.errors.append(SpecValidationMessage(
                path="dataFlow.viewModel",
                message="viewModel must be an object",
            ))
            return

        valid_platforms = {"ios", "android", "web"}

        methods = view_model.get("methods", []) or []
        method_names: set[str] = set()
        for i, method in enumerate(methods):
            path = f"dataFlow.viewModel.methods[{i}]"
            if isinstance(method, str):
                if method in method_names:
                    result.errors.append(SpecValidationMessage(
                        path=path, message=f"Duplicate method name '{method}'"
                    ))
                method_names.add(method)
                continue
            if not isinstance(method, dict):
                result.errors.append(SpecValidationMessage(
                    path=path, message="Method entry must be string or object"
                ))
                continue
            name = method.get("name")
            if not name:
                result.errors.append(SpecValidationMessage(
                    path=path, message="Required field 'name' is missing"
                ))
                continue
            if name in method_names:
                result.errors.append(SpecValidationMessage(
                    path=path, message=f"Duplicate method name '{name}'"
                ))
            method_names.add(name)
            # Reuse the existing signature/platform checks.
            self._validate_repository_method(method, path, result)

        vars_list = view_model.get("vars", []) or []
        var_names: set[str] = set()
        for i, var in enumerate(vars_list):
            path = f"dataFlow.viewModel.vars[{i}]"
            if not isinstance(var, dict):
                result.errors.append(SpecValidationMessage(
                    path=path, message="Var entry must be an object"
                ))
                continue
            if not self._validate_required_fields(var, ["name", "type"], path, result):
                continue
            name = var.get("name", "")
            if name in var_names:
                result.errors.append(SpecValidationMessage(
                    path=path, message=f"Duplicate var name '{name}'"
                ))
            var_names.add(name)

            if "platforms" in var:
                pf = var.get("platforms")
                if not isinstance(pf, list):
                    result.errors.append(SpecValidationMessage(
                        path=f"{path}.platforms",
                        message="platforms must be an array of ['ios', 'android', 'web']",
                    ))
                else:
                    invalid = [p for p in pf if p not in valid_platforms]
                    if invalid:
                        result.errors.append(SpecValidationMessage(
                            path=f"{path}.platforms",
                            message=(
                                f"platforms contains invalid values {invalid!r}; "
                                "allowed: ['ios', 'android', 'web']"
                            ),
                        ))
                    elif not pf:
                        result.warnings.append(SpecValidationMessage(
                            path=f"{path}.platforms",
                            message=(
                                f"vars['{name}'].platforms is [] — var will "
                                "not be auto-imported into any Protocol."
                            ),
                            level="warning",
                        ))

    def _validate_mermaid_diagram(self, diagram: str, result: SpecValidationResult):
        """Validate Mermaid diagram syntax."""
        # Check for unquoted paths with slashes in brackets
        # Pattern: [/something] without quotes - this causes Mermaid syntax errors
        # Correct: ["/api/v1/users"] or ["text with /"]
        # Wrong: [/api/v1/users]
        unquoted_slash_pattern = re.compile(r'\[[^\]"]*\/[^\]"]*\]')
        matches = unquoted_slash_pattern.findall(diagram)
        if matches:
            result.errors.append(SpecValidationMessage(
                path="dataFlow.diagram",
                message=f"Mermaid syntax error: Paths with '/' must be quoted. Found: {matches[0]}. Use [\"/api/path\"] instead of [/api/path]"
            ))

    def _validate_state_management(self, state_mgmt: dict, result: SpecValidationResult):
        """Validate stateManagement section."""
        # Validate states
        states = state_mgmt.get("states", [])
        for i, state in enumerate(states):
            if not self._validate_required_fields(state, ["name", "values"], f"stateManagement.states[{i}]", result):
                continue
            values = state.get("values", [])
            if not values:
                result.errors.append(SpecValidationMessage(
                    path=f"stateManagement.states[{i}].values",
                    message="At least one state value is required"
                ))
            for j, val in enumerate(values):
                if not self._validate_required_fields(
                    val, ["value", "description"],
                    f"stateManagement.states[{i}].values[{j}]", result
                ):
                    continue

        # Validate UI variables
        variables = state_mgmt.get("uiVariables", [])
        for i, var in enumerate(variables):
            if not self._validate_required_fields(
                var, ["name", "type", "description"],
                f"stateManagement.uiVariables[{i}]", result
            ):
                continue
            # Validate camelCase
            var_name = var.get("name", "")
            if var_name and not self._matches_variable_name(var_name):
                result.errors.append(SpecValidationMessage(
                    path=f"stateManagement.uiVariables[{i}].name",
                    message=f"Variable name must be camelCase: '{var_name}'"
                ))

        # Validate event handlers — View-local, simple name+description.
        handlers = state_mgmt.get("eventHandlers", [])
        for i, handler in enumerate(handlers):
            if not self._validate_required_fields(
                handler, ["name", "description"],
                f"stateManagement.eventHandlers[{i}]", result
            ):
                continue
            handler_name = handler.get("name", "")
            if handler_name and not self._matches_event_handler_name(handler_name):
                result.errors.append(SpecValidationMessage(
                    path=f"stateManagement.eventHandlers[{i}].name",
                    message=f"Handler name must start with 'on' followed by PascalCase: '{handler_name}'"
                ))

        # Validate display logic
        logic_rules = state_mgmt.get("displayLogic", [])
        for i, rule in enumerate(logic_rules):
            if not isinstance(rule, dict):
                result.errors.append(SpecValidationMessage(
                    path=f"stateManagement.displayLogic[{i}]",
                    message=f"Display logic rule must be an object, got {type(rule).__name__}"
                ))
                continue
            self._validate_required_fields(
                rule, ["condition", "effects"],
                f"stateManagement.displayLogic[{i}]", result
            )
            effects = rule.get("effects", [])
            for j, effect in enumerate(effects):
                if not isinstance(effect, dict):
                    result.errors.append(SpecValidationMessage(
                        path=f"stateManagement.displayLogic[{i}].effects[{j}]",
                        message=f"Effect must be an object, got {type(effect).__name__}"
                    ))
                    continue
                self._validate_required_fields(
                    effect, ["element", "state"],
                    f"stateManagement.displayLogic[{i}].effects[{j}]", result
                )
                # Validate optional variableName
                var_name = effect.get("variableName")
                if var_name is not None:
                    if not isinstance(var_name, str) or not var_name:
                        result.errors.append(SpecValidationMessage(
                            path=f"stateManagement.displayLogic[{i}].effects[{j}].variableName",
                            message=(
                                f"variableName must be a non-empty string, "
                                f"got {var_name!r}"
                            )
                        ))
                    elif not self._matches_variable_name(var_name):
                        result.errors.append(SpecValidationMessage(
                            path=f"stateManagement.displayLogic[{i}].effects[{j}].variableName",
                            message=(
                                f"variableName must be camelCase starting with a "
                                f"lowercase letter: {var_name!r}"
                            )
                        ))

    def _validate_user_actions(self, actions: list, result: SpecValidationResult):
        """Validate userActions section."""
        for i, action in enumerate(actions):
            if not self._validate_required_fields(
                action, ["action", "processing"],
                f"userActions[{i}]", result
            ):
                continue

    def _validate_validation_section(self, validation: dict, result: SpecValidationResult):
        """Validate the validation section."""
        # Client-side validations
        client_validations = validation.get("clientSide", [])
        for i, val in enumerate(client_validations):
            if not self._validate_required_fields(
                val, ["field", "rule"],
                f"validation.clientSide[{i}]", result
            ):
                continue

        # Server-side validations
        server_validations = validation.get("serverSide", [])
        for i, val in enumerate(server_validations):
            if not self._validate_required_fields(
                val, ["condition", "handling"],
                f"validation.serverSide[{i}]", result
            ):
                continue

    def _validate_transitions(self, transitions: list, result: SpecValidationResult):
        """Validate transitions section."""
        for i, trans in enumerate(transitions):
            if not self._validate_required_fields(
                trans, ["condition", "destination"],
                f"transitions[{i}]", result
            ):
                continue

    def _validate_related_files(self, files: list, result: SpecValidationResult):
        """Validate relatedFiles section."""
        for i, file_info in enumerate(files):
            if not self._validate_required_fields(
                file_info, ["type", "path"],
                f"relatedFiles[{i}]", result
            ):
                continue
            file_type = file_info.get("type", "")
            if file_type and file_type not in self._effective_file_types:
                result.errors.append(SpecValidationMessage(
                    path=f"relatedFiles[{i}].type",
                    message=f"Invalid file type: '{file_type}'. Valid types: {', '.join(sorted(self._effective_file_types))}"
                ))

    def _validate_cross_references(self, data: dict, result: SpecValidationResult):
        """Validate cross-references between sections."""
        # Skip cross-reference checks when layoutFile is set — components live
        # in the Layout JSON, not in the spec. Sub-specs inherit the parent's
        # layoutFile (via metadata.parentSpec), so check the parent too.
        has_layout_file = (
            bool(data.get("metadata", {}).get("layoutFile"))
            or self._parent_spec_has_layout_file()
        )
        if has_layout_file:
            return

        # Collect all component IDs
        component_ids = set()
        structure = data.get("structure", {})
        for comp in structure.get("components", []):
            if isinstance(comp, dict) and "id" in comp:
                component_ids.add(comp["id"])

        # Check displayLogic element references
        state_mgmt = data.get("stateManagement", {})
        for i, rule in enumerate(state_mgmt.get("displayLogic", [])):
            if not isinstance(rule, dict):
                continue
            for j, effect in enumerate(rule.get("effects", [])):
                if not isinstance(effect, dict):
                    continue
                element = effect.get("element", "")
                if element and element not in component_ids:
                    result.warnings.append(SpecValidationMessage(
                        path=f"stateManagement.displayLogic[{i}].effects[{j}].element",
                        message=f"Element '{element}' not found in components list",
                        level="warning"
                    ))

        # Check state visibleElements references
        for i, state in enumerate(state_mgmt.get("states", [])):
            if not isinstance(state, dict):
                continue
            for j, val in enumerate(state.get("values", [])):
                if not isinstance(val, dict):
                    continue
                for element in val.get("visibleElements", []):
                    if element not in component_ids:
                        result.warnings.append(SpecValidationMessage(
                            path=f"stateManagement.states[{i}].values[{j}].visibleElements",
                            message=f"Element '{element}' not found in components list",
                            level="warning"
                        ))

    # ========== Component Spec Validation ==========

    def _validate_component_spec(self, data: dict, result: SpecValidationResult):
        """Validate the component specification structure."""
        # Check required top-level fields
        self._validate_required_fields(data, ["type", "version", "metadata", "structure"], "", result)

        # Validate type
        if data.get("type") != "component_spec":
            result.errors.append(SpecValidationMessage(
                path="type",
                message=f"Expected 'component_spec', got '{data.get('type')}'"
            ))

        # Validate version format
        version = data.get("version", "")
        if not re.match(r"^\d+\.\d+$", version):
            result.errors.append(SpecValidationMessage(
                path="version",
                message=f"Invalid version format: '{version}'. Expected 'X.Y' (e.g., '1.0')"
            ))

        # Validate metadata
        if "metadata" in data:
            self._validate_component_metadata(data["metadata"], result)

        # Validate props
        if "props" in data and data["props"]:
            self._validate_props(data["props"], result)

        # Validate slots
        if "slots" in data and data["slots"]:
            self._validate_slots(data["slots"], result)

        # Validate structure
        if "structure" in data:
            self._validate_component_structure(data["structure"], result)

        # Validate stateManagement
        if "stateManagement" in data and data["stateManagement"]:
            self._validate_component_state_management(data["stateManagement"], result)

        # Validate usage
        if "usage" in data and data["usage"]:
            self._validate_usage(data["usage"], result)

    def _validate_component_metadata(self, metadata: dict, result: SpecValidationResult):
        """Validate component metadata section."""
        self._validate_required_fields(metadata, ["name", "displayName", "description"], "metadata", result)

        # Validate name format (PascalCase)
        name = metadata.get("name", "")
        if name and not re.match(r"^[A-Z][a-zA-Z0-9]*$", name):
            result.errors.append(SpecValidationMessage(
                path="metadata.name",
                message=f"Name must be PascalCase: '{name}'"
            ))

        # Validate category
        category = metadata.get("category", "")
        if category and category not in self._effective_component_categories:
            result.warnings.append(SpecValidationMessage(
                path="metadata.category",
                message=f"Unknown category: '{category}'. Valid categories: {', '.join(sorted(self._effective_component_categories))}",
                level="warning"
            ))

        # Validate date formats
        for date_field in ["createdAt", "updatedAt"]:
            if date_field in metadata:
                date_value = metadata[date_field]
                if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_value):
                    result.warnings.append(SpecValidationMessage(
                        path=f"metadata.{date_field}",
                        message=f"Date should be YYYY-MM-DD format: '{date_value}'",
                        level="warning"
                    ))

    def _validate_props(self, props: dict, result: SpecValidationResult):
        """Validate props section."""
        items = props.get("items", [])
        prop_names = set()

        for i, prop in enumerate(items):
            if not self._validate_required_fields(
                prop, ["name", "type", "description"],
                f"props.items[{i}]", result
            ):
                continue

            # Validate camelCase
            prop_name = prop.get("name", "")
            if prop_name:
                if not self._matches_prop_name(prop_name):
                    result.errors.append(SpecValidationMessage(
                        path=f"props.items[{i}].name",
                        message=f"Prop name must be camelCase: '{prop_name}'"
                    ))
                if prop_name in prop_names:
                    result.errors.append(SpecValidationMessage(
                        path=f"props.items[{i}].name",
                        message=f"Duplicate prop name: '{prop_name}'"
                    ))
                prop_names.add(prop_name)

    def _validate_slots(self, slots: dict, result: SpecValidationResult):
        """Validate slots section."""
        items = slots.get("items", [])
        slot_names = set()

        for i, slot in enumerate(items):
            if not self._validate_required_fields(
                slot, ["name", "description"],
                f"slots.items[{i}]", result
            ):
                continue

            # Validate camelCase
            slot_name = slot.get("name", "")
            if slot_name:
                if not self._matches_slot_name(slot_name):
                    result.errors.append(SpecValidationMessage(
                        path=f"slots.items[{i}].name",
                        message=f"Slot name must be camelCase: '{slot_name}'"
                    ))
                if slot_name in slot_names:
                    result.errors.append(SpecValidationMessage(
                        path=f"slots.items[{i}].name",
                        message=f"Duplicate slot name: '{slot_name}'"
                    ))
                slot_names.add(slot_name)

    def _validate_component_structure(self, structure: dict, result: SpecValidationResult):
        """Validate component structure section."""
        self._validate_required_fields(structure, ["components", "layout"], "structure", result)

        # Collect all component IDs for cross-reference
        component_ids = set()

        # Validate components
        components = structure.get("components", [])
        if not components:
            result.errors.append(SpecValidationMessage(
                path="structure.components",
                message="At least one component is required"
            ))

        for i, comp in enumerate(components):
            self._validate_component_part(comp, f"structure.components[{i}]", result)
            if isinstance(comp, dict) and "id" in comp:
                if comp["id"] in component_ids:
                    result.errors.append(SpecValidationMessage(
                        path=f"structure.components[{i}].id",
                        message=f"Duplicate component ID: '{comp['id']}'"
                    ))
                component_ids.add(comp["id"])

        # Validate layout
        if "layout" in structure:
            self._validate_layout(structure["layout"], "structure.layout", component_ids, result)

    def _validate_component_part(self, comp: Any, path: str, result: SpecValidationResult):
        """Validate a single component in component spec."""
        if not self._validate_required_fields(comp, ["type", "id", "description"], path, result):
            return

        # Validate type (component spec has limited types)
        comp_type = comp.get("type", "")
        if comp_type and comp_type not in self._effective_component_types:
            result.errors.append(SpecValidationMessage(
                path=f"{path}.type",
                message=f"Invalid component type: '{comp_type}'. Valid types: {', '.join(sorted(self._effective_component_types))}"
            ))

        # Validate ID format (snake_case)
        comp_id = comp.get("id", "")
        if comp_id and not re.match(r"^[a-z][a-z0-9_]*$", comp_id):
            result.errors.append(SpecValidationMessage(
                path=f"{path}.id",
                message=f"ID must be snake_case: '{comp_id}'"
            ))

    def _validate_component_state_management(self, state_mgmt: dict, result: SpecValidationResult):
        """Validate component stateManagement section."""
        # Validate internal states
        internal_states = state_mgmt.get("internalStates", [])
        for i, state in enumerate(internal_states):
            if not self._validate_required_fields(
                state, ["name", "type", "description"],
                f"stateManagement.internalStates[{i}]", result
            ):
                continue
            # Validate camelCase
            state_name = state.get("name", "")
            if state_name and not self._matches_internal_state_name(state_name):
                result.errors.append(SpecValidationMessage(
                    path=f"stateManagement.internalStates[{i}].name",
                    message=f"State name must be camelCase: '{state_name}'"
                ))

        # Validate exposed events
        events = state_mgmt.get("exposedEvents", [])
        for i, event in enumerate(events):
            if not self._validate_required_fields(
                event, ["name", "description"],
                f"stateManagement.exposedEvents[{i}]", result
            ):
                continue
            # Validate onXxx pattern (or custom allowed names)
            event_name = event.get("name", "")
            if event_name and not self._matches_exposed_event_name(event_name):
                result.errors.append(SpecValidationMessage(
                    path=f"stateManagement.exposedEvents[{i}].name",
                    message=f"Event name must start with 'on' followed by PascalCase: '{event_name}'"
                ))

            # Validate parameters
            params = event.get("parameters", [])
            for j, param in enumerate(params):
                if not self._validate_required_fields(
                    param, ["name", "type"],
                    f"stateManagement.exposedEvents[{i}].parameters[{j}]", result
                ):
                    continue

    def _validate_usage(self, usage: dict, result: SpecValidationResult):
        """Validate usage section."""
        # Just warnings for empty sections
        if not usage.get("example") and not usage.get("usedInScreens"):
            result.warnings.append(SpecValidationMessage(
                path="usage",
                message="Consider adding usage example or listing screens that use this component",
                level="warning"
            ))
