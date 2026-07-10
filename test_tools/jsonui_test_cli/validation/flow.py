"""Flow test validation."""

from __future__ import annotations

from pathlib import Path

from .models import ValidationMessage, ValidationResult
from .step import StepValidator
from .launch import validate_launch
from .platform import validate_platform_field


class FlowTestValidator:
    """Validates flow test structure."""

    def __init__(self, step_validator: StepValidator):
        self._step_validator = step_validator
        self._test_file_path: Path | None = None

    def set_test_file_path(self, path: Path | None):
        """Set the test file path for resolving relative paths."""
        self._test_file_path = path
        self._step_validator.set_test_file_path(path)

    def validate(self, data: dict, path: str, result: ValidationResult):
        """Validate flow test structure."""
        # Warn if file references use subdirectories
        self._check_subdirectory_references(data, path, result)

        # Validate sources if present (drivers require an array of {layout, alias?, spec?})
        if "sources" in data:
            self._validate_sources(data["sources"], f"{path}.sources", result)

        # Validate test-level platform if present (flow tests have no case objects)
        if "platform" in data:
            validate_platform_field(data["platform"], f"{path}.platform", result)

        # Validate launch configuration if present
        if "launch" in data:
            validate_launch(data["launch"], f"{path}.launch", result)

        # Validate steps
        steps = data.get("steps", [])
        if not steps:
            result.warnings.append(ValidationMessage(
                path=path,
                message="No steps defined in flow test",
                level="warning"
            ))

        for i, step in enumerate(steps):
            step_path = f"{path}.steps[{i}]"
            self._step_validator.validate_step(step, step_path, result, is_flow=True)

        # Validate setup/teardown if present
        for section in ["setup", "teardown"]:
            if section in data:
                for i, step in enumerate(data[section]):
                    step_path = f"{path}.{section}[{i}]"
                    self._step_validator.validate_step(step, step_path, result, is_flow=True)

    def _validate_sources(self, sources, path: str, result: ValidationResult):
        """Validate the sources array.

        Mirrors the driver models (FlowTestSource): sources must be an array of
        objects with a required 'layout' string and optional 'alias'/'spec'
        strings. An object map ({"alias": "path"}) passes JSON but crashes the
        iOS/Android drivers at deserialization.
        """
        if not isinstance(sources, list):
            result.errors.append(ValidationMessage(
                path=path,
                message=f"'sources' must be an array of {{layout, alias?, spec?}} objects, got: {type(sources).__name__}. The drivers reject non-array sources at parse time."
            ))
            return

        if len(sources) == 0:
            result.errors.append(ValidationMessage(
                path=path,
                message="'sources' must not be empty (omit it entirely when using file references)"
            ))
            return

        valid_source_keys = {"layout", "alias", "spec"}
        for i, source in enumerate(sources):
            source_path = f"{path}[{i}]"
            if not isinstance(source, dict):
                result.errors.append(ValidationMessage(
                    path=source_path,
                    message=f"Source must be an object with a 'layout' string, got: {type(source).__name__}"
                ))
                continue

            layout = source.get("layout")
            if not isinstance(layout, str) or not layout.strip():
                result.errors.append(ValidationMessage(
                    path=source_path,
                    message="Source must have a non-empty string 'layout'"
                ))

            for key in ("alias", "spec"):
                if key in source and (not isinstance(source[key], str) or not source[key].strip()):
                    result.errors.append(ValidationMessage(
                        path=source_path,
                        message=f"Source '{key}' must be a non-empty string"
                    ))

            for key in source.keys():
                if key not in valid_source_keys:
                    result.warnings.append(ValidationMessage(
                        path=source_path,
                        message=f"Unknown key in source: {key}",
                        level="warning"
                    ))

    def _check_subdirectory_references(self, data: dict, path: str, result: ValidationResult):
        """Check for file references that use unsupported subdirectory paths."""
        all_steps = []
        # Collect steps from setup, teardown, and main steps
        all_steps.extend(data.get("setup", []))
        all_steps.extend(data.get("steps", []))
        all_steps.extend(data.get("teardown", []))

        for i, step in enumerate(all_steps):
            if "file" in step:
                file_ref = step["file"]
                # Only warn if path contains directory separator but is NOT just a simple name
                # The loader automatically looks in screens/ subdirectory, so no prefix needed
                if "/" in file_ref or "\\" in file_ref:
                    result.warnings.append(ValidationMessage(
                        path=f"{path}.steps",
                        message=f"File reference '{file_ref}' contains path separator. Use just the filename (e.g., 'login' instead of 'screens/login'). The loader automatically looks in screens/ subdirectory.",
                        level="warning"
                    ))
