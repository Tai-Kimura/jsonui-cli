"""Screen test validation."""

from __future__ import annotations

import re
from pathlib import Path

from .models import ValidationMessage, ValidationResult
from .step import StepValidator
from ..schema import VALID_TOP_LEVEL_KEYS, VALID_CASE_KEYS, VALID_SOURCE_KEYS

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
        # Check for unknown top-level keys
        for key in data.keys():
            if key not in VALID_TOP_LEVEL_KEYS:
                result.warnings.append(ValidationMessage(
                    path=path,
                    message=f"Unknown top-level key: {key}",
                    level="warning"
                ))

        # Validate source object keys
        source = data.get("source")
        if source and isinstance(source, dict):
            for key in source.keys():
                if key not in VALID_SOURCE_KEYS:
                    result.warnings.append(ValidationMessage(
                        path=f"{path}.source",
                        message=f"Unknown source key: {key}",
                        level="warning"
                    ))

        # Check required fields
        if "metadata" not in data:
            result.warnings.append(ValidationMessage(
                path=path,
                message="Missing 'metadata' field",
                level="warning"
            ))

        # Validate cases
        cases = data.get("cases", [])
        if not cases:
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

        # Validate that all @{varName} placeholders have corresponding args defined
        defined_args = set(case.get("args", {}).keys()) if isinstance(case.get("args"), dict) else set()
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
