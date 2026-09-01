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
from .. import shared_core


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
        # api_directory -> canonical route index. `validate all` walks many
        # specs of one project; the OpenAPI documents are read once.
        self._api_index_cache: dict[Path, dict[str, dict[str, str]]] = {}
        self._api_yaml_skip_reported: bool = False
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
        # A parent spec is a container: the merger builds its sections from
        # the sub-specs, and anything declared here is discarded without a
        # word. Refused at authoring time so it never reaches `jui build`,
        # from the same rule the merger halts on.
        self._reject_parent_declarations(data, result)

        if "dataFlow" in data and data["dataFlow"]:
            # First: every check below, and the HTML the doc site renders,
            # must see what `jui build` will generate from — not the mark.
            self._resolve_canonical_marks(data, result)
            self._validate_data_flow(data["dataFlow"], result)
            # Declared routes against the project's OpenAPI canonical
            # (skipped when the project has no readable API documents).
            self._validate_api_endpoint_canonical(data, result)

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

        # Validate branchContracts (opt-in — absent section changes nothing)
        if "branchContracts" in data and data["branchContracts"]:
            self._validate_branch_contracts(data["branchContracts"], result)
            self._validate_branch_cross_faces(data, result)

        # Validate relatedFiles
        if "relatedFiles" in data:
            self._validate_related_files(data["relatedFiles"], result)

        # `metadata.layoutFile` names the Layout JSON this spec documents,
        # and was read for its CONTENTS without anything asking whether it
        # was there. `jui verify` does catch an unresolvable one, but only
        # under `--fail-on-diff`, and this gate is the one a spec author
        # runs.
        self._check_layout_ref(
            (data.get("metadata") or {}).get("layoutFile"),
            "metadata.layoutFile", result, what="metadata.layoutFile")

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

        # Validate collection(s). `structure.collections` (array) is the
        # multi-Collection form — screens with several Collections declare
        # each cell's typed data there (doc-spec-schema-single-collection-only).
        if "collection" in structure and structure["collection"]:
            self._validate_collection(structure["collection"], component_ids, result)
        collections = structure.get("collections")
        if isinstance(collections, list):
            for i, coll in enumerate(collections):
                coll_path = f"structure.collections[{i}]"
                if isinstance(coll, dict):
                    self._validate_collection(coll, component_ids, result, path=coll_path)
                else:
                    result.errors.append(SpecValidationMessage(
                        path=coll_path,
                        message="Each structure.collections entry must be an object",
                    ))

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

    def _validate_collection(self, collection: dict, component_ids: set, result: SpecValidationResult, path: str = "structure.collection"):
        """Validate collection structure.

        A collection must declare at least one of:
          * `cell` — single-cell layout (legacy / simple case),
          * `cellClasses` — non-empty array of cell refs (multi-cell Layout JSON),
          * `sections[].cell` — per-section cell refs (dynamic switching).

        Either the legacy single-cell schema OR the modern `cellClasses` +
        `sections` schema is accepted; both are valid and supported at the
        Layout JSON / runtime level.
        """
        self._validate_required_fields(collection, ["id"], path, result)

        # Each entry names a cell Layout JSON. The shape check below only
        # asks that the array is non-empty, so a name that resolves to
        # nothing counted as a satisfied declaration.
        for index, ref in enumerate(collection.get("cellClasses") or []):
            self._check_layout_ref(ref, f"{path}.cellClasses[{index}]",
                                   result, what="cellClasses entry")

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
                path=path,
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
            self._validate_layout(collection["cell"], f"{path}.cell", component_ids, result)

        header = collection.get("header")
        if isinstance(header, dict) and not _has_external_layout_ref(header):
            self._validate_layout(header, f"{path}.header", component_ids, result)

        footer = collection.get("footer")
        if isinstance(footer, dict) and not _has_external_layout_ref(footer):
            self._validate_layout(footer, f"{path}.footer", component_ids, result)

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

            # `request` / `response` are field -> type objects. A bare schema
            # name reads as a reference but is not one: nothing resolves it,
            # so the HTML renders the name as a quoted string and the
            # markdown generator raised a bare AttributeError naming neither
            # the field nor the spec. Caught here so the mistake is reported
            # where it was made, with the path — the generators are not the
            # place to learn that a spec is wrong.
            for field in ("request", "response"):
                value = endpoint.get(field)
                if value is not None and not isinstance(value, dict):
                    kind = type(value).__name__
                    result.errors.append(SpecValidationMessage(
                        path=f"dataFlow.apiEndpoints[{i}].{field}",
                        message=(
                            f"'{field}' must be an object of field -> type "
                            f"(e.g. {{\"message\": \"string\"}}), got {kind}"
                            + (f" '{value}'" if isinstance(value, str) else "")
                            + ". A schema name on its own is not resolved by "
                            "anything — write the fields out."
                        )
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

    # ========== Branch Contracts (opt-in) ==========
    #
    # branchContracts declares machine-checkable branch tables for VM/UseCase
    # methods. The vocabulary is CLOSED by design (docs/plans/2026-08-24-spec-
    # branch-declarations-feasibility.md + P0 pilot):
    #   when : data.<field> / arg.<name> / api.<op> (named mock scenario) /
    #          cond (named condition reference, '!' prefix allowed)
    #   then : data.<field> (literal, '@strings_key', '@data.<field>') /
    #          transition / api ('none') / api.<op> ('called'|'not-called') /
    #          api.<op>.request (partial request-body object)
    # Branches outside the vocabulary are {note} entries — allowed, counted
    # by the doc generator, never validated as contracts.
    #
    # Reference checks follow the validator-wide convention: when the
    # referenced declaration section is ABSENT we skip the existence check
    # (cannot prove a reference dangling without a contract). Unknown KEYS in
    # the closed sets are always errors; unknown data-field NAMES are
    # warnings (VM-internal state may intentionally stay undeclared).

    _BRANCH_THEN_API_VERDICTS = ("called", "not-called")

    def _validate_branch_contracts(self, bc: Any, result: SpecValidationResult):
        if not isinstance(bc, dict):
            result.errors.append(SpecValidationMessage(
                path="branchContracts",
                message=f"branchContracts must be an object, got {type(bc).__name__}",
            ))
            return
        for key in bc:
            if key not in ("conditions", "methods", "notes", "seedableState"):
                result.errors.append(SpecValidationMessage(
                    path=f"branchContracts.{key}",
                    message=(
                        "Unknown branchContracts key — allowed: "
                        "'conditions', 'methods', 'notes', 'seedableState'"
                    ),
                ))

        seedable = self._validate_seedable_state(bc.get("seedableState"), result)
        data_fields = self._collect_branch_data_fields()
        condition_names = self._validate_branch_conditions(
            bc.get("conditions"), data_fields, result, seedable
        )
        self._validate_branch_condition_usage(bc, condition_names, result)
        self._validate_branch_arg_bindings(bc, result)

        methods = bc.get("methods")
        if methods is None:
            return
        if not isinstance(methods, dict):
            result.errors.append(SpecValidationMessage(
                path="branchContracts.methods",
                message=f"methods must be an object, got {type(methods).__name__}",
            ))
            return
        declared_methods = self._collect_vm_handler_names()
        api_ops = self._collect_branch_api_ops()
        transition_dests = self._collect_transition_destinations()
        for method_name, contract in methods.items():
            path = f"branchContracts.methods.{method_name}"
            if declared_methods and method_name not in declared_methods:
                result.errors.append(SpecValidationMessage(
                    path=path,
                    message=(
                        f"Method '{method_name}' not found in "
                        "dataFlow.viewModel.methods or "
                        "stateManagement.eventHandlers"
                    ),
                ))
            self._validate_branch_method_contract(
                contract, path, data_fields, condition_names,
                api_ops, transition_dests, result, seedable
            )

    def _collect_branch_data_fields(self) -> set[str]:
        """Data-field names data.* / witness keys may reference.

        uiVariables + viewModel.vars (same surface as @{binding} sources)
        plus stateManagement.states[].name (state enums are data too).
        Empty set signals callers to skip existence checks.
        """
        names = self._collect_vm_var_names()
        state_mgmt = (self._spec_data or {}).get("stateManagement") or {}
        for state in state_mgmt.get("states", []) or []:
            if isinstance(state, dict) and isinstance(state.get("name"), str):
                names.add(state["name"])
        return names

    def _collect_branch_api_ops(self) -> set[str]:
        """Method names declared under dataFlow repositories/useCases.

        api.<op> references are checked against these (warning-level —
        an op may legitimately be an operation id the spec never lists).
        """
        names: set[str] = set()
        data_flow = (self._spec_data or {}).get("dataFlow") or {}
        for section in ("repositories", "useCases"):
            for entry in data_flow.get(section, []) or []:
                if not isinstance(entry, dict):
                    continue
                for method in entry.get("methods", []) or []:
                    if isinstance(method, str):
                        # Free-text signature — take the leading identifier.
                        m = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)", method)
                        if m:
                            names.add(m.group(1))
                    elif isinstance(method, dict) and isinstance(method.get("name"), str):
                        names.add(method["name"])
        return names

    def _collect_transition_destinations(self) -> set[str]:
        names: set[str] = set()
        for trans in (self._spec_data or {}).get("transitions", []) or []:
            if isinstance(trans, dict) and isinstance(trans.get("destination"), str):
                names.add(trans["destination"])
        return names

    def _validate_branch_conditions(
        self, conditions: Any, data_fields: set[str],
        result: SpecValidationResult, seedable: set[str] | None = None,
    ) -> set[str]:
        """Validate branchContracts.conditions. Returns declared names."""
        names: set[str] = set()
        if conditions is None:
            return names
        if not isinstance(conditions, dict):
            result.errors.append(SpecValidationMessage(
                path="branchContracts.conditions",
                message=f"conditions must be an object, got {type(conditions).__name__}",
            ))
            return names
        for name, cond in conditions.items():
            path = f"branchContracts.conditions.{name}"
            if not self._matches_variable_name(name):
                result.errors.append(SpecValidationMessage(
                    path=path,
                    message=f"Condition name must be camelCase: '{name}'",
                ))
            names.add(name)
            if not isinstance(cond, dict):
                result.errors.append(SpecValidationMessage(
                    path=path,
                    message=f"Condition must be an object, got {type(cond).__name__}",
                ))
                continue
            for key in cond:
                if key not in ("meaning", "witness_true", "witness_false"):
                    result.errors.append(SpecValidationMessage(
                        path=f"{path}.{key}",
                        message=(
                            "Unknown condition key — allowed: 'meaning', "
                            "'witness_true', 'witness_false'"
                        ),
                    ))
            meaning = cond.get("meaning")
            if not isinstance(meaning, str) or not meaning:
                result.errors.append(SpecValidationMessage(
                    path=f"{path}.meaning",
                    message="Condition requires a non-empty 'meaning' string",
                ))
            for wkey in ("witness_true", "witness_false"):
                if wkey in cond:
                    self._validate_branch_witness(
                        cond[wkey], f"{path}.{wkey}", data_fields, result,
                        seedable,
                    )
            # Two witnesses that arrange the same state cannot separate the
            # branches they gate: the generated tests would set up identical
            # state and then assert opposite outcomes.
            true_w = cond.get("witness_true")
            false_w = cond.get("witness_false")
            if (
                isinstance(true_w, dict) and isinstance(false_w, dict)
                and true_w == false_w
            ):
                result.warnings.append(SpecValidationMessage(
                    path=path,
                    message=(
                        "witness_true and witness_false arrange the same "
                        "state, so they cannot tell the condition's two "
                        "sides apart"
                    ),
                    level="warning",
                ))
        return names

    def _validate_branch_arg_bindings(
        self, bc: dict, result: SpecValidationResult,
    ) -> None:
        """`arg.<name>` has to name a declared parameter of the method.

        The generated act call is built from
        `dataFlow.viewModel.methods[].params`; an argument matching nothing
        there is dropped, and the branch then runs with a different input
        than it declares — silently, unless the harness happens to reject
        the missing value. eventHandlers are not a second declaration site:
        they are View-layer handlers with no signature, so a contract that
        pins arguments needs the method on the ViewModel's public API.
        """
        methods = bc.get("methods")
        if not isinstance(methods, dict) or not isinstance(self._spec_data, dict):
            return
        view_model = (self._spec_data.get("dataFlow") or {}).get("viewModel") or {}
        declared: dict[str, set[str]] = {}
        for method in view_model.get("methods", []) or []:
            if isinstance(method, dict) and isinstance(method.get("name"), str):
                params = method.get("params")
                declared[method["name"]] = {
                    p["name"] for p in params
                    if isinstance(p, dict) and isinstance(p.get("name"), str)
                } if isinstance(params, list) else set()
            elif isinstance(method, str):
                declared[method.split("(")[0].strip()] = set()

        for method_name, contract in methods.items():
            if not isinstance(contract, dict):
                continue
            params = declared.get(method_name)
            for i, branch in enumerate(contract.get("branches") or []):
                if not isinstance(branch, dict) or "note" in branch:
                    continue
                when = branch.get("when")
                if not isinstance(when, dict):
                    continue
                for key in when:
                    if not key.startswith("arg."):
                        continue
                    name = key[len("arg."):]
                    if params is not None and name in params:
                        continue
                    path = (
                        f"branchContracts.methods.{method_name}."
                        f"branches[{i}].when.{key}"
                    )
                    if params is None:
                        message = (
                            f"'{method_name}' is not declared in "
                            "dataFlow.viewModel.methods, so it has no "
                            "parameter list to bind this argument to — "
                            "declare it there with `params` "
                            "(stateManagement.eventHandlers is View-layer "
                            "only and carries no signature)"
                        )
                    else:
                        message = (
                            f"'{method_name}' declares no parameter "
                            f"'{name}' — its params are "
                            f"{sorted(params) if params else '(none)'}"
                        )
                    result.errors.append(SpecValidationMessage(
                        path=path, message=message,
                    ))

    def _validate_branch_condition_usage(
        self, bc: dict, condition_names: set[str],
        result: SpecValidationResult,
    ) -> None:
        """Conditions against the branches that gate on them.

        Two directions the reference check does not cover: a condition
        nothing gates on is a declaration whose witnesses no generated test
        ever arranges, and a branch gating on a condition whose witness for
        that side is absent fails test generation outright — which validate
        can say first.
        """
        conditions = bc.get("conditions")
        if not isinstance(conditions, dict) or not conditions:
            return
        methods = bc.get("methods")
        if not isinstance(methods, dict):
            return

        needed: dict[str, set[str]] = {}
        for method_name, contract in methods.items():
            if not isinstance(contract, dict):
                continue
            for i, branch in enumerate(contract.get("branches", []) or []):
                if not isinstance(branch, dict) or "note" in branch:
                    continue
                when = branch.get("when")
                if not isinstance(when, dict):
                    continue
                ref = when.get("cond")
                if not isinstance(ref, str) or not ref:
                    continue
                negated = ref.startswith("!")
                name = ref[1:] if negated else ref
                wkey = "witness_false" if negated else "witness_true"
                needed.setdefault(name, set()).add(wkey)
                cond = conditions.get(name)
                if not isinstance(cond, dict) or name not in condition_names:
                    continue  # unknown cond — already an error elsewhere
                if not isinstance(cond.get(wkey), dict):
                    result.warnings.append(SpecValidationMessage(
                        path=(
                            f"branchContracts.methods.{method_name}."
                            f"branches[{i}].when.cond"
                        ),
                        message=(
                            f"Condition '{name}' has no {wkey}, so this "
                            "branch cannot be arranged — test generation "
                            "fails on it"
                        ),
                        level="warning",
                    ))

        for name in conditions:
            if isinstance(name, str) and name not in needed:
                result.warnings.append(SpecValidationMessage(
                    path=f"branchContracts.conditions.{name}",
                    message=(
                        "Condition is declared but no branch gates on it — "
                        "its witnesses are never exercised"
                    ),
                    level="warning",
                ))

    def _validate_seedable_state(
        self, seedable: Any, result: SpecValidationResult,
    ) -> set[str]:
        """`seedableState: {name: type}` — ViewModel-internal state a branch
        may arrange.

        The layer exists because a value that is neither bound to the UI nor
        a screen state does not belong on the data surface, yet branches
        still gate on it. Declaring the names (rather than letting `when` reach for
        any property path) keeps the contract off the implementation's
        private vocabulary: a rename breaks a declaration someone has to
        update, not an arrange step that silently stops arranging.

        The declaration is also what makes the write checkable at all. The
        harness applies data keys leniently on purpose — a data-only field
        assigned onto the ViewModel invents a property that then shadows the
        store — so the writer cannot tell "should exist on the VM" from
        "belongs to the store". These names carry exactly that bit.
        """
        names: set[str] = set()
        if seedable is None:
            return names
        if not isinstance(seedable, dict):
            result.errors.append(SpecValidationMessage(
                path="branchContracts.seedableState",
                message=(
                    "seedableState must be an object of {name: type}, got "
                    f"{type(seedable).__name__}"
                ),
            ))
            return names
        for name, type_name in seedable.items():
            path = f"branchContracts.seedableState.{name}"
            if not self._matches_variable_name(name):
                result.errors.append(SpecValidationMessage(
                    path=path,
                    message=f"Seedable state name must be camelCase: '{name}'",
                ))
                continue
            if not isinstance(type_name, str) or not type_name:
                result.errors.append(SpecValidationMessage(
                    path=path,
                    message=(
                        "Seedable state type must be a non-empty type string "
                        "using the same vocabulary as dataFlow.viewModel.vars "
                        f"(e.g. 'Int?', '[String]'), got {type_name!r}"
                    ),
                ))
                continue
            names.add(name)
        return names

    def _check_branch_seedable_ref(
        self, name: str, path: str, seedable: set[str],
        result: SpecValidationResult,
    ) -> None:
        """`state.<name>` resolves only against a declaration.

        An error, not a warning, and deliberately unlike the undeclared
        data-field case: a data field may exist on a platform this spec does
        not describe, but internal state is arranged by the generated test
        itself — an undeclared name means nothing will be seeded, and the
        branch would run against whatever state it happened to start in.
        """
        if not self._matches_variable_name(name):
            result.errors.append(SpecValidationMessage(
                path=path,
                message=f"Seedable state name must be camelCase: '{name}'",
            ))
            return
        if name not in seedable:
            result.errors.append(SpecValidationMessage(
                path=path,
                message=(
                    f"'state.{name}' is not declared in "
                    "branchContracts.seedableState — declare it (with its "
                    "type) or use 'data.<field>' if it belongs to the data "
                    "surface"
                ),
            ))

    def _validate_branch_witness(
        self, witness: Any, path: str, data_fields: set[str],
        result: SpecValidationResult, seedable: set[str] | None = None,
    ) -> None:
        """Witness / baseline object: {field: any JSON value}."""
        if not isinstance(witness, dict):
            result.errors.append(SpecValidationMessage(
                path=path,
                message=f"Witness must be an object, got {type(witness).__name__}",
            ))
            return
        for field_name in witness:
            if field_name.startswith("state."):
                self._check_branch_seedable_ref(
                    field_name[len("state."):], f"{path}.{field_name}",
                    seedable or set(), result,
                )
                continue
            if data_fields and field_name not in data_fields:
                result.warnings.append(SpecValidationMessage(
                    path=f"{path}.{field_name}",
                    message=(
                        f"Witness field '{field_name}' is not declared in "
                        "stateManagement.uiVariables / dataFlow.viewModel.vars "
                        "/ stateManagement.states"
                    ),
                    level="warning",
                ))

    def _validate_branch_method_contract(
        self, contract: Any, path: str, data_fields: set[str],
        condition_names: set[str], api_ops: set[str],
        transition_dests: set[str], result: SpecValidationResult,
        seedable: set[str] | None = None,
    ) -> None:
        if not isinstance(contract, dict):
            result.errors.append(SpecValidationMessage(
                path=path,
                message=f"Method contract must be an object, got {type(contract).__name__}",
            ))
            return
        for key in contract:
            if key not in ("baseline", "branches"):
                result.errors.append(SpecValidationMessage(
                    path=f"{path}.{key}",
                    message="Unknown contract key — allowed: 'baseline', 'branches'",
                ))
        if "baseline" in contract:
            self._validate_branch_witness(
                contract["baseline"], f"{path}.baseline", data_fields, result,
                seedable,
            )
        branches = contract.get("branches")
        if not isinstance(branches, list) or not branches:
            result.errors.append(SpecValidationMessage(
                path=f"{path}.branches",
                message="Contract requires a non-empty 'branches' array",
            ))
            return
        for i, branch in enumerate(branches):
            self._validate_branch_entry(
                branch, f"{path}.branches[{i}]", data_fields,
                condition_names, api_ops, transition_dests, result, seedable
            )

    def _validate_branch_entry(
        self, branch: Any, path: str, data_fields: set[str],
        condition_names: set[str], api_ops: set[str],
        transition_dests: set[str], result: SpecValidationResult,
        seedable: set[str] | None = None,
    ) -> None:
        if not isinstance(branch, dict):
            result.errors.append(SpecValidationMessage(
                path=path,
                message=f"Branch must be an object, got {type(branch).__name__}",
            ))
            return
        if "note" in branch:
            # Escape hatch: prose-only branch. Nothing else may ride along —
            # a note with when/then would silently drop the contract half.
            if not isinstance(branch["note"], str) or not branch["note"]:
                result.errors.append(SpecValidationMessage(
                    path=f"{path}.note",
                    message="note must be a non-empty string",
                ))
            extras = [k for k in branch if k != "note"]
            if extras:
                result.errors.append(SpecValidationMessage(
                    path=path,
                    message=(
                        f"A note branch must contain only 'note' (found "
                        f"{extras!r}). Declare the contract half as a "
                        "separate {when, then} branch."
                    ),
                ))
            return
        for key in branch:
            if key not in ("when", "then", "notes", "platforms", "baseline"):
                result.errors.append(SpecValidationMessage(
                    path=f"{path}.{key}",
                    message=(
                        "Unknown branch key — allowed: 'when', 'then', "
                        "'baseline', 'notes', 'platforms' (or a lone 'note')"
                    ),
                ))
        if "baseline" in branch:
            # A pre-state this branch alone starts from, overriding the
            # method's baseline KEY BY KEY.
            #
            # `when data.*` takes scalars only, and `baseline` takes any
            # JSON — so a list-valued pre-state was fixed per method while
            # the scalars agreeing with it moved per branch. That asymmetry
            # is a shape that builds incoherent states: a list with one row
            # beside an "empty" flag the branch flipped, arranged and
            # asserted against a state the implementation cannot reach. One
            # project arrived at it three times, twice in opposite authoring
            # orders and once by a writer who had considered the second
            # field and rejected it as a substitute for the first.
            #
            # So the fix is not "let `when` carry lists" — the composition
            # of partial overrides is the shape, and widening the types
            # that can be partially overridden keeps it. A branch states
            # the whole value of every key it touches instead.
            self._validate_branch_witness(
                branch["baseline"], f"{path}.baseline", data_fields, result,
                seedable,
            )
        if "platforms" in branch:
            # Platform-scoped branch (P3b: a data field may exist on one
            # platform only — e.g. an Android-only alert-message var while
            # iOS carries the same text in a shared data field). Renderers
            # skip branches whose platforms exclude their target.
            platforms = branch["platforms"]
            if (not isinstance(platforms, list) or not platforms
                    or any(p not in ("ios", "android", "web") for p in platforms)):
                result.errors.append(SpecValidationMessage(
                    path=f"{path}.platforms",
                    message=(
                        "platforms must be a non-empty array of "
                        "['ios', 'android', 'web']"
                    ),
                ))
        for req in ("when", "then"):
            part = branch.get(req)
            if not isinstance(part, dict) or not part:
                result.errors.append(SpecValidationMessage(
                    path=f"{path}.{req}",
                    message=f"Branch requires a non-empty '{req}' object",
                ))
        when = branch.get("when")
        if isinstance(when, dict):
            for key, value in when.items():
                self._validate_branch_when_entry(
                    key, value, f"{path}.when", data_fields,
                    condition_names, api_ops, result, seedable
                )
        then = branch.get("then")
        if isinstance(then, dict):
            for key, value in then.items():
                self._validate_branch_then_entry(
                    key, value, f"{path}.then", data_fields,
                    api_ops, transition_dests, result
                )
            self._check_response_ref_resolvable(when, then, path, result)

    def _check_response_ref_resolvable(
        self, when: Any, then: dict, path: str, result: SpecValidationResult,
    ) -> None:
        """`@response.<path>` reads the branch's own scenario, so the branch
        has to name exactly one. Test generation fails on this; validate can
        say it while the spec is being written."""
        uses_response = any(
            isinstance(v, str) and v.startswith("@response.")
            for v in then.values()
        )
        if not uses_response:
            return
        scenarios = [
            k for k, v in (when or {}).items()
            if isinstance(when, dict) and k.startswith("api.")
            and not k.endswith(".request") and isinstance(v, str)
        ]
        if len(scenarios) != 1:
            result.warnings.append(SpecValidationMessage(
                path=f"{path}.then",
                message=(
                    "'@response.<path>' reads the response of the branch's "
                    f"own scenario, but `when` names {len(scenarios)} "
                    "`api.<op>` scenario(s) — test generation needs exactly one"
                ),
                level="warning",
            ))

    @staticmethod
    def _is_scalar(value: Any) -> bool:
        return value is None or isinstance(value, (str, int, float, bool))

    def _check_branch_data_field(
        self, field_name: str, path: str, data_fields: set[str],
        result: SpecValidationResult,
    ) -> None:
        if not self._matches_variable_name(field_name):
            result.errors.append(SpecValidationMessage(
                path=path,
                message=f"Data field must be camelCase: '{field_name}'",
            ))
        elif data_fields and field_name not in data_fields:
            result.warnings.append(SpecValidationMessage(
                path=path,
                message=(
                    f"Data field '{field_name}' is not declared in "
                    "stateManagement.uiVariables / dataFlow.viewModel.vars "
                    "/ stateManagement.states"
                ),
                level="warning",
            ))

    def _check_branch_api_op(
        self, op: str, path: str, api_ops: set[str],
        result: SpecValidationResult,
    ) -> None:
        if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", op):
            result.errors.append(SpecValidationMessage(
                path=path,
                message=f"API operation name must be an identifier: '{op}'",
            ))
        elif api_ops and op not in api_ops:
            result.warnings.append(SpecValidationMessage(
                path=path,
                message=(
                    f"API operation '{op}' is not declared in "
                    "dataFlow.repositories[].methods or dataFlow.useCases[].methods"
                ),
                level="warning",
            ))

    def _validate_branch_when_entry(
        self, key: str, value: Any, path: str, data_fields: set[str],
        condition_names: set[str], api_ops: set[str],
        result: SpecValidationResult, seedable: set[str] | None = None,
    ) -> None:
        entry_path = f"{path}.{key}"
        if key == "cond":
            if not isinstance(value, str) or not value:
                result.errors.append(SpecValidationMessage(
                    path=entry_path,
                    message="cond must be a non-empty condition name string ('!' prefix allowed)",
                ))
                return
            ref = value[1:] if value.startswith("!") else value
            if ref not in condition_names:
                result.errors.append(SpecValidationMessage(
                    path=entry_path,
                    message=(
                        f"cond references undeclared condition '{ref}' — "
                        "declare it in branchContracts.conditions"
                    ),
                ))
            return
        if key.startswith("data."):
            self._check_branch_data_field(
                key[len("data."):], entry_path, data_fields, result
            )
            if not self._is_scalar(value):
                result.errors.append(SpecValidationMessage(
                    path=entry_path,
                    message=(
                        "when data.* value must be a scalar literal "
                        f"(string/number/bool/null), got {type(value).__name__}"
                    ),
                ))
            return
        if key.startswith("state."):
            self._check_branch_seedable_ref(
                key[len("state."):], entry_path, seedable or set(), result
            )
            return
        if key.startswith("arg."):
            arg = key[len("arg."):]
            if not self._matches_variable_name(arg):
                result.errors.append(SpecValidationMessage(
                    path=entry_path,
                    message=f"Argument name must be camelCase: '{arg}'",
                ))
            if not self._is_scalar(value):
                result.errors.append(SpecValidationMessage(
                    path=entry_path,
                    message=(
                        "when arg.* value must be a scalar literal "
                        f"(string/number/bool/null), got {type(value).__name__}"
                    ),
                ))
            return
        if key.startswith("api."):
            op = key[len("api."):]
            if "." in op:
                result.errors.append(SpecValidationMessage(
                    path=entry_path,
                    message=(
                        "when api key must be 'api.<op>' (the value is the "
                        "named mock scenario) — '.request' matching belongs in 'then'"
                    ),
                ))
                return
            self._check_branch_api_op(op, entry_path, api_ops, result)
            if not isinstance(value, str) or not value:
                result.errors.append(SpecValidationMessage(
                    path=entry_path,
                    message="when api.<op> value must be a named mock scenario string",
                ))
            return
        result.errors.append(SpecValidationMessage(
            path=entry_path,
            message=(
                f"Unknown when key '{key}' — allowed: 'data.<field>', "
                "'state.<name>', 'arg.<name>', 'api.<op>', 'cond'"
            ),
        ))

    def _validate_branch_then_entry(
        self, key: str, value: Any, path: str, data_fields: set[str],
        api_ops: set[str], transition_dests: set[str],
        result: SpecValidationResult,
    ) -> None:
        entry_path = f"{path}.{key}"
        if key == "transition":
            if not isinstance(value, str) or not value:
                result.errors.append(SpecValidationMessage(
                    path=entry_path,
                    message="transition must be a non-empty destination string",
                ))
                return
            if transition_dests and value not in transition_dests:
                result.warnings.append(SpecValidationMessage(
                    path=entry_path,
                    message=(
                        f"Transition destination '{value}' does not match any "
                        "transitions[].destination"
                    ),
                    level="warning",
                ))
            return
        if key == "api":
            if value != "none":
                result.errors.append(SpecValidationMessage(
                    path=entry_path,
                    message=(
                        "then 'api' accepts only 'none' (no API reached). For "
                        "per-operation verdicts use 'api.<op>': "
                        "'called'/'not-called'"
                    ),
                ))
            return
        if key.startswith("api."):
            rest = key[len("api."):]
            if rest.endswith(".request"):
                op = rest[: -len(".request")]
                self._check_branch_api_op(op, entry_path, api_ops, result)
                self._validate_branch_request_match(
                    value, entry_path, data_fields, result
                )
                return
            if "." in rest:
                result.errors.append(SpecValidationMessage(
                    path=entry_path,
                    message=(
                        "then api key must be 'api.<op>' or 'api.<op>.request', "
                        f"got '{key}'"
                    ),
                ))
                return
            self._check_branch_api_op(rest, entry_path, api_ops, result)
            if value not in self._BRANCH_THEN_API_VERDICTS:
                result.errors.append(SpecValidationMessage(
                    path=entry_path,
                    message=(
                        "then api.<op> value must be 'called' or 'not-called' "
                        f"(got {value!r})"
                    ),
                ))
            return
        if key.startswith("data."):
            self._check_branch_data_field(
                key[len("data."):], entry_path, data_fields, result
            )
            self._validate_branch_then_value(
                value, entry_path, data_fields, result, allow_empty_list=True,
            )
            return
        result.errors.append(SpecValidationMessage(
            path=entry_path,
            message=(
                f"Unknown then key '{key}' — allowed: 'data.<field>', "
                "'transition', 'api', 'api.<op>', 'api.<op>.request'"
            ),
        ))

    def _validate_branch_then_value(
        self, value: Any, path: str, data_fields: set[str],
        result: SpecValidationResult, *, allow_empty_list: bool = False,
    ) -> None:
        """then data.* / request-leaf value: scalar literal, '@strings_key',
        '@data.<field>' or '@response.<path>' reference.

        ``allow_empty_list`` opens exactly one exception, for
        ``then data.<field>``: ``[]``, meaning "this collection is empty
        afterwards". Contracts that clear a list on failure had no way to say
        so, and the scalar witness they fell back on — a visibility flag set
        in the same update — stays satisfied when only the clearing is
        removed, so the guarantee never reached the observable surface.

        Non-empty lists stay rejected: matching elements would bind the
        contract to the mock body. Request-match leaves never take the
        exception either — ``[]`` there would be a claim about a request,
        which is a different statement with no defined partial-match meaning.
        """
        if allow_empty_list and isinstance(value, list) and not value:
            return
        if not self._is_scalar(value):
            result.errors.append(SpecValidationMessage(
                path=path,
                message=self._branch_then_value_error(value, allow_empty_list),
            ))
            return
        if not isinstance(value, str) or not value.startswith("@"):
            return
        ref = value[1:]
        if ref.startswith("data."):
            self._check_branch_data_field(
                ref[len("data."):], path, data_fields, result
            )
        elif ref.startswith("response."):
            # A value the server chose (a passed-through API error message).
            # The text lives in the scenario, so only the shape is checkable
            # here; test generation reads the actual value out of the mock.
            # A numeric segment indexes a list: FastAPI's 422 puts the text
            # a screen shows inside `detail[]`, so without this the one
            # response class where "the screen shows what the server sent"
            # is most worth stating is the one class that cannot state it.
            #
            # THIS GATE RUNS FIRST. The reporting lane named the generator,
            # which is the second gate; a spec carrying `detail.0.msg` was
            # rejected here before generation ever read the body, with a
            # different message. Fixing one of the two would have moved the
            # refusal rather than removed it.
            if "[" in ref or "]" in ref:
                # One spelling, and the other is refused by name. The rest of
                # this vocabulary is dotted, and a second spelling is a second
                # thing every reader of a contract has to know.
                dotted = ref.replace("[", ".").replace("]", "")
                result.errors.append(SpecValidationMessage(
                    path=path,
                    message=(
                        f"'@response.' indexes a list with a dotted number, "
                        f"not brackets — write '@{dotted}' rather than "
                        f"'{value}'"
                    ),
                ))
            elif not re.match(r"^response\.[A-Za-z_][A-Za-z0-9_]*"
                              r"(\.([A-Za-z_][A-Za-z0-9_]*|[0-9]+))*$", ref):
                result.errors.append(SpecValidationMessage(
                    path=path,
                    message=(
                        "'@response.' must be followed by a dotted field path "
                        "into the response body, with a number for a list "
                        f"position (e.g. '@response.detail.0.msg'), got "
                        f"'{value}'"
                    ),
                ))
        elif not re.match(r"^[a-z][a-z0-9_]*$", ref):
            result.errors.append(SpecValidationMessage(
                path=path,
                message=(
                    f"'@' reference must be a snake_case strings key, "
                    f"'@data.<field>' or '@response.<path>', got '{value}'"
                ),
            ))

    @staticmethod
    def _branch_then_value_error(value: Any, allow_empty_list: bool) -> str:
        base = ("Value must be a scalar literal, '@strings_key', "
                "'@data.<field>' or '@response.<path>'")
        if allow_empty_list:
            # Say what IS accepted and what is deliberately not, so a
            # non-empty list reads as a scope decision rather than an
            # oversight the author should work around.
            base += (
                ", or '[]' to assert the collection is empty (only the empty "
                "list is accepted — element-by-element matching is out of "
                "scope, since it binds the contract to the mock body)"
            )
        return f"{base}, got {type(value).__name__}"

    def _validate_branch_request_match(
        self, value: Any, path: str, data_fields: set[str],
        result: SpecValidationResult,
    ) -> None:
        """api.<op>.request partial match: object whose leaves are scalars
        or '@data.<field>' references. Nested objects allowed."""
        if not isinstance(value, dict) or not value:
            result.errors.append(SpecValidationMessage(
                path=path,
                message=(
                    "api.<op>.request must be a non-empty partial request "
                    f"object, got {type(value).__name__}"
                ),
            ))
            return
        for k, v in value.items():
            leaf_path = f"{path}.{k}"
            if isinstance(v, dict):
                self._validate_branch_request_match(v, leaf_path, data_fields, result)
            else:
                self._validate_branch_then_value(v, leaf_path, data_fields, result)

    # ---- Cross-face correlation (weak phase — warnings only) ----
    #
    # Once a spec declares branchContracts, branch facts can also live as
    # prose in the legacy faces (validation.serverSide, userActions).
    # Census over the first adopted specs (docs/plans/2026-08-24-spec-face-
    # cross-consistency-design.md) showed drift concentrates in exactly two
    # seams, and that prose *presence* is a project culture (some projects
    # never write serverSide prose) — so the checks are strictly
    # "if the prose says it, the contract must know it": absence of prose
    # is always legal, and nothing pushes prose to be added. branchContracts
    # is treated as the canonical side; only prose-only facts warn.

    _SNAKE_TOKEN_RE = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)+")

    def _validate_branch_cross_faces(self, data: dict, result: SpecValidationResult):
        bc = data.get("branchContracts")
        if not isinstance(bc, dict):
            return
        methods = bc.get("methods") or {}
        if not isinstance(methods, dict) or not methods:
            return

        # A token counts as drift only when validation.serverSide is the
        # ONLY place in the whole spec that knows it: component ids, UI
        # element names, request fields, deliberately note-demoted codes
        # etc. all appear somewhere else in the spec, while a stale/new
        # prose-only error code by definition does not. Precision over
        # recall — this is a warning-class net.
        known: set[str] = set()

        def collect_tokens(node):
            if isinstance(node, dict):
                for k, v in node.items():
                    known.update(self._SNAKE_TOKEN_RE.findall(str(k)))
                    collect_tokens(v)
            elif isinstance(node, list):
                for v in node:
                    collect_tokens(v)
            elif isinstance(node, str):
                known.update(self._SNAKE_TOKEN_RE.findall(node))

        rest = dict(data)
        validation = dict(data.get("validation") or {})
        validation.pop("serverSide", None)
        rest["validation"] = validation
        collect_tokens(rest)
        transition_dests = self._collect_transition_destinations()

        # Seam 1: validation.serverSide prose mentions a branch-like token
        # (error code / outcome word) the contract does not know.
        for i, entry in enumerate((data.get("validation") or {}).get("serverSide", []) or []):
            if not isinstance(entry, dict):
                continue
            prose = f"{entry.get('condition', '')} {entry.get('handling', '')}"
            for token in sorted(set(self._SNAKE_TOKEN_RE.findall(prose))):
                if token not in known:
                    result.warnings.append(SpecValidationMessage(
                        path=f"validation.serverSide[{i}]",
                        message=(
                            f"Prose mentions branch-like token '{token}' that "
                            "branchContracts does not know — declare the "
                            "branch (or scenario) or update the stale prose"
                        ),
                        level="warning",
                    ))

        # Seam 2: a userActions entry that talks about a contracted method
        # routes to a declared transition destination no branch declares.
        declared_transitions: set[str] = set()
        for contract in methods.values():
            if not isinstance(contract, dict):
                continue
            for branch in contract.get("branches", []) or []:
                if not isinstance(branch, dict):
                    continue
                value = (branch.get("then") or {}).get("transition")
                if isinstance(value, str):
                    declared_transitions.add(value)
        method_names = [m for m in methods if isinstance(m, str)]
        for i, action in enumerate(data.get("userActions", []) or []):
            if not isinstance(action, dict):
                continue
            prose = f"{action.get('action', '')} {action.get('processing', '')}"
            if not any(name in prose for name in method_names):
                continue
            for dest in sorted(transition_dests):
                if dest in prose and dest not in declared_transitions:
                    result.warnings.append(SpecValidationMessage(
                        path=f"userActions[{i}]",
                        message=(
                            f"Prose routes to transition '{dest}' but no "
                            "branch of the contracted method(s) declares "
                            "`then.transition` to it — declare the branch or "
                            "update the stale prose"
                        ),
                        level="warning",
                    ))

    # --- spec endpoint <-> API canonical (OpenAPI) -----------------------
    #
    # A screen spec names the transport it talks to; the OpenAPI documents
    # under api_directory are the canonical spelling of those routes. Nothing
    # compared the two until now, so a path that drifted (renamed resource,
    # `{venueId}` where the API says `{venue_id}`) stayed invisible until
    # someone generated branch tests and the mock resolver refused to bind.
    #
    # Warnings only, and only in the direction spec -> canonical: a screen
    # spec is not expected to cover every route the API offers.

    _PATH_PARAM_RE = re.compile(r"\{[^}]*\}")
    _COLON_PARAM_RE = re.compile(r"(?<=/):[A-Za-z_][A-Za-z0-9_]*")
    _ENDPOINT_RE = re.compile(r"^([A-Za-z]+)\s+(\S+)$")

    @classmethod
    def _normalize_api_path(cls, path: str) -> str:
        """Path with every parameter segment collapsed, so `{venueId}`,
        `{venue_id}` and `:venueId` all compare equal."""
        return cls._COLON_PARAM_RE.sub("{}", cls._PATH_PARAM_RE.sub("{}", path))

    # `_candidate_api_directories` / `_load_api_canonical_index` /
    # `_index_api_directory` lived here until v1.7.8. They answered "where is
    # the canon" without following `extends`, so they gave a different answer
    # than the live path — and they had no callers left, which is the worst
    # combination: a helper that looks like the right one to reach for, and is
    # wrong. See `_canon_context`.




    def _collect_declared_endpoints(self, data_flow: dict) -> list[tuple[str, str]]:
        """(spec path, '<VERB> <path>') for everything dataFlow declares."""
        declared: list[tuple[str, str]] = []
        for section in ("repositories", "useCases"):
            for i, entry in enumerate(data_flow.get(section, []) or []):
                if not isinstance(entry, dict):
                    continue
                for j, method in enumerate(entry.get("methods", []) or []):
                    if not isinstance(method, dict):
                        continue
                    endpoint = method.get("endpoint")
                    if isinstance(endpoint, str) and endpoint.strip():
                        declared.append((
                            f"dataFlow.{section}[{i}].methods[{j}].endpoint",
                            endpoint.strip(),
                        ))
        for i, entry in enumerate(data_flow.get("apiEndpoints", []) or []):
            if not isinstance(entry, dict):
                continue
            path = entry.get("path")
            verb = entry.get("method")
            if isinstance(path, str) and isinstance(verb, str) and path and verb:
                declared.append((
                    f"dataFlow.apiEndpoints[{i}]", f"{verb.upper()} {path}"
                ))
        return declared

    def _validate_api_endpoint_canonical(
        self, data: dict, result: SpecValidationResult
    ):
        data_flow = data.get("dataFlow")
        if not isinstance(data_flow, dict):
            return
        declared = self._collect_declared_endpoints(data_flow)
        if not declared:
            return
        canon = shared_core.openapi_canonical()
        if canon is None:
            return
        context = self._canon_context()
        if context is None:
            return
        self._report_yaml_shortfall(context, result)
        for message in getattr(context, "unknown_config_keys", ()):
            # A warning, not an error: an unrecognised key may be a setting a
            # future version reads, or a project's own note without the
            # underscore. A broken `extends` value is an error because it
            # changes what is generated; a key nothing reads changes nothing
            # by itself — the harm is that the author thinks it does.
            result.warnings.append(SpecValidationMessage(
                path="jui.config.json", message=message, level="warning"))
        for message in getattr(context, "unresolved_extends", ()):
            # An error, not a warning: a pointer that names nothing produced
            # byte-identical output to no pointer at all, so a typo was
            # invisible except by A/B. Writing `extends` is a statement of
            # intent; not writing it is not.
            result.errors.append(SpecValidationMessage(
                path="jui.config.json", message=message))
        for message in getattr(context, "invalid_config_values", ()):
            # Same ruling as `extends`: a declared value nothing accepts is a
            # broken declaration, and this one silently changed how every
            # generated parameter is spelled.
            result.errors.append(SpecValidationMessage(
                path="jui.config.json", message=message))
        index = context.index
        if not index:
            # Silence here compared nothing and looked exactly like a project
            # whose routes all match: the warning count simply drops to zero.
            # Measured — deleting the OpenAPI documents took a spec from one
            # endpoint warning to none, with nothing said about why.
            #
            # This is the oldest check in the file and the only one with the
            # hole; the marks added later already fail loudly when the canon
            # cannot be found. The lesson reached the new checks and was never
            # applied back to this one — the same shape a consumer lane found
            # in its own three gates on the same day, the guard present in the
            # two it built after learning it and absent from the one it
            # already had.
            # Per file, not once per run. The first version deduplicated per
            # validator while counting per file, and the two units disagreed:
            # a batch whose unchecked declarations totalled four reported
            # whichever count the first-reached file happened to hold — "1
            # endpoint declaration(s) were not checked" over a shortfall of
            # four (found by a consumer lane, which held the total at four
            # and watched the reported number track the file order). Every
            # other message in this validator is a per-file fact attributed to
            # its file; this one now is too, and the run total is the sum of
            # what the batch prints. Loudness is proportionate: a project
            # with fifty canonless spec files has fifty files' worth of
            # unchecked contracts.
            # Still absent when the YAML shortfall already said why the index
            # is empty — two sentences for one cause reads as two problems.
            if not getattr(context, "missing_yaml", 0):
                # Name the directory and the config: without the where, a
                # consumer lane that provoked this on purpose was left with
                # three hypotheses it could not tell apart from the outside.
                api_dir = getattr(context, "api_dir", None)
                cfg = getattr(context, "config_path", None)
                where = f" ('{api_dir}', from '{cfg}')" if api_dir else ""
                # Both units, labelled. A spec that lists its routes in
                # `apiEndpoints` as well as on its methods declares each of
                # them twice, and a count that does not say which unit it
                # counts gets read as the other one: a lane summed these
                # against its route count and reported the checker counting
                # something else (134 routes, 263 sites — both numbers were
                # right, in different units).
                routes = {
                    (canon.normalize_path(e.split(" ", 1)[-1]),
                     e.split(" ", 1)[0].upper())
                    for _, e in declared
                }
                result.warnings.append(SpecValidationMessage(
                    path="dataFlow",
                    message=(
                        f"{len(routes)} endpoint(s), declared in "
                        f"{len(declared)} place(s), were not checked: no "
                        f"OpenAPI document was found under "
                        f"api_directory{where}. This is not 'every route "
                        "matches' — nothing was compared."
                    ),
                    level="warning",
                ))
            return

        for spec_path, endpoint in declared:
            operation, reason = canon.lookup(index, endpoint)
            if operation is not None:
                verb, _, path = endpoint.strip().partition(" ")
                path = path.split("?")[0]
                if operation.path != path:
                    result.warnings.append(SpecValidationMessage(
                        path=spec_path,
                        message=(
                            f"Endpoint path parameters differ from the API "
                            f"document: spec '{path}' vs canonical "
                            f"'{operation.path}'"
                        ),
                        level="warning",
                    ))
                continue

            # Non-HTTP transports (WebSocket, RTDB, GraphQL ...) are declared
            # the same way and are legal — the canonical documents simply do
            # not describe them.
            if reason in ("non_http", "malformed"):
                continue
            verb, _, path = endpoint.strip().partition(" ")
            path = path.split("?")[0]
            if reason == "method_missing":
                verbs = sorted({m for (p, m) in index
                                if p == canon.normalize_path(path)})
                result.warnings.append(SpecValidationMessage(
                    path=spec_path,
                    message=(
                        f"Endpoint path '{path}' is declared in the API "
                        f"document but not for {verb.upper()} (declared: "
                        f"{', '.join(verbs)})"
                    ),
                    level="warning",
                ))
            else:
                result.warnings.append(SpecValidationMessage(
                    path=spec_path,
                    message=(
                        f"Endpoint '{verb.upper()} {path}' is not declared in "
                        "any OpenAPI document under api_directory — update the "
                        "spec to the canonical route, or document the route"
                    ),
                    level="warning",
                ))

    # --- @canonical marks -------------------------------------------------

    def _reject_parent_declarations(self, data: dict, result):
        """A screen_parent_spec may not declare what its sub-specs provide.

        Measured on a real parent: nine repository-method declarations that
        changed nothing when edited, with `jui build`, `jui verify`, this
        validator and `generate project --dry-run` all green in both
        directions, and zero merge conflicts — the parent was never a
        participant to conflict with. `branchContracts` and `error_handling`
        were vanishing the same way and nobody had noticed those at all.
        """
        rules = shared_core.load("parent_spec_rules")
        if rules is None:
            return
        for path, message in rules.dropped_parent_declarations(data):
            result.errors.append(SpecValidationMessage(path=path, message=message))

    def _resolve_canonical_marks(
        self, data: dict, result: SpecValidationResult
    ):
        """Expand `params: "@canonical"` / `returnType: "@canonical.wire"`.

        A thin adapter: the walk, the lookup and the expansion all live in
        `shared/core/openapi_canonical.py`, because `jui build` resolves the
        same marks when it generates repository stubs and two answers to one
        question would drift. Everything this file adds is where the canon is
        found and how a failure is reported.

        A mark that cannot resolve is an ERROR. Falling back to an empty
        parameter list would generate a stub with no arguments and say nothing.
        """
        canon = shared_core.openapi_canonical()
        if canon is None:
            return
        # Both kinds, or a spec whose only mark is a misplaced one returns
        # here and is never told about it — which is the exact silence this
        # release removes. Caught by the test, because the first probe for it
        # happened to carry a repository mark as well.
        if not (list(canon.iter_marked_methods(data))
                or list(canon.iter_misplaced_marks(data))
                or list(canon.iter_divergence_declarations(data))):
            return
        context = self._canon_context()
        index, convention = context.index, context.convention
        # Before resolution, not after: `resolve_spec_marks` rewrites `params`
        # in place, so a method that carried a mark stops looking like one and
        # the "a mark has no divergence to declare" check silently never fires.
        # Caught by the test for exactly that case.
        errors = canon.check_divergences(data, index, convention)
        mark_errors, warnings = canon.resolve_spec_marks(data, index, convention)
        errors.extend(mark_errors)
        for path, message in errors:
            result.errors.append(SpecValidationMessage(path=path, message=message))
        for path, message in warnings:
            result.warnings.append(SpecValidationMessage(
                path=path, message=message, level="warning"))

    def _report_yaml_shortfall(self, context, result):
        """Say once that the check was skipped, rather than degrade quietly.

        Half an index would report every route living in the YAML documents as
        missing — a wrong answer that looks like a finding.
        """
        if not getattr(context, "missing_yaml", 0):
            return
        if self._api_yaml_skip_reported:
            return
        self._api_yaml_skip_reported = True
        result.warnings.append(SpecValidationMessage(
            path="dataFlow",
            message=(
                f"Endpoint check skipped: {context.missing_yaml} YAML "
                "OpenAPI document(s) under api_directory cannot be "
                "read without PyYAML installed"
            ),
            level="warning",
        ))

    def _canon_context(self):
        """The API canon and the naming convention, from ONE config.

        Resolved together. They used to be separate calls and a split tree
        pulled them apart — the documents came from the repository-root config
        while the convention was searched for by walking up from the spec,
        which in that layout never reaches the app config. The run then
        expanded marks in `camelCase` and compared divergences against the
        document's raw spelling, in the same run.
        """
        canon = shared_core.openapi_canonical()
        if canon is None:
            return None
        try:
            cwd = Path.cwd().resolve()
        except OSError:
            cwd = None
        spec_dir = (self._spec_file_path.parent.resolve()
                    if self._spec_file_path else None)
        key = (spec_dir, cwd)
        if key in self._api_index_cache:
            return self._api_index_cache[key]
        # Cached per validator: a batch run validates every spec in a
        # directory and would otherwise re-read and re-index the whole canon
        # once per file.
        context = canon.build_spec_canon_context(self._spec_file_path,
                                                 extra_roots=(cwd,))
        self._api_index_cache[key] = context
        return context

    def _declared_directory(self, key: str, default: str):
        """A directory the project declares, from the config that owns the spec.

        The nearest `jui.config.json` above the spec, not the one nearest
        the working directory — a run started from anywhere else would
        otherwise resolve a different project's layouts.
        """
        if not self._spec_file_path:
            return None
        for parent in self._spec_file_path.parents:
            config = parent / "jui.config.json"
            if not config.is_file():
                continue
            try:
                declared = json.loads(config.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return None
            if not isinstance(declared, dict):
                return None
            return parent / declared.get(key, default)
        return None

    def _declared_path_roots(self, kind: str | None = None):
        """The bases a declaration that names a file may be written from.

        Three, in order, and a path only counts as missing when it is under
        none of them:

        1. **the declared directory for its KIND**, when the declaration has
           one — `layoutFile` and `cellClasses` name layouts, so
           `layouts_directory`. `relatedFiles[].path` has no kind (a layout,
           a view model and a model all share the key), so it skips this
           one and starts at 2.
        2. **the directory the declaration is written in.**
        3. **every declared boundary above it, up to the project.**

        One rule with a kind-dependent first step, rather than two rules —
        the same question was asked twice within a week and the answers had
        drifted apart by a candidate.
        """
        if not self._spec_file_path:
            return []
        roots = []
        if kind == "layout":
            declared = self._declared_directory(
                "layouts_directory", "docs/screens/layouts")
            if declared is not None:
                roots.append(declared)
        roots.append(self._spec_file_path.parent)
        roots.extend(self._boundary_roots())
        return roots

    def _boundary_roots(self):
        """Step 3: declared boundaries above the spec, up to the project.

        EVERY declared boundary above the spec, not the nearest one. The
        first version stopped at the first ancestor holding a
        `jui.config.json`, which in a multi-app repository is the APP's
        config — and reported 35 warnings on a project whose 26 unique paths
        all resolve, because the repository root above it was never tried.

        The reporter's own evidence for the shape of the bug: one warning
        named a class under an application tree that is a SIBLING of the
        docs tree at the repository root — a path that cannot exist under
        either candidate the message listed. **The check was searching only
        places the file could not be and concluding it was nowhere.**

        Their layout is why the repository root cannot be derived from the
        app: the docs tree lives in the parent repository while the
        application trees are submodules beside it, so a spec has to name
        files in both — and the only base that spells both without `../`
        chains is the repository root. Collecting every marker
        (`jui.config.json` or `.git`, file or directory, so a submodule
        boundary counts) reaches it without this code knowing the topology.

        Generous by design. A finding needs the path to be under NONE of
        these, because one visibly wrong finding is what stops people acting
        on the rest — and this one shipped as 35 of them.
        """
        roots = []
        # Bounded, and the bound is the project. Collecting every marker
        # above the spec had no ceiling, so on a machine where this
        # repository sits inside another checkout, the OUTER checkout's
        # `.git` became a candidate — and a path that exists only outside
        # this project resolved. A consumer produced 43 such paths on one
        # machine without contriving anything: green at their desk, warning
        # in CI, on a check scheduled to become an error. "Cannot reproduce
        # locally" is the worst shape for that to take.
        #
        # The ceiling is the nearest enclosing `.git` — the same place
        # `jsonui-test` resolves its project root from. A split tree still
        # reaches its parent repository (the specs live in the parent, so
        # the parent is the nearest `.git`); a submodule stops at its own.
        # Ascending further is guessing about the machine, and breadth
        # beyond the project belongs in config, where the answer does not
        # depend on what happens to sit above the checkout.
        for parent in self._spec_file_path.parents:
            if ((parent / "jui.config.json").is_file()
                    or (parent / ".git").exists()):
                roots.append(parent)
            if (parent / ".git").exists():
                break
        return roots

    def _check_layout_ref(self, value, path: str, result, *, what: str):
        """Report a layout name that resolves under none of its bases.

        `layoutFile` and `cellClasses[]` name a layout WITHOUT the `.json`
        suffix, so the suffix is added here rather than expected from the
        author — every one of the 30 references a consumer counted is
        written that way, and demanding the other spelling would report
        them all.
        """
        if not isinstance(value, str) or not value.strip():
            return                      # a shape problem, checked elsewhere
        name = value.strip()
        if not name.endswith(".json"):
            name += ".json"
        roots = self._declared_path_roots("layout")
        if not roots or any((root / name).exists() for root in roots):
            return
        result.warnings.append(SpecValidationMessage(
            path=path,
            message=(
                f"{what} names a layout that does not exist: {value} "
                f"(looked for {name} under "
                f"{', '.join(str(r) for r in roots)}). A warning for now — "
                "this becomes an error once projects have cleared their "
                "existing counts, so it is worth fixing rather than living "
                "with."
            ),
            level="warning",
        ))

    def _validate_related_files(self, files: list, result: SpecValidationResult):
        """Validate relatedFiles section."""
        roots = self._declared_path_roots()
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

            # `type` is checked against an allow-list and errors on a bad
            # value, so `relatedFiles` reads as a validated declaration —
            # and `path`, sitting beside something guarded, was never
            # suspected. Measured on one repository: 353 paths across 103
            # specs, 11 of them naming files that do not exist, and the run
            # reported PASSED / 0 errors / 0 warnings. The other 342 resolve,
            # so the convention is alive; only the check was missing.
            #
            # A warning, and deliberately not permanently one: projects
            # measure their own counts first, and the weight moves to error
            # when they reach zero. Saying so in the message is the
            # difference between a warning people clear and one they learn
            # to scroll past.
            declared = file_info.get("path")
            if roots and isinstance(declared, str) and declared.strip():
                candidate = Path(declared.strip())
                if not (candidate.is_absolute() and candidate.exists()) and \
                        not any((root / declared.strip()).exists()
                                for root in roots):
                    result.warnings.append(SpecValidationMessage(
                        path=f"relatedFiles[{i}].path",
                        message=(
                            f"names a file that does not exist: {declared} "
                            f"(looked under {', '.join(str(r) for r in roots)})"
                            ". A warning for now — this becomes an error once "
                            "projects have cleared their existing counts, so "
                            "it is worth fixing rather than living with."
                        ),
                        level="warning"
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
