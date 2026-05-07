"""Main TestValidator class."""

from __future__ import annotations

import json
from pathlib import Path

from .models import ValidationMessage, ValidationResult
from .step import StepValidator
from .screen import ScreenTestValidator
from .flow import FlowTestValidator
from .description import DescriptionValidator


class TestValidator:
    """Validates JsonUI test files."""

    def __init__(self):
        self._test_file_path: Path | None = None
        self._step_validator = StepValidator()
        self._screen_validator = ScreenTestValidator(self._step_validator)
        self._flow_validator = FlowTestValidator(self._step_validator)
        self._description_validator = DescriptionValidator()

    def validate_file(self, file_path: Path) -> ValidationResult:
        """Validate a single test or description file."""
        self._test_file_path = Path(file_path).resolve()
        self._step_validator.set_test_file_path(self._test_file_path)
        self._screen_validator.set_test_file_path(self._test_file_path)
        self._flow_validator.set_test_file_path(self._test_file_path)

        result = ValidationResult(file_path=file_path)

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                result.test_data = data
        except json.JSONDecodeError as e:
            result.errors.append(ValidationMessage(
                path=str(file_path),
                message=f"Invalid JSON: {e}"
            ))
            return result
        except Exception as e:
            result.errors.append(ValidationMessage(
                path=str(file_path),
                message=f"Cannot read file: {e}"
            ))
            return result

        # Determine file type by extension or content
        file_name = file_path.name
        if file_name.endswith('.test.json'):
            self._validate_test(data, str(file_path), result)
        elif 'case_name' in data or (file_path.parent.name == 'descriptions'):
            # Description file (has case_name or is in descriptions folder)
            self._description_validator.validate(data, str(file_path), result)
        elif 'type' in data and data['type'] in ['screen', 'flow']:
            # Test file without .test.json extension
            self._validate_test(data, str(file_path), result)
        else:
            result.errors.append(ValidationMessage(
                path=str(file_path),
                message="Unknown file type: expected test file (.test.json) or description file"
            ))

        return result

    def validate_data(self, data: dict, name: str = "test") -> ValidationResult:
        """Validate test data directly (for testing)."""
        result = ValidationResult(file_path=Path(name))
        result.test_data = data
        self._validate_test(data, name, result)
        return result

    def _validate_test(self, data: dict, path: str, result: ValidationResult):
        """Validate test structure."""
        test_type = data.get("type")

        if test_type == "screen":
            self._screen_validator.validate(data, path, result)
        elif test_type == "flow":
            self._flow_validator.validate(data, path, result)
        else:
            result.errors.append(ValidationMessage(
                path=path,
                message=f"Unknown or missing test type: {test_type}"
            ))
