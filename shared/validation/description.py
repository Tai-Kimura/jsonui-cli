"""Description file validation."""

from __future__ import annotations

from .models import ValidationMessage, ValidationResult
from ..schema import VALID_DESCRIPTION_KEYS


class DescriptionValidator:
    """Validates description files."""

    def validate(self, data: dict, path: str, result: ValidationResult):
        """Validate a description file."""
        # Check required field
        if "case_name" not in data:
            result.errors.append(ValidationMessage(
                path=path,
                message="Description file missing required 'case_name' field"
            ))

        # Check for unknown keys
        for key in data.keys():
            if key not in VALID_DESCRIPTION_KEYS:
                result.warnings.append(ValidationMessage(
                    path=path,
                    message=f"Unknown description key: {key}",
                    level="warning"
                ))

        # Validate case_name is non-empty string
        if "case_name" in data:
            case_name = data["case_name"]
            if not isinstance(case_name, str) or not case_name.strip():
                result.errors.append(ValidationMessage(
                    path=path,
                    message="'case_name' must be a non-empty string"
                ))

        # Validate summary is string if present
        if "summary" in data and not isinstance(data["summary"], str):
            result.errors.append(ValidationMessage(
                path=path,
                message="'summary' must be a string"
            ))

        # Validate preconditions is array of strings if present
        if "preconditions" in data:
            preconditions = data["preconditions"]
            if not isinstance(preconditions, list):
                result.errors.append(ValidationMessage(
                    path=path,
                    message="'preconditions' must be an array"
                ))
            elif not all(isinstance(item, str) for item in preconditions):
                result.errors.append(ValidationMessage(
                    path=path,
                    message="'preconditions' must be an array of strings"
                ))

        # Validate test_procedure is array of strings if present
        if "test_procedure" in data:
            test_procedure = data["test_procedure"]
            if not isinstance(test_procedure, list):
                result.errors.append(ValidationMessage(
                    path=path,
                    message="'test_procedure' must be an array"
                ))
            elif not all(isinstance(item, str) for item in test_procedure):
                result.errors.append(ValidationMessage(
                    path=path,
                    message="'test_procedure' must be an array of strings"
                ))

        # Validate expected_results is array of strings if present
        if "expected_results" in data:
            expected_results = data["expected_results"]
            if not isinstance(expected_results, list):
                result.errors.append(ValidationMessage(
                    path=path,
                    message="'expected_results' must be an array"
                ))
            elif not all(isinstance(item, str) for item in expected_results):
                result.errors.append(ValidationMessage(
                    path=path,
                    message="'expected_results' must be an array of strings"
                ))

        # Validate notes is string if present
        if "notes" in data and not isinstance(data["notes"], str):
            result.errors.append(ValidationMessage(
                path=path,
                message="'notes' must be a string"
            ))
