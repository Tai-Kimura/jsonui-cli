"""Flow test validation."""

from __future__ import annotations

from pathlib import Path

from .models import ValidationMessage, ValidationResult
from .step import StepValidator


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
