"""Screen test validation."""

from __future__ import annotations

import re
from pathlib import Path

from .models import ValidationMessage, ValidationResult
from .step import StepValidator
from .launch import validate_launch
from .mock import find_mock_index, validate_mock_reference
from .platform import validate_platform_field
from . import declared_paths
from .required import check_required_top_level
from .responsive import validate_responsive_field
from ..schema import (
    VALID_SCREEN_READY_VALUES,
    VALID_SCREEN_TOP_LEVEL_KEYS,
    VALID_FLOW_TOP_LEVEL_KEYS,
    VALID_CASE_KEYS,
    VALID_SOURCE_KEYS,
)

# Pattern to match @{varName} placeholders
ARG_PLACEHOLDER_PATTERN = re.compile(r'@\{([^}]+)\}')


class ScreenTestValidator:
    """Validates screen test structure."""

    def __init__(self, step_validator: StepValidator):
        self._step_validator = step_validator
        self._test_file_path: Path | None = None

    def set_test_file_path(self, path: Path | None):
        """Set the test file path for resolving relative paths."""
        self._test_file_path = path
        self._step_validator.set_test_file_path(path)

    def validate(self, data: dict, path: str, result: ValidationResult):
        """Validate screen test structure."""
        # Unknown top-level keys are errors — the schema says
        # additionalProperties: false, and the old shared screen∪flow key set
        # let the wrong-type mistake (flow keys in a screen test) through
        # without even a warning. A key from the flow list gets a pointed
        # message instead of "unknown".
        for key in data.keys():
            if key in VALID_SCREEN_TOP_LEVEL_KEYS:
                continue
            if key in VALID_FLOW_TOP_LEVEL_KEYS:
                message = (
                    f"'{key}' is a flow-test key, not valid in a screen test"
                    " — should this file be type: flow?"
                )
            else:
                message = f"Unknown top-level key: {key}"
            result.errors.append(ValidationMessage(
                path=path,
                message=message
            ))

        # Validate source object keys. 'spec' is the pre-2026-08-01 spelling of
        # 'document' (flow-test used it as its canonical key until then):
        # deprecated alias with a warning, error when both are present. Any
        # other unknown key is an error — the schema says
        # additionalProperties: false, and the old warning-only handling let
        # 3 of the 4 shipped examples violate the repo's own schema unnoticed.
        source = data.get("source")
        if source and isinstance(source, dict):
            if "spec" in source:
                if "document" in source:
                    result.errors.append(ValidationMessage(
                        path=f"{path}.source",
                        message="'spec' and 'document' are both present — 'spec' is the deprecated alias of 'document', drop it"
                    ))
                else:
                    result.warnings.append(ValidationMessage(
                        path=f"{path}.source",
                        message="'spec' is deprecated — rename to 'document' (canonical key)",
                        level="warning"
                    ))
            for key in source.keys():
                if key not in VALID_SOURCE_KEYS and key != "spec":
                    result.errors.append(ValidationMessage(
                        path=f"{path}.source",
                        message=f"Unknown source key: {key} (allowed: {', '.join(VALID_SOURCE_KEYS)})"
                    ))

            # The path is resolved, not merely typed. A `source.layout`
            # pointing at a file that does not exist validated clean, so a
            # green run said the same thing whether the paths were right or
            # whether nothing had looked at them.
            for key, kind in (("layout", "layout"), ("document", "document"),
                              ("spec", "document")):
                value = source.get(key)
                if key in source and not declared_paths.resolves(
                        value, kind):
                    result.warnings.append(ValidationMessage(
                        path=f"{path}.source",
                        message=declared_paths.unresolved_message(
                            key, value, kind),
                        level="warning"
                    ))

        # `screenReady` overrides the runner's readiness gate for this file.
        # Its values are checked here because a misspelling is otherwise
        # invisible until the run: an unrecognised string falls through to the
        # default gate, so the file waits for the very marker it declared it
        # would not wait for, and fails as a timeout that names the screen
        # rather than the typo.
        if "screenReady" in data:
            ready = data["screenReady"]
            if isinstance(ready, str):
                if ready not in VALID_SCREEN_READY_VALUES:
                    result.errors.append(ValidationMessage(
                        path=f"{path}.screenReady",
                        message=(
                            f"Unknown screenReady value: {ready!r} (allowed: "
                            f"{', '.join(VALID_SCREEN_READY_VALUES)}, or "
                            "{\"marker\": \"<screen id>\"})"
                        )
                    ))
            elif isinstance(ready, dict):
                unknown = [k for k in ready if k != "marker"]
                if unknown:
                    result.errors.append(ValidationMessage(
                        path=f"{path}.screenReady",
                        message=f"Unknown screenReady key(s): {', '.join(sorted(unknown))} (only 'marker')"
                    ))
                if not isinstance(ready.get("marker"), str) or not ready.get("marker"):
                    result.errors.append(ValidationMessage(
                        path=f"{path}.screenReady",
                        message="screenReady object form requires a non-empty 'marker' (the screen id to wait for instead)"
                    ))
            else:
                result.errors.append(ValidationMessage(
                    path=f"{path}.screenReady",
                    message=(
                        "screenReady must be a string ("
                        f"{', '.join(VALID_SCREEN_READY_VALUES)}) or "
                        "{\"marker\": \"<screen id>\"}"
                    )
                ))

        # Required top-level keys. Errors, not warnings: the same schema's
        # `additionalProperties: false` is enforced as an error, and there is
        # no reading of one declaration that makes it weaker than the other.
        check_required_top_level(data, "screen", path, result)

        # Validate test-level platform if present
        if "platform" in data:
            validate_platform_field(data["platform"], f"{path}.platform", result)

        # Validate launch configuration if present
        if "launch" in data:
            validate_launch(data["launch"], f"{path}.launch", result)

        # Validate root-level mock scenario set (screen tests select scenarios per file)
        if "mocks" in data:
            index = find_mock_index(self._test_file_path)
            validate_mock_reference(data["mocks"], f"{path}.mocks", result, index)

        # Validate cases
        cases = data.get("cases", [])
        if "cases" in data and not cases:
            # Present but empty is not a schema violation — `required` asks
            # for the key — so it stays a warning. A file that declares an
            # empty list has said something, even if it asserts nothing.
            result.warnings.append(ValidationMessage(
                path=path,
                message="No test cases defined",
                level="warning"
            ))

        for i, case in enumerate(cases):
            case_path = f"{path}.cases[{i}]"
            self._validate_case(case, case_path, result)

        # Validate setup/teardown if present
        for section in ["setup", "teardown"]:
            if section in data:
                for i, step in enumerate(data[section]):
                    step_path = f"{path}.{section}[{i}]"
                    self._step_validator.validate_step(step, step_path, result)

    def _validate_case(self, case: dict, path: str, result: ValidationResult):
        """Validate a test case."""
        # Check required fields
        if "name" not in case:
            result.errors.append(ValidationMessage(
                path=path,
                message="Test case missing 'name' field"
            ))

        # Warn if description is missing (recommended for HTML sidebar display)
        if "description" not in case:
            case_name = case.get("name", "unknown")
            result.warnings.append(ValidationMessage(
                path=path,
                message=f"Test case '{case_name}' missing 'description' field (recommended for HTML documentation)",
                level="warning"
            ))

        # Check for unknown keys
        for key in case.keys():
            if key not in VALID_CASE_KEYS:
                result.warnings.append(ValidationMessage(
                    path=path,
                    message=f"Unknown case key: {key}",
                    level="warning"
                ))

        # Validate case-level platform override if present
        if "platform" in case:
            validate_platform_field(case["platform"], f"{path}.platform", result)

        # Validate case-level responsive gate if present (screen tests only;
        # resolved at runtime — unmet gates skip the case, ANDs with platform)
        if "responsive" in case:
            validate_responsive_field(case["responsive"], f"{path}.responsive", result)

        # Validate descriptionFile if present
        if "descriptionFile" in case and self._test_file_path:
            desc_file_path = case["descriptionFile"]
            # Resolve relative to test file location
            if not Path(desc_file_path).is_absolute():
                desc_file_path = self._test_file_path.parent / desc_file_path

            desc_path = Path(desc_file_path)
            if not desc_path.exists():
                result.warnings.append(ValidationMessage(
                    path=path,
                    message=f"Description file not found: {case['descriptionFile']}",
                    level="warning"
                ))

        # Validate args if present
        if "args" in case:
            args = case["args"]
            if not isinstance(args, dict):
                result.errors.append(ValidationMessage(
                    path=f"{path}.args",
                    message="'args' must be an object/dictionary"
                ))
            else:
                for key, value in args.items():
                    if not isinstance(key, str):
                        result.errors.append(ValidationMessage(
                            path=f"{path}.args",
                            message=f"Argument key must be a string, got: {type(key).__name__}"
                        ))
                    if not isinstance(value, (str, int, float, bool)):
                        result.errors.append(ValidationMessage(
                            path=f"{path}.args.{key}",
                            message=f"Argument value must be a primitive type (string, number, boolean), got: {type(value).__name__}"
                        ))

        # Validate steps
        steps = case.get("steps", [])
        if not steps:
            result.warnings.append(ValidationMessage(
                path=path,
                message="Test case has no steps",
                level="warning"
            ))

        for i, step in enumerate(steps):
            step_path = f"{path}.steps[{i}]"
            self._step_validator.validate_step(step, step_path, result)

        # Validate that all @{varName} placeholders have corresponding args defined.
        # Runtime variables created by readText steps resolve at execution time,
        # so they count as defined too.
        defined_args = set(case.get("args", {}).keys()) if isinstance(case.get("args"), dict) else set()
        defined_args |= self._extract_runtime_variables(steps)
        used_args = self._extract_used_args(steps)
        undefined_args = used_args - defined_args
        if undefined_args:
            for arg_name in sorted(undefined_args):
                result.errors.append(ValidationMessage(
                    path=path,
                    message=f"Undefined argument '@{{{arg_name}}}' used in steps but not defined in 'args'"
                ))

    def _extract_used_args(self, steps: list) -> set[str]:
        """Extract all @{varName} placeholders used in steps."""
        used_args: set[str] = set()
        for step in steps:
            self._extract_args_from_value(step, used_args)
        return used_args

    def _extract_runtime_variables(self, steps: list) -> set[str]:
        """Extract variable names defined by readText steps (including nested repeat/retry)."""
        variables: set[str] = set()
        for step in steps:
            if not isinstance(step, dict):
                continue
            if step.get("action") == "readText" and isinstance(step.get("variable"), str):
                variables.add(step["variable"])
            nested = step.get("steps")
            if isinstance(nested, list):
                variables |= self._extract_runtime_variables(nested)
        return variables

    def _extract_args_from_value(self, obj, used_args: set[str]):
        """Recursively extract @{varName} from any string value in the object."""
        if isinstance(obj, str):
            matches = ARG_PLACEHOLDER_PATTERN.findall(obj)
            used_args.update(matches)
        elif isinstance(obj, dict):
            for value in obj.values():
                self._extract_args_from_value(value, used_args)
        elif isinstance(obj, list):
            for item in obj:
                self._extract_args_from_value(item, used_args)
